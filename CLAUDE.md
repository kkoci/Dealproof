# DealProof — Claude Code Guide

## Project

**DealProof** is a verifiable AI negotiation system. Two Claude Sonnet agents (buyer + seller)
negotiate a data deal entirely inside an Intel TDX Trusted Execution Environment on Phala Cloud.
When they agree, the CPU produces a cryptographic DCAP attestation quote — hardware-signed proof
that neither agent cheated, the data was what the seller claimed, and the deal terms are tamper-proof.

Trust stack: TDX enclave (environment) → DCAP attestation (code) → Contexto memory (attested
inputs) → πCreds behavioral credentials (attested conduct) → Auditor witness (attested compliance
report) → Arbitrator (attested deadlock resolution).

---

## Context Loading Order

Before starting any task, read in this order:

1. This file (`CLAUDE.md`) — constraints, flow, what not to build
2. `app/api/routes.py` — the full orchestration in `_negotiate_deal()`
3. `app/api/schemas.py` — all Pydantic models (source of truth for response shape)
4. The relevant layer file (see Key Files below)
5. `README.md` — for phase status and current architecture diagram

---

## Stack

| Layer | Technology |
|-------|-----------|
| AI agents | Claude claude-sonnet-4-6 via `anthropic.AsyncAnthropic` |
| TEE runtime | Phala Cloud CVM (Intel TDX) |
| TEE attestation | dstack tappd — `POST /prpc/Tappd.TdxQuote` |
| Data provenance | Props-inspired Merkle root verification + transcript corpus hashing |
| TinyCloud | Listen transcript store (KV + SQL on Phala TEE) — ETHGlobal NYC integration |
| Seller identity | DKIM email proof — `dkimpy` + DNS-over-HTTPS |
| Attested memory | Contexto `@ekai/memory` sidecar (port 4011) |
| πCreds | LLM-inferred policy + conduct credentials |
| Auditor agent | Read-only TEE compliance witness — `app/agents/auditor.py` |
| Arbitrator agent | Deadlock resolver — `app/agents/arbitrator.py` |
| API framework | FastAPI + uvicorn |
| Persistence | SQLite via aiosqlite |
| Smart contract | Solidity (DealProof.sol) on Sepolia — Phase 4 |
| Frontend | React 18 + Vite 5 + Tailwind CSS |
| Dev Credential | `app/devcred/` — GitHub API → git corpus hashing → SeniorDevCredential (TDX-attested) |

---

## Environment Constraints

DealProof runs inside a Phala Cloud Intel TDX CVM in production.

**DNS**: UDP port 53 is blocked inside the CVM. Always use DNS-over-HTTPS via httpx:
`https://1.1.1.1/dns-query` with `Accept: application/dns-json`. Port 443 is open.

**Secrets**: always read from `.env` via `app/config.py` (Pydantic Settings). Never hardcode
API keys, private keys, or contract addresses.

**Attestation-first**: clients MUST call `GET /api/attest` before sending any payload.
Verify `mrenclave` matches the known build measurement, then POST. The attestation is a
privacy prerequisite, not a response artifact. (Andrew Miller feedback, June 3 2026.)

---

## Actual Request Flow (`routes.py` → `_negotiate_deal`)

```
Step 0   DKIM email proof (optional, non-fatal)
           verify_email_proof() via DoH
           verified_domain injected into SellerAgent system prompt

Step 1   Props verification (optional, fail-fast HTTP 400 on failure)
           compute_merkle_root(chunk_hashes)
           produces data_verification_attestation TDX quote

Step 1b  On-chain escrow deposit (Phase 4, optional)

Step Q   DataQualityAgent (optional, non-fatal)
           DataQualityAgent.assess(data_description, quality_metrics) → DataQualityReport
           quality_hash included in TDX re-attestation
           quality_context injected into BuyerAgent + SellerAgent system prompts

Step M1  Contexto memory pre-deal
           search_memories() → inject context into agent prompts
           get_memory_hash() → memory_hash (state A)

Step 3   Negotiation loop
           BuyerAgent ↔ SellerAgent (AsyncAnthropic)
           ArbitratorAgent called if max_rounds exhausted without agreement (non-fatal)
             → agreed=True + arbitrated=True if arbitration succeeds

Step M2  (if agreed) Contexto memory post-deal
           add_memories() for both agents
           get_memory_hash() → memory_hash_post (state B)

Step P   (if agreed) πCreds audit
           audit_agent_policy() × 2
           audit_deal_conduct()
           hash_credentials() → picreds_hash

Step A   (if agreed) Auditor compliance witness
           AuditorAgent.audit() → AuditReport
           audit_credential_hash = SHA-256(report fields)
           audit_credential_hash = SHA-256(report fields)
           Re-attest: SHA-256(deal + hashA + hashB + picreds_hash + audit_credential_hash + quality_hash) → TDX quote

Step 3b  (if agreed) On-chain escrow release

Step 4   Persist DealResult to SQLite, return response
```

Props verification runs BEFORE the negotiation loop. Memory is split: recall before,
store after. πCreds, Auditor, and post-deal memory only run on agreement.
Arbitrator runs inside the negotiation loop only when max_rounds is exhausted without agreement.

---

## Key Files

```
app/api/routes.py          All HTTP endpoints + full _negotiate_deal() orchestration
app/api/schemas.py         DealCreate, DealResult, PiCred Pydantic models
app/agents/buyer.py        BuyerAgent (claude-sonnet-4-6)
app/agents/seller.py       SellerAgent (claude-sonnet-4-6, accepts verified_domain)
app/agents/negotiation.py  run_negotiation() loop + first-pass sign_result() + arbitrator wiring
app/agents/auditor.py      AuditorAgent — read-only TEE witness, AuditReport + credential_hash
app/agents/arbitrator.py   ArbitratorAgent — deadlock resolver, price clamped to [floor, budget]
app/agents/data_credential.py  DataCredentialAgent — team dynamics credential from TinyCloud corpus (ETHGlobal M3)
app/agents/data_quality.py     DataQualityAgent — TEE-resident dataset quality assessor; quality_hash in TDX quote
app/tee/attestation.py     sign_result() → POST /prpc/Tappd.TdxQuote
app/tee/dcap.py            TDX quote header parser (Phase 7)
app/props/verifier.py      Props Merkle verification
app/props/transcript_hasher.py  TinyCloud transcript → Merkle root (ETHGlobal M1)
TinyCloud/bridge.ts             Bun HTTP bridge: wraps tc CLI for Python ↔ TinyCloud (port 4098)
TinyCloud/feed/                 TinyCloud CLI + saved corpus (conversations.json, transcripts/)
TinyCloud/listen/               TinyCloud Listen backend — source of truth for data shapes
TinyCloud/TINYCLOUD_WORKFLOW.md Auth setup, session patch, bulk download, troubleshooting
PAYLOADS.md                    Full payload reference: deals, ingest modes, real transcript, eval corpora
app/rate_limit.py          Shared slowapi Limiter — per-IP rate limits on paid-API endpoints
app/dkim/verifier.py       DKIM email proof (dkimpy + DoH)
app/memory/client.py       Contexto sidecar client (search, add, get_memory_hash)
app/picreds/auditor.py     LLM audit: audit_agent_policy(), audit_deal_conduct()
app/picreds/constraints.py Deterministic constraint checks (no LLM) — authoritative booleans
app/picreds/credential.py  make_credential(), hash_credentials()
demo.py                    CLI demo — transcript + attestations + memory + πCreds + auditor + arbitrator
memory-service/            Contexto @ekai/memory sidecar (Node.js, port 4011)
frontend/                  React 18 + Vite 5 + Tailwind — Offer Check UI + Dev Credential backend (see below)

--- Offer Check vertical (vertical/hr-offer-check branch) — see build_spec_offer_check.md
    and offercheck_phase2_spec.md (agentic layer — different numbering scheme, see README) ---
app/offercheck/schemas.py     CompetingOffer, ConsistencyCheck, SessionView, AttestationReceipt, DcapVerification, OfferLetterExtraction, Company/Bulk/Credential/Agentic schemas, EmployerInvite* / CandidateJoinRequest schemas
app/offercheck/verifier.py    check_consistency() — software-only plausibility check, no LLM/TEE
app/offercheck/negotiation.py Pure state machine + attestation hashing: apply_move(), attested_terms(), competing_offer_hash(), final_gap_pct(), market_percentile()
app/offercheck/store.py       In-memory Session store (no DB, no auth beyond opaque tokens) — company_id/credential/attestation/candidate_floor/employer_authority_limit fields
app/offercheck/invites.py     EmployerInvite in-memory store — employer-initiated negotiation, pending until a candidate claims it (see "Employer-Initiated Invites" below)
app/offercheck/auth.py        In-memory Company store (Phase 3) — register_company(), get_company_by_api_key(), connect_ats()
app/offercheck/credential.py  OfferVerifiedCredential + PackageCredential — deterministic capitulation/convergence checks, no LLM (mirrors app/picreds/constraints.py)
app/offercheck/billing.py     Pricing tiers (individual/team/growth/enterprise) + record_verification_usage() (StripeNotConfigured-gated)
app/offercheck/parsing.py     PDF offer-letter parsing (Phase 2) — pypdf text extraction + Claude field extraction
app/offercheck/integrations/  greenhouse.py, lever.py (outbound notify + HMAC webhook verify), workday.py (deliberate stub),
                               market_data.py (external market-comparator fetch — BLS OEWS (US) + ONS ASHE (UK), cached, never raises)
app/offercheck/package.py     Phase 2B: OfferPackage math (total_comp_value, hard clamps, is_converged) + a parallel package state machine (apply_package_move, package_current_turn) — can't share app/offercheck/negotiation.py's scalar apply_move()
app/offercheck/agents/        candidate_agent.py, employer_agent.py (mirror app/agents/buyer.py, seller.py) + mediator.py (mirrors app/agents/negotiation.py);
                               package_candidate_agent.py, package_employer_agent.py, package_mediator.py (Phase 2B counterparts, package-shaped I/O)
app/offercheck/demo_auth.py   Magic-link auth — stateless HMAC tokens, single-use consumption, per-session spend cap, startup fail-fast
app/offercheck/rate_limit.py  Per-IP hourly rate limits — session creation + both agentic endpoints, hardcoded limits, no new env vars
app/offercheck/routes.py      POST /api/offercheck/sessions, /parse-offer-letter, /employer/band, /employer/move, /candidate/move, /company/register,
                               /company/ats-connect, /company/verify/bulk, /integrations/{provider}/webhook/{company_id}, /sessions/{id}/start-agentic,
                               /sessions/{id}/start-agentic-package, /auth/demo-link, /employer/new, /candidate/join/{invite_id};
                               GET /sessions/{id}, /attest, /dcap-verify, /credential, /company/sessions, /auth/verify, /employer/invite/{invite_id};
                               PATCH /sessions/{id}/candidate/enable-agentic, /sessions/{id}/employer/enable-agentic
frontend/src/pages/offercheck/  Landing, CandidateNew (+ PDF upload + AI-negotiation floor + package terms), CandidateJoin (employer-invite claim
                                 form, same fields as CandidateNew), CandidateSession, EmployerSession (+ attestation/credential panel + agentic
                                 panel + package results table + attestation-first input gating + stage spine/spotlighted-next-action via
                                 getNextAction()/ActionPanels, see "Offer Check Session UX" below), Demo (magic-link spectator view), CompanyRegister,
                                 CompanyNew (employer-initiated invite creation + status check), Dashboard — all page wrappers max-w-3xl

--- Dev Credential vertical (product/dev-credential branch) — merged 2026-07-18, see "Merge: Dev Credential
    into Offer Check" below. Backend is live and mounted (app/main.py registers devcred_router); the
    frontend pages below are NOT routed from App.jsx — Offer Check's App.jsx/NavBar/theme are what ship,
    per the merge decision. Kept in the tree as reference pending the git-verification-step integration
    into Offer Check's own flow (proposal pending, not yet built). ---
app/devcred/__init__.py        Package init
app/devcred/git_hasher.py                  hash_commit(), compute_repo_corpus_root(), extract_commit_metrics() — no LLM
app/devcred/routes.py                      POST /api/devcred/ingest — GitHub API fetch, corpus hash, metrics; token never persisted
app/devcred/agents/git_inspector.py        GitInspectorAgent — deterministic hard findings (years, languages_deep, test_culture, seniority_signal)
app/devcred/agents/git_evaluator.py        GitEvaluatorAgent — LLM evaluation grounded in hard findings; seniority clamped >= hard signal
app/devcred/schemas.py                     SeniorDevCredential + DevCredEvaluateResponse + DevCredStatusResponse
(routes.py Phase 3)                        POST /api/devcred/{id}/evaluate + GET /api/devcred/{id}
scripts/generate_git_fixtures.py           7 scenarios: genuine_senior/mid/junior + 3 SCAE adversarial + thin_history
tests/test_devcred.py                      29 tests — corpus root, SCAE ×3, inspector ×4, clamp, pipeline, schema, hash
tests/test_devcred_rate_limit.py           5 tests — /evaluate 3/hr + /ingest 10/hr (slowapi), daily 50/day hard stop, counter DB layer
frontend/src/pages/devcred/Landing.jsx     UNROUTED — /devcred/ hero, flow diagram, privacy pills, 3-step explanation (dark/indigo theme, not reused)
frontend/src/pages/devcred/Setup.jsx       UNROUTED — /devcred/new token input (cleared post-submit), repo selector, progress steps, attestation-first
                                            input gating (GET /api/attest via getEnclaveAttestation()) + redpill.ai-style Verification Center,
                                            see "Offer Check Session UX" below
frontend/src/pages/devcred/Results.jsx     UNROUTED — /devcred/:id credential card + TrustStackBar + share/download actions
frontend/src/components/TrustStackBar.jsx  UNROUTED — animated trust stack: TDX ENCLAVE → DCAP → REPO CORPUS → DEV CREDENTIAL
```

---

## DealResult Response Fields

```
attestation                   TDX quote (re-attested after Auditor if agreed)
data_verification_attestation TDX quote from Props verification
dkim_verification             {domain, verified, dns_unavailable, error} or null
memory_hash                   pre-deal buyer:seller hash (state A)
memory_hash_post              post-deal buyer:seller hash (state B)
memory_attested               bool
picreds                       list[DealProofCredential] — policy×2, conduct×1
picreds_hash                  SHA-256 of all credentials, embedded in TDX report_data
picreds_attested              bool
audit_report                  {genuine_negotiation, round_count, final_price,
                               summary, credential_hash} or null
arbitrated                    bool — true when ArbitratorAgent resolved a deadlock
memory_context_hash           SHA-256 of recalled memories injected into agent prompts
                               proves what the agents remembered, not just that state changed
memory_write_hash             SHA-256 of outcome_messages written to memory post-deal
                               proves this deal caused the A→B state transition
data_quality_report           {completeness_score, schema_consistent, label_distribution,
                               quality_issues, overall_quality, summary, quality_hash} or null
quality_attested              bool — true when DataQualityAgent ran and deal agreed
transcript                    list of negotiation rounds
```

---

## Test Suite (411 passed, 2 skipped, 3 known-environment failures — run with `pytest`, no Docker or tappd required)

The 3 known failures are in `tests/test_e2e.py` (core DealProof, unrelated to Offer Check) — they
assert on a mocked `sign_result` return value but get back a real `sim_quote:...` hash instead.
Confirmed via `git stash` that these fail identically with zero Offer Check changes applied; this
dev machine runs Python 3.14 while `requirements.txt` pins `pydantic==2.10.5`/`fastapi==0.115.6`
(no prebuilt wheel for 3.14 — see the "Live 422 Fix" section below for the same friction
documented previously). Not touched or explained further here — flagged so it isn't mistaken for
a regression introduced by the invite work below.

```
tests/test_agents.py          6   BuyerAgent + SellerAgent + AuditorAgent unit tests
tests/test_negotiation.py     8   Negotiation loop, arbitrator, combined attestation payload
tests/test_tee.py            10   KMS + TDX quote HTTP calls + GET /api/attest
tests/test_props.py          23   Props verifier: helpers + failure paths + route gate
tests/test_dkim_verifier.py  19   DKIM: parsing + DNS-over-HTTPS + verification paths
tests/test_memory.py          4   Contexto client: add, search, hash, sidecar-down
tests/test_picreds.py        11   πCreds: constraint checks (5 pure) + auditor + credentials + failure
tests/test_e2e.py            13   Full HTTP stack end-to-end (TestClient + mocks)
tests/test_contract.py        8   Phase 4 escrow: create/complete/refund
tests/test_data_credential.py 7   Transcript hasher + DataCredentialAgent + ingest + credential endpoints
tests/test_data_quality.py   13   DataQualityAgent: happy path, failure path, hash determinism, agent injection, schema
tests/test_offercheck.py     56   Offer Check: consistency checks, revision-loop state machine, privacy, attestation (incl. opening-offer delta /
                                  final_gap_pct, external market comparator / market_percentile via BLS + ONS — fetch mocked, source-selection,
                                  unmapped-role and HTTP-error fallback, never-raises, HTTP e2e wiring), PDF parsing, HTTP e2e
tests/test_offercheck_phase3.py 34   Offer Check: company auth, credential, billing, ATS integrations, bulk verify, webhooks, HTTP e2e
tests/test_offercheck_agentic.py 25  Offer Check: CandidateAgent/EmployerAgent clamps, mediator convergence, reasoning-never-crosses-boundary, mixed human/agentic value-exposure boundary, PATCH enable-agentic endpoints, query-token param rename regression, HTTP e2e
tests/test_offercheck_demo_auth.py 23  Offer Check: HMAC token roundtrip/tamper/expiry, single-use, spend cap, demo-link + verify + gated start-agentic HTTP e2e
tests/test_offercheck_package.py 43  Offer Check: total_comp formula, hard clamps, package turn-order, reasoning-never-crosses-boundary, convergence hint, package credential, package-state SessionView sync, PATCH enable-agentic-package endpoints, converged_hint field, HTTP e2e
tests/test_offercheck_rate_limit.py 23  Offer Check: per-IP limits (session-create, agentic-call, provenance-verify, parse-offer-letter, move, company-register, bulk-verify), X-Forwarded-For handling, independent buckets, HTTP e2e 429s
tests/test_offercheck_invites.py 12  Offer Check: employer-initiated invite lifecycle (create → unclaimed status → join → normal Session),
                                      company-auth gating, double-claim rejection, sealed agentic floor pass-through
tests/test_offercheck_approval.py 31  Offer Check: PENDING_APPROVAL resolution rule (both-approve/decline-wins/reopen/stalemate),
                                      reopen turn-assignment, opening_employer_offer survives a reopen untouched, package-mode parity, HTTP e2e
```

**Resilience guarantees:**
- Memory sidecar down → deal proceeds, `memory_attested: false`
- πCreds audit fails → deal proceeds, `picreds: null`, `picreds_attested: false`
- DKIM fails → deal proceeds, `dkim_verification.verified: false`
- Auditor fails → deal proceeds, `audit_report: null`
- Arbitrator fails → negotiation returns `agreed: false` as before

Run tests: `pytest tests/ -v` (no Docker, no tappd required)

---

## Phase Status

| Phase | What | Status |
|-------|------|--------|
| 1–6 | Scaffold, TEE, Props, escrow, polish, DKIM + React frontend | ✅ Complete |
| 7 | DCAP quote parsing — header done; on-chain verifier contract pending | 🔄 Partial |
| 8 | Contexto attested memory — sidecar + memory_hash A→B in TDX quote | ✅ Complete |
| 9 | πCreds — LLM policy + conduct credentials attested in TDX quote | ✅ Complete |
| 10 | Auditor agent — read-only TEE compliance witness; credential_hash in TDX report_data | ✅ Complete |
| 11 | Arbitrator agent — deadlock resolution; arbitrated settlement attested in TDX quote | ✅ Complete |
| 12 | DCAP on-chain verifier contract | 🔜 Pending |
| **ETHGlobal NYC — TinyCloud Integration** | | |
| M1 | Transcript corpus hasher — `app/props/transcript_hasher.py` | ✅ Complete |
| M2 | Corpus ingestion endpoint — `POST /api/transcripts/ingest` (direct + tinycloud modes) | ✅ Complete |
| M3 | DataCredentialAgent — TEE-attested team dynamics credential | ✅ Complete |
| M4 | Credential endpoint — `POST /api/deals/{id}/credential` | ✅ Complete |
| M5 | Tests — transcript hasher + ingestion + credential endpoint | ✅ Complete |
| M6 | Arc on-chain credential anchoring — ArcIDRegistry.register() via web3.py | ✅ Complete |
| M7 | Hedera HCS autonomous deal outcome publishing — hiero_sdk_python | ✅ Complete |
| M8 | ENS agent identity — reverse resolution + GET /api/ens/agents | ✅ Complete |
| M9 | ETHGlobal NYC prize submission copy — ETHGLOBAL_SUBMISSIONS.md | ✅ Complete |
| **Offer Check — vertical/hr-offer-check** | | |
| OC-P1 | Phase 1 POC — revision-loop state machine, in-memory sessions, no TEE/LLM/DB (`app/offercheck/`) | ✅ Complete |
| OC-P2 | TDX attestation receipt on session close, DCAP quote parsing, PDF offer-letter upload + Claude extraction | ✅ Complete |
| OC-P3 | Company auth, bulk verify, TA dashboard, ATS integrations, πCreds conduct credential, billing | ✅ Complete |
| OC-P4 | Real database (companies + sessions still in-memory) | 🔜 Pending |
| OC-P5 | Agentic negotiation Phase 2A (`offercheck_phase2_spec.md`) — CandidateAgent + EmployerAgent, sealed floor/band, mediator over the real state machine | ✅ Complete |
| OC-P6 | Agentic Phase 2B — full compensation package negotiation | ✅ Complete |
| OC-P7 | Agentic Phase 2C — real Phala Cloud TDX deployment for the agent loop (currently: simulation-mode reasoning, same as the rest of this vertical) | 🔜 Pending |
| OC-P8 | Magic-link auth — gates every Claude-calling endpoint, single-use tokens, spend cap, startup fail-fast | ✅ Complete |
| OC-P9 | Tests — `tests/test_offercheck_package.py` (34 tests) | ✅ Complete |
| OC-P10 | Per-IP rate limiting on session creation + both agentic endpoints — closes the self-issued-token cost-drain gap found during Phase 2C deploy prep | ✅ Complete |
| OC-P11 | Tests — `tests/test_offercheck_rate_limit.py` (10 tests) | ✅ Complete |
| OC-P12 | Live negotiation transcript (agentic-mode round values exposed to both parties); post-creation "enable AI negotiation" opt-in (PATCH endpoints); package-mode `SessionView` sync bug fix | ✅ Complete |
| OC-P13 | Tests — 11 new cases in `tests/test_offercheck_agentic.py`, 1 new case in `tests/test_offercheck_package.py` | ✅ Complete |
| OC-P14 | Live 422 fix (query-param/body-field name collision in start-agentic routes); package-mode "enable AI negotiation" opt-in parity (2 new PATCH endpoints); full transcript UI pass (chat-bubble round history, live round counter + spinner, convergence hint); demo-link auto-prefill sync fix | ✅ Complete |
| OC-P15 | Tests — 9 new cases across `tests/test_offercheck_package.py` and `tests/test_offercheck_agentic.py` | ✅ Complete |
| OC-P16 | Employer-initiated invites — `POST /employer/new`, `GET /employer/invite/{id}`, `POST /candidate/join/{id}` (`app/offercheck/invites.py`); `CompanyNew.jsx` + `CandidateJoin.jsx` | ✅ Complete |
| OC-P17 | Tests — `tests/test_offercheck_invites.py` (10 tests) | ✅ Complete |
| OC-P18 | Merge `product/dev-credential` into this branch — backend fully mounted (`app/devcred/*`, `devcred_router`), App.jsx conflict resolved in Offer Check's favor per merge decision (see "Merge: Dev Credential into Offer Check" below); devcred's own frontend pages unrouted pending the integration proposal | ✅ Complete |
| OC-P19 | Fix devcred's `git_hasher.py`/`git_inspector.py` to iterate all branches (not just `main`), SHA-deduplicated, so feature/PR-only commits aren't missed | 🔜 Pending (plan confirmed, not yet built) |
| OC-P20 | Fold Dev Credential's git-verification capability into Offer Check's candidate/employer flow as a pre-negotiation step, using Offer Check's own page/component patterns | 🔜 Pending (insertion point proposed, not yet built) |
| OC-P21 | Attestation-first input gating (`GET /api/attest` via `getEnclaveAttestation()`) on CandidateSession/EmployerSession's sensitive inputs; human decision trace bubble + one-sided-decline fallback bubble in the round history | ✅ Complete |
| OC-P22 | `HowThisWorksStrip`; stage spine + spotlighted next action (`getNextAction()`/`getStageStatuses()`/`StageSpine`/`ActionPanels`) replacing "show every applicable panel at once"; fixed a persistent-status-vs-actionable-choice collapse regression (verified-credential summary + agentic run results) found immediately after shipping — see "Offer Check Session UX" below | ✅ Complete |
| OC-P23 | Container width normalization — every Offer Check page wrapper (session views, invite/join flows, company auth, dashboard, demo) to `max-w-3xl`, up from `max-w-lg`/`max-w-md` | ✅ Complete |
| **Dev Credential vertical** | **product/dev-credential branch (merged into vertical/hr-offer-check 2026-07-18)** | |
| DC-1 | Git ingestion + corpus hashing — `app/devcred/git_hasher.py` + `POST /api/devcred/ingest` | ✅ Complete |
| DC-2 | GitAnalysisAgent (GitInspectorAgent deterministic + GitEvaluatorAgent LLM) | ✅ Complete |
| DC-3 | SeniorDevCredential schema + `POST /api/devcred/{id}/evaluate` + TDX attestation | ✅ Complete |
| DC-4 | Synthetic fixtures + SCAE adversarial tests — `tests/test_devcred.py` (29 tests) | ✅ Complete |
| DC-5 | Frontend `/devcred/` pages — credential card + trust stack + shareable URL; `Setup.jsx` gained attestation-first input gating + a Verification Center first, then the same pattern was ported to OC-P21's CandidateSession/EmployerSession work | ✅ Complete, but unrouted after the merge (see OC-P18) — superseded by OC-P20's in-Offer-Check integration |
| DC-6 | Rate limiting — slowapi 3/hr (`/evaluate`) + 10/hr (`/ingest`) per IP; daily 50/day hard stop via `eval_counters` table | ✅ Complete |

---

## πCreds Eval Architecture

`app/picreds/constraints.py` runs **before** the LLM audit in `audit_deal_conduct()`.
It contains pure deterministic functions — no LLM, no network. Verifiable from transcript alone.

**Hard constraint booleans are authoritative — code overrides LLM output:**
```python
"buyer_budget_respected":    constraint_results["buyer_budget"].passed   # NOT from LLM
"seller_floor_respected":    constraint_results["seller_floor"].passed   # NOT from LLM
"no_sudden_capitulation":    constraint_results["capitulation"].passed   # NOT from LLM
"convergence_pattern_valid": constraint_results["convergence"].passed    # NOT from LLM
"genuine_negotiation": False if any_hard_failure else llm.get("genuine_negotiation", True)
```

`genuine_negotiation` is `False` if **any** hard check fails, regardless of what the LLM returns.
The LLM prompt also states this explicitly so its assessment text is consistent.

**Checks implemented** (in `constraints.py`):
- `check_buyer_budget_respected` — every buyer offer ≤ buyer_budget
- `check_seller_floor_respected` — every seller offer ≥ floor_price
- `check_no_sudden_capitulation` — no agent moves > `capitulation_threshold` (default `0.40`) in one round
- `check_convergence_pattern` — buyer prices non-decreasing, seller prices non-increasing

**`check_minimum_rounds` is intentionally absent and must not be added.**
A fast deal (seller opens at an acceptable price, buyer accepts) is not a protocol violation.
Requiring multiple rounds produces false positives on legitimate quick agreements.

`CAPITULATION_THRESHOLD = 0.40` is a module-level constant in `constraints.py`, configurable
per call via `run_all_checks(..., capitulation_threshold=0.40)`.

---

## Auditor + Arbitrator Architecture

### AuditorAgent (`app/agents/auditor.py`)

Read-only TEE witness. Called from `routes.py` (Step A) after πCreds on every agreed deal.
Makes one Claude call; returns `AuditReport` or `None` on failure.

```python
@dataclass
class AuditReport:
    genuine_negotiation: bool   # qualitative — did agents bargain authentically?
    round_count: int
    final_price: float
    summary: str                # one-sentence characterisation
    credential_hash: str        # SHA-256(fields, sort_keys=True) — in TDX report_data
```

Structural checks (`monotonic_convergence`, `within_bounds`, `capitulation`) are intentionally
absent — they belong in `app/picreds/constraints.py` where they run deterministically.
An LLM can misfire on these (confirmed in production: Auditor incorrectly flagged buyer opening
below seller floor as a convergence failure). The Auditor's scope is qualitative only.

The Auditor is independent of πCreds — it receives the same transcript but has no knowledge
of the πCreds findings. It is an additional attestation layer, not a replacement.

### ArbitratorAgent (`app/agents/arbitrator.py`)

Deadlock resolver. Called from inside `run_negotiation()` when `max_rounds` is exhausted
without agreement. Passed as `arbitrator=ArbitratorAgent()` from `routes.py`.

```python
@dataclass
class ArbitrationResult:
    proposed_price: float   # clamped to [floor_price, buyer_budget] in code
    rationale: str
    arbitrated: bool = True
```

**Price clamping is enforced in code regardless of LLM output:**
```python
price = max(floor_price, min(buyer_budget, price))
```

Passing `arbitrator=None` to `run_negotiation()` skips arbitration entirely (used in tests
that don't want arbitration to activate).

**`arbitration_enabled` flag is intentionally absent** — the arbitrator is always active
when an `ArbitratorAgent` instance is passed. Control it by passing `None` instead.

---

## DataQualityAgent Architecture

`app/agents/data_quality.py` runs at **Step Q** — before memory recall and before the
negotiation loop — when `quality_metrics` is provided in `DealCreate`.

### Flow

```
DealCreate.quality_metrics (DataQualityMetrics)
  → DataQualityAgent.assess(data_description, metrics)
      → one Claude call → DataQualityReport
          → build_quality_context(report, "buyer")  → injected into BuyerAgent system prompt
          → build_quality_context(report, "seller") → injected into SellerAgent system prompt
          → report.quality_hash                     → included in TDX re-attestation payload
  → DealResult.data_quality_report (dict)
  → DealResult.quality_attested (bool)
```

### DataQualityMetrics (DealCreate field)

```python
class DataQualityMetrics(BaseModel):
    row_count: int
    column_names: list[str]
    null_rates: dict[str, float]          # column → null rate 0.0–1.0
    label_column: str | None              # target column name
    label_distribution: dict[str, float] | None  # {"normal": 0.842, "anomaly": 0.158}
    schema_valid: bool = True
    additional_notes: str | None
```

### DataQualityReport

```python
@dataclass
class DataQualityReport:
    completeness_score: float   # mean(1 - null_rate) across columns
    schema_consistent: bool
    label_distribution: dict | None
    quality_issues: list[str]   # e.g. "12.4% null rate in pressure_hpa column"
    overall_quality: str        # "high" | "medium" | "low"
    summary: str                # one sentence
    quality_hash: str           # SHA-256(report fields) — in TDX report_data
```

### What agents see

Both agents receive a `[TEE-VERIFIED DATASET QUALITY CREDENTIAL]` block in their system
prompts containing `overall_quality`, `completeness_score`, `quality_issues`, and
`label_distribution`. The buyer is told to cite issues when negotiating down; the seller is
told to be transparent and price issues in proactively.

### Resilience

DataQualityAgent is non-fatal. If it fails, `data_quality_report: null`, `quality_attested: false`,
and agents proceed without quality context — same pattern as memory, πCreds, Auditor.

---

## Dev Credential Rate Limiting

**SECURITY: Any endpoint that calls an external paid API (Claude, GitHub) must be
rate-limited. This is a standing requirement** — see the same rule enforced on the
Offer Check vertical (`vertical/hr-offer-check` branch, `app/offercheck/rate_limit.py`).

`app/rate_limit.py` holds one process-wide `slowapi.Limiter` (`key_func=get_remote_address`),
imported by `app/main.py` (wires `app.state.limiter` + `SlowAPIMiddleware` +
`RateLimitExceeded` → 429 JSON handler) and by `app/devcred/routes.py`.

| Endpoint | Limit | Reason |
|----------|-------|--------|
| `POST /api/devcred/{id}/evaluate` | 3/hour/IP | Calls Claude (`GitEvaluatorAgent`) — paid, primary credit-drain risk |
| `POST /api/devcred/ingest` | 10/hour/IP | Calls GitHub API — free tier, lower priority, still rate-limited per the standing rule |

**Daily hard stop, independent of the per-IP limit:** `app/db.py`'s `eval_counters` table
(one row per UTC day) tracks total `/evaluate` calls across all callers. `evaluate_credential()`
calls `db.increment_daily_eval_count(today)` before touching the DB record or Claude; if the
returned count exceeds `DAILY_EVAL_LIMIT` (50, module constant in `app/devcred/routes.py`), it
calls `db.decrement_daily_eval_count(today)` to compensate (so the rejected call isn't counted)
and returns HTTP 503. The increment-then-compensate pattern keeps the check atomic under
SQLite's serialized writers without a separate lock.

Both route functions take a `request: Request` argument — required by slowapi's `@limiter.limit(...)`
decorator to read `request.client.host`. Any test that calls these functions directly (not through
`TestClient`) must construct a real `starlette.requests.Request` with a `client` tuple in its scope;
see `_fake_request()` in `tests/test_devcred.py` / `tests/test_devcred_rate_limit.py`.

---

## ETHGlobal NYC — TinyCloud Integration

**Context:** DealProof integrates with TinyCloud's Listen app. Listen stores Fireflies/Google Meet
transcripts in TinyCloud KV/SQL on a Phala TEE CVM (`api.listen.tinycloud.xyz`). DealProof runs
on its own Phala TEE CVM. Both are TEE-native — two attested processes, verifiable end-to-end.

**TinyCloud repos:** `TinyCloud/feed` (CLI read tooling) + `TinyCloud/listen` (transcript backend)

**TinyCloud transcript data shape** (`NormalizedTranscriptSentence`):
```python
{
    "index": int,             # 0-based position
    "speaker_id": str,        # slugified name e.g. "alice-johnson"
    "speaker_name": str,      # human-readable
    "text": str,
    "start_time": float | None,
    "end_time": float | None,
    "language": str | None,   # null → coerce to "en"
}
```
Stored in TinyCloud KV at: `xyz.tinycloud.listen/transcript/{conversationId}`
Conversations in SQL at: `xyz.tinycloud.listen/conversations` (`conversation` table)
258/282 conversations have pre-generated `summary` — prefer summary over raw sentences for tokens.

**Demo flow:**
```
POST /api/transcripts/ingest  (corpus_id, mode="local"|"tinycloud"|"direct", ...)
  → corpus_root, seller_proof

POST /api/deals/run  (data_hash: corpus_root, seller_proof, buyer_budget, ...)
  → deal_id, attestation

POST /api/deals/{id}/credential
  → TeamDynamicsCredential + TDX quote + Arc tx + Hedera tx
```

**Three ingest modes** (`POST /api/transcripts/ingest`):

| mode | what it does | when to use |
|------|-------------|-------------|
| `direct` | uses `conversations` array in the request body | tests, synthetic data |
| `local` | reads `TinyCloud/feed/conversations.json` + `TinyCloud/feed/transcripts/*.json` | dev, offline |
| `tinycloud` | fetches live via the bridge at `http://localhost:4098` | fresh data, CI |

**Bridge** (`TinyCloud/bridge.ts`, port 4098):
- Why: TinyCloud node requires UCAN delegation auth + specific TLS JA3 fingerprint; Python httpx fails both
- What: Bun script that wraps the `tc` CLI (auth handled by tc's existing session)
- Exposes: `POST /v1/sql`, `GET /v1/kv/:key`, `GET /health`
- Run from `TinyCloud/feed/`: `TC_BIN=./node_modules/.bin/tc bun run ../bridge.ts`

**Local corpus files** (saved via bulk download, not committed):
- `TinyCloud/feed/conversations.json` — 449 SQL rows
- `TinyCloud/feed/transcripts/rec-*.json` — 225 KV transcript blobs

**Session key patch** (one-time after `tc init`):
`~/.tinycloud/profiles/listen/session.json` stores only the public key in `jwk`; `key.json` has the private key.
Fix: copy `key.json` → `session.json.jwk` (see `TinyCloud/TINYCLOUD_WORKFLOW.md` § Step 3).

**Prize targets:** ENS ($4k) + Arc ($2k) + Hedera ($3k) + Unlink ($1k) + World ($2.5k) = $12.5k

---

## Offer Check Architecture (`vertical/hr-offer-check`, Phase 1)

Standalone product sharing this repo for dev speed — see `build_spec_offer_check.md` for the full
phased spec. Follows the same per-vertical isolation pattern as SOC2 / Dev Credential / Fundraising
(`app/<vertical>/` module + own router prefix + `frontend/src/pages/<vertical>/`). **Phase 1 was
deliberately dependency-free**: no TEE, no LLM, no database — pure Python state machine over
in-memory sessions, so the revision-loop product concept could be validated before trust
infrastructure was added. **Phase 2 (current)** still has no database — sessions are still
in-memory — but adds attestation and PDF parsing on top of the same state machine.

**The revision loop is the product** (Tina's bar, per the build spec) — never collapse this to a
single above/below screener. Candidate and employer alternate accept/counter/walk moves, up to 5
rounds, and each counter must causally change the other party's next move.

```
app/offercheck/store.py       Session dataclass — id, tokens, competing_offer, band, history, attestation (in-memory dict)
app/offercheck/verifier.py    check_consistency() — rule-based plausibility screen, NOT a legal verification
app/offercheck/negotiation.py set_employer_band(), apply_move(), attested_terms() — state machine + hashing, pure functions
app/offercheck/parsing.py     extract_text_from_pdf() (pypdf) + extract_offer_from_text() (Claude) — draft prefill only
app/offercheck/routes.py      /api/offercheck/* — token-derived actor identity, never trusted from client input
```

**Privacy invariant (non-negotiable, enforced in `routes.py::_view_for`):** a `SessionView` never
contains the counterparty's raw number. Only `gap_pct`, `state`, `round_number`, and move history
(accept/counter/walk — no values) cross the party boundary. Each viewer's own current value
(`my_current_value`) is fine since it's their own submission. `gap_pct` is computed server-side from
`candidate_ask` vs. `employer_current_offer`; the employer's band (`band_min/mid/max`) is used once,
at band-submission time, to produce that call's gap preview, then never re-exposed.

**Turn order is derived from `state`, not passed by the client:** `PENDING_EMPLOYER` (employer's
turn, must set band first) → `EMPLOYER_RESPONDED` (candidate's turn) ⇄ `CANDIDATE_COUNTERED`
(employer's turn) → `AGREED` | `WALKAWAY` | `EXPIRED`. `round_number` increments once per move
(band submission itself doesn't count); the 5th unresolved counter auto-transitions to `EXPIRED`
inside `apply_move()` — there is no separate "check if expired" endpoint or cron.

**`check_minimum_rounds`-style validation is intentionally absent**, same reasoning as the core
πCreds constraints above: an employer opening at an acceptable band and the candidate accepting
immediately is a legitimate fast deal, not a protocol violation.

**Attestation (Phase 2):** `routes.py::_maybe_attest` runs after every `apply_move()` call and is a
no-op unless `session.state` just became terminal — it's idempotent, so both `employer_move` and
`candidate_move` can call it unconditionally without tracking who closed the session. It calls the
*same* `app/tee/attestation.sign_result()` used by core DealProof — no separate offercheck-specific
enclave code path, because the whole FastAPI process (core + offercheck routes) already runs inside
the TDX CVM in production; attestation is "produce a quote over the outcome," not "run verification
somewhere special." The hashed payload (`negotiation.attested_terms()`) deliberately excludes every
raw number — `competing_offer_hash` and `employer_band_hash` are SHA-256 digests, and only the
already-mutually-known outcome (`state`, `round_number`, `agreed_price`) appears in the clear.
`GET /sessions/{id}/attest` and `/dcap-verify` (the latter reusing `app/tee/dcap.parse_tdx_quote`
verbatim) both 409 until the session is terminal, and accept either party's token — the receipt is
identical regardless of viewer once the outcome is closed.

**Opening-offer delta tracking (`final_gap_pct`):** `band_gap_pct()`/`live_gap_pct()` already measure
the candidate's ask against the employer's *private* band and *current* offer, but neither survives
past the round it's computed in, and neither is attested — a verifier reading `attested_terms()` sees
`agreed_price` in isolation, with no sense of how much movement it represents. `final_gap_pct(session)`
closes that gap against a genuine external anchor: `session.opening_employer_offer`, snapshotted once
in `apply_move()` on the employer's *first* counter and never overwritten afterward (an employer who
accepts immediately, without ever countering, leaves it `None`). Deliberately anchored on the
employer's opening position rather than a self-reported outcome — the candidate agent never controls
what the employer opens with. `(agreed_price - opening_employer_offer) / opening_employer_offer * 100`,
`None` if the session never reached a real employer counter or never reached `agreed_price`. Only the
computed percentage is folded into `attested_terms()` — the raw `opening_employer_offer` stays private,
same discipline as `competing_offer_hash`/`employer_band_hash` never exposing raw band numbers.

**External market comparator (`market_percentile`, `app/offercheck/integrations/market_data.py`):**
`final_gap_pct` is still a *relative* anchor — it only measures negotiation movement against the
employer's own starting position, not whether the final number is reasonable by any outside standard.
`market_percentile` adds that missing *absolute* anchor: where `agreed_price` lands (0-100) against
real third-party salary comparators the negotiating agent never had access to or control over.

Data sources: **BLS OEWS** (US, Bureau of Labor Statistics' Occupational Employment and Wage
Statistics survey) for USD offers and **ONS ASHE** (UK, Office for National Statistics' Annual
Survey of Hours and Earnings) for GBP offers — free and public with no sales process, following
this repo's established external-integration convention (`app/offercheck/integrations/greenhouse.py`
/ `lever.py` / `billing.py` — implement the vendor's documented REST shape via `httpx` directly, no
vendor SDK). This replaces an earlier **PayScale**-based implementation from an initial pass: PayScale
turned out to be enterprise/sales-gated with no self-serve API access at all, so it was never actually
viable to integrate — fully removed, no PayScale code remains. levels.fyi was reconsidered and rejected
again for the same reason as before: no official public/documented API, only unofficial scrapers, the
same "no generic public endpoint" problem `workday.py` already declined to build against.

**Accepted tradeoff, stated plainly:** both BLS and ONS are occupation-code + region granular, not
job-title + seniority-level granular. "Senior Backend Engineer" maps to the same bucket as any other
software-development role at any seniority — the wage *percentile* still carries real signal, but this
is coarser than a paid, job-title-precise source would be. `fetch_market_range`'s signature and
`MarketRange`'s shape are deliberately unchanged from the PayScale version specifically so a more
granular paid source can be swapped in later without touching `negotiation.py`/`schemas.py`/
`routes.py` at all — those layers only ever see the derived percentile, never which source or exact
API answered the call.

**Source selection is currency-based** (`fetch_market_range(role, level, location, currency)`):
`currency == "GBP"` → ONS, anything else (including the default `"USD"`) → BLS. `level` is accepted
for signature stability but not used for occupation-code selection — neither survey's SOC taxonomy is
seniority-stratified; seniority differences show up in the wage percentile spread itself, not in which
occupation bucket a role maps to. **Offer Check doesn't currently capture currency or location
anywhere on `CompetingOffer`/`Session`** (same known gap as the previous pass), so in practice every
real caller today passes the module's `DEFAULT_LOCATION`/`DEFAULT_CURRENCY` ("United States"/"USD")
and **BLS is the only source actually reached in production** until that's added — ONS is fully
implemented and tested, just currently unreached by any real session. Both source functions also only
ever query a *national* aggregate area code today (`0000000` for BLS, `K02000001` for ONS), for the
same reason: no real location signal exists yet to route to a specific metro/region.

Occupation-code mapping (`_map_role_to_bls_soc` / `_map_role_to_ons_soc`): both surveys use an SOC
(Standard Occupational Classification) code, but **US SOC and UK SOC are different taxonomies that
happen to share an acronym** — the two lookup tables are independent and their codes are not
interchangeable. Both are small, deliberately non-exhaustive keyword tables covering common tech
roles; anything unmapped returns `None`, which propagates out as `market_percentile: None` exactly
like any other lookup failure. Confirm both tables against the current BLS SOC (bls.gov/soc) and ONS
SOC (ons.gov.uk) indexes before relying on them in production — some mappings are approximations
(e.g. "product manager" has no dedicated BLS code).

Like Stripe/Greenhouse/Lever/the PayScale version this replaces, the exact BLS/ONS request-response
shapes below have **not** been exercised against a live query in this environment — BLS's OEWS
series-ID construction and per-percentile datatype codes, and ONS's dataset/dimension-label shape,
should both be confirmed against current developer docs (bls.gov/developers,
bls.gov/help/hlpforma.htm#OE, api.ons.gov.uk) before relying on this in production. Configured via
`BLS_API_KEY` (`app/config.py`, optional — BLS's public API works unauthenticated at a lower rate
limit; ONS needs no key at all).

`fetch_market_range_bls(role, location)` / `fetch_market_range_ons(role, location)` never raise
(unmapped role, no network access, timeout, malformed response all degrade to `None`) and each cache
in-memory, keyed by `(source, role, location)` in one shared cache, since the same combination
repeats across sessions and this is a network call kept off the hot path — called at most once per
session, in `routes.py::_maybe_attest`, only when `session.state == "AGREED"` (never on every round).
`negotiation.market_percentile(session, market_range)` stays a separate, pure, synchronous function —
piecewise-linear between the fetched p25/p50/p75, clamped to `[0, 100]` beyond that range — so the
placement math is unit-testable with zero I/O; the fetch and the calculation are two different
concerns on purpose, and this function needed no changes at all for the PayScale→BLS/ONS swap.

**A failed or unmapped market-data lookup degrades gracefully by design — the session still
reaches `AGREED` and still attests normally; `market_percentile` is just `None`.** This is the same
non-fatal resilience pattern as memory/πCreds/Auditor/Arbitrator/DKIM elsewhere in this repo, applied
here for the first time to something that isn't even part of the negotiation itself — a lookup failure
here can *never* block or fail a negotiation, by construction (neither fetch function has a raising
code path at all, not even one `_maybe_attest` needs to catch).

`session.market_percentile` is persisted on `Session` (unlike `final_gap_pct`, which is cheap enough
to recompute live on every `SessionView`/`AttestationReceipt`/`AgenticResult` build) because computing
it requires that async network fetch — there's no synchronous way to get a fresh `MarketRange` at read
time, so the computed percentile is stored once, at the `AGREED` transition, and read directly
thereafter (including by `attested_terms()`, which reads `session.market_percentile` rather than
calling `market_percentile()` again — it has no `MarketRange` to pass and must stay I/O-free). Only
the derived percentile is ever attested or exposed — the raw fetched `p25/p50/p75` range (and which
source/currency answered) is never persisted on `Session` at all, same privacy discipline as
`opening_employer_offer` never appearing in `attested_terms()` raw.

**PDF parsing (Phase 2) is a draft prefill, not a data source:** `POST /parse-offer-letter` returns
`ExtractedOfferFields` (schemas.py) — a deliberately *unvalidated* shape (`base_salary` can be `0`)
distinct from the strict `CompetingOffer` model that `POST /sessions` enforces. A bad or low-confidence
extraction can never become the record of truth; the candidate reviews/edits it client-side first.
Extraction failures (`OfferLetterParseError` — unreadable PDF, scanned image with no text layer,
Claude call failure) return HTTP 422 with a clear detail message; the candidate falls back to manual
entry in the same form. This mirrors the non-fatal resilience pattern used everywhere else in this
repo (memory sidecar, πCreds, Auditor, DKIM) — parsing failing never blocks the product.

**Company auth (Phase 3) sits alongside per-session tokens, not in place of them:**
`app/offercheck/auth.py` is a second, independent in-memory store (`Company`, keyed by a SHA-256'd
API key — the raw key is returned exactly once at `POST /company/register` and never stored). It
adds an optional `X-API-Key` header to `POST /sessions` (tags `company_id` for dashboard visibility)
and drives `POST /company/verify/bulk` + `GET /company/sessions`. It does **not** change how a
session's negotiation actions are authorized — `POST .../employer/band` and `.../employer/move`
still require the per-session `employer_token`, exactly as in Phase 1. This was a deliberate scope
boundary: company auth answers "which sessions belong to us" and "can we act in bulk," not "can we
bypass the share-a-link model for an individual negotiation."

**The conduct credential (`app/offercheck/credential.py`) needs raw values the privacy layer hides
from `SessionView` — so `RoundEntry` gained a `value` field that `_view_for()`/`RoundSummary` still
never read.** Capitulation and convergence are computed from `RoundEntry.value` sequences (per-actor,
in order — `session.original_candidate_ask` is the immutable baseline candidate value, captured once
at session creation, needed because `session.candidate_ask` itself mutates round over round).
`compute_credential()` raises `ValueError` on a non-terminal session — same "don't compute a
conclusion before there's an outcome" discipline as `negotiation.attested_terms()`. The credential's
hash is computed *before* signing (`routes.py::_maybe_attest`) and passed into
`attested_terms(session, credential_hash=...)`, so it lands in the same TDX quote as everything
else — mirroring core DealProof's Step P (πCreds) → Step A (Auditor) → final re-attest ordering.

**Billing and ATS integrations follow the exact `EscrowNotConfigured` convention already established
by `app/contract/escrow.py`:** unset credentials raise a `*NotConfigured` exception
(`billing.StripeNotConfigured`, `integrations._shared.AtsNotConfigured` subclasses per vendor),
caught non-fatally in `routes.py::_maybe_notify` with a log line — a company without billing or ATS
configured gets a session that still closes and attests correctly, just without those two side
effects. `_maybe_notify` is guarded by `session.notified` so it fires at most once per session,
mirroring the `session.attestation is not None` idempotency guard on `_maybe_attest`.

**Nothing in this environment could be verified against a live Stripe, Greenhouse, or Lever
account** — there are no test credentials for any of them here. The pricing-tier logic, HMAC
signature verification, and every `NotConfigured` fallback path are real and tested; the actual
outbound HTTP request shapes (`billing.py`, `integrations/greenhouse.py`, `integrations/lever.py`)
are each explicitly caveated in their docstrings as unverified against a live account — confirm
against current vendor docs before depending on them in production. `workday.py` doesn't even
attempt a real call: Workday has no generic public endpoint, only tenant-specific WSDL/OAuth setups,
matching the build spec's own "(stretch)" framing for it.

**Inbound ATS webhooks are authenticated purely by HMAC signature, not by API key:**
`POST /integrations/{provider}/webhook/{company_id}` — the vendor is calling *us*, so there's no
`X-API-Key` exchange in this direction. `company_id` in the path selects whose `webhook_secret` to
verify the `X-Signature` header against; it is not itself a secret (same trust model as `session_id`
+ token in the base flow — the identifier is public, the token/signature is what actually gates
access).

---

## Agentic Negotiation (`offercheck_phase2_spec.md` Phase 2A)

Added at explicit user request on top of the base build spec — that spec's own Phase 1 says "no LLM"
outright, and this vertical was human-only through OC-1 → OC-8. The user's framing: "it has to
resemble DealProof otherwise what's the point" — so `app/offercheck/agents/` is a deliberate mirror of
`app/agents/{buyer,seller,negotiation}.py`, not a new pattern:

```
app/offercheck/agents/candidate_agent.py  mirrors app/agents/buyer.py — hard floor clamp in code
app/offercheck/agents/employer_agent.py   mirrors app/agents/seller.py — hard band clamp in code
app/offercheck/agents/mediator.py         mirrors app/agents/negotiation.py::run_negotiation()
```

**The mediator drives the SAME `negotiation.apply_move()` the human endpoints call** — there is no
separate agentic state machine. This is why an agentic session gets identical turn-order,
max-rounds-auto-expiry, TDX attestation, and `credential.py` conduct-credential guarantees for free:
`apply_move()` doesn't know or care whether a human clicked a button or an agent's JSON response drove
the call.

**Two sealed inputs, added to the existing submission endpoints, not new ones:**
`CandidateSubmitRequest.candidate_floor` (+ `candidate_priorities`) and
`EmployerBandRequest.employer_authority_limit` (+ `employer_priorities`) — both optional, both stored
on `Session`, both absent from every response schema (`SessionView` only exposes the *boolean*
`agentic_ready = candidate_floor is not None and employer_authority_limit is not None`). `POST
/sessions/{id}/start-agentic` requires both sealed — `mediator.build_agents()` raises
`AgenticNotReady` (→ HTTP 412) otherwise.

**Privacy contract, deliberately different from the base human flow's gap-%-only contract:**
within a round, each agent *is* told the opposing side's current offer amount — that's this mode's own
contract per `offercheck_phase2_spec.md`: "the offer number per round crosses the boundary, nothing
else." What never crosses, exactly as everywhere else in this vertical: either side's *sealed*
parameter, and either agent's reasoning. `mediator.py` maintains two independent per-agent histories
(`candidate_history`, `employer_history`) — `_own_entry()` keeps an agent's own past turns in full
(including its own reasoning, so it stays self-consistent across rounds, same as core's
BuyerAgent/SellerAgent "remembering" via the Claude message thread), `_crossing_entry()` strips the
*other* agent's turns down to `{action, value}` before they're shown across the boundary. Both agents
also hard-clamp their own returned value in `_parse_response()` regardless of what the LLM says — same
"prompt asks nicely, code guarantees it" discipline as `BuyerAgent.budget` / `SellerAgent.floor_price`
/ `ArbitratorAgent`'s price clamp.

**`build_agents()` is split out from `run_agentic_negotiation()` specifically for testability.**
Patching `anthropic.AsyncAnthropic` by module path does *not* give `CandidateAgent` and
`EmployerAgent` independently different mocks — both modules `import anthropic`, which is the same
singleton module object, so two `patch("...anthropic.AsyncAnthropic", ...)` calls collide on the
identical attribute (whichever patch is innermost wins for *both* agents, silently breaking
round-robin tests in confusing ways — this cost real debugging time when first written). The fix,
matching `tests/test_negotiation.py`'s existing pattern for BuyerAgent/SellerAgent: construct real
agent instances (no network call happens at construction), then
`patch.object(agent.client.messages, "create", side_effect=...)` on each *instance* directly. This is
why `mediator.build_agents(session) -> (CandidateAgent, EmployerAgent)` and
`mediator.run_agentic_negotiation(session, candidate_agent, employer_agent)` are two functions, not
one — tests construct via `build_agents()`, patch each instance, then call
`run_agentic_negotiation()` directly with pre-built, pre-patched agents.

**Verified against the real Anthropic API**, not just mocked tests (a real key was available in this
environment as of this phase, unlike Phase 2's PDF-parsing verification which could not be):
employer opened, candidate countered, employer countered, candidate accepted — 4 rounds, ~11 seconds,
`genuine_negotiation: true`. Confirms the full loop — sealed inputs, turn order, hard clamps, credential
computation, attestation — end to end with real model behavior, not just scripted mock responses.

**Not built (Phase 2B/2C, per the spec's own phasing and its own "what not to build in Phase 2" list):**
full compensation-package negotiation (equity/signing/bonus/remote/PTO as one structured object per
round), and moving the agent loop's I/O onto a real Phala Cloud TDX deployment specifically (it already
inherits the same simulation-mode `sign_result()` reasoning as the rest of this vertical — there is no
separate "the agent loop is somehow less inside the enclave" gap, just the same not-yet-deployed-to-Phala
gap that applies to all of Offer Check).

---

## Magic-Link Auth (`app/offercheck/demo_auth.py`)

Added on top of Phase 2A at explicit user request, framed as "a 30-minute security fix, not a full
auth system" — and built accordingly: no accounts, no email, no token database, no OAuth. The
non-negotiable rule it exists to enforce: **no endpoint that triggers a Claude API call may run for
an unauthenticated caller.** Currently that's just `start-agentic`; the rule is written into the
module docstring as a standing instruction for whoever adds the next agent-calling endpoint, with a
`# TODO: replace with TinyCloud OpenKey delegation when available` at each call site so it's clear
this is a stopgap, not the final answer.

**Party token OR demo token — deliberately not AND.** The originating request's literal wording
("No exceptions") could be read as requiring both a party token *and* a magic link on every call.
That reading was rejected: a party-token holder (`candidate_token`/`employer_token`) is already
authenticated exactly as for every other session endpoint — requiring a magic link *on top* of that
for the real two-party flow would be friction with no security benefit, and would break the
already-shipped Phase 2A UX (the "Let agents negotiate" button on `CandidateSession`/`EmployerSession`
never needed a magic link and still doesn't). The magic link solves a different problem: sharing a
*working* demo with someone who was never a party to the negotiation. `_authorize_agentic_call()` in
`routes.py` tries the party token first, falls through to the demo token only if that fails, and
401s only if *neither* is valid — which is exactly "prevent unauthenticated access," the rule as
actually stated at the top of the request.

**Tokens are stateless.** `token = f"{expires_at}.{HMAC-SHA256(f'{session_id}:{expires_at}', OFFERCHECK_SECRET_KEY)}"`
— validity is checked by recomputing the signature from the token's own embedded `expires_at`, no
lookup table needed. Only two things need in-memory state, and both are intentionally ephemeral
(lost on restart, same as every other in-memory store in this vertical):
  - **Single-use consumption** (`_CONSUMED_TOKENS`, a `set[str]`) — a demo token is marked consumed
    the moment it passes validation in `_authorize_agentic_call()`, *before* the negotiation runs,
    not gated on the negotiation later succeeding. This means a demo token that hits a transient
    error mid-negotiation cannot be replayed — matches "single-use" strictly, at the cost of not
    being retry-friendly. That tradeoff was made deliberately for a spectator-demo use case where
    replay risk matters more than retry convenience.
  - **Spend cap** (`_CALL_COUNTS`, a `dict[str, int]`) — 15 Claude calls per session (3 full 5-round
    negotiations), incremented in `mediator.py`'s round loop before every actual agent `.decide()`
    call, independent of which auth path was used. This is explicitly a *backstop*: the token system
    is the primary abuse control; the spend cap catches the case a single session accumulates many
    separate authorized runs (e.g. several different party tokens or several different demo links,
    each individually legitimate) that together exceed a sane cost ceiling. `SpendCapExceeded` →
    HTTP 429.

**Startup fail-fast, literally at process startup** (`app/main.py`'s `lifespan`, not lazily on first
use) — `demo_auth.require_secret_key_configured()` raises `RuntimeError` if `OFFERCHECK_SECRET_KEY`
is unset, which prevents the *entire* app (core DealProof routes included, since they share this
process on this branch) from serving any request at all. This was requested explicitly ("fail fast")
and accepted as-is even though it's broader than "just block offercheck" — this branch only serves
this vertical anyway, so the blast radius matches intent. `demo_auth.warn_if_anthropic_keys_identical()`
is the softer companion check (`OFFERCHECK_API_KEY` vs `ANTHROPIC_API_KEY`) — logs, does not block
startup, because a shared key degrading gracefully is preferable to bricking the app over a
usage-tracking nicety.

`OFFERCHECK_SECRET_KEY` / `OFFERCHECK_INTERNAL_KEY` / `OFFERCHECK_API_KEY` (optional) /
`OFFERCHECK_DEMO_BASE_URL` live in `.env` (gitignored). Generate the first two with
`python -c "import secrets; print(secrets.token_hex(32))"`.

---

## Full Compensation Package Negotiation (`offercheck_phase2_spec.md` Phase 2B)

Extends Phase 2A from a single scalar (base salary) to a full package — base, equity_grant,
vesting_years, cliff_months, signing_bonus, annual_bonus_pct, remote, start_date_days, pto_days —
negotiated as one structured object per round.

**Why this is a parallel state machine, not an extension of the scalar one:** `negotiation.apply_move()`
and everything built on it (`RoundEntry.value: float`, `SessionView.gap_pct`, `credential.compute_credential()`)
is scalar by construction. Retrofitting it to carry `float | dict` would touch nearly every file in this
vertical and risk the already-shipped Phase 1 human flow for a feature that's agentic-only. Instead
`app/offercheck/package.py` mirrors the scalar machine's *shape* exactly — `PACKAGE_TERMINAL_STATES`,
`_PACKAGE_TURN_BY_STATE`, `apply_package_move()` — over new `package_*` fields on `Session`
(`package_state`, `package_round_number`, `candidate_current_package`, `employer_current_package`,
`package_history`, `package_agreed`). The Phase 1 human flow is completely untouched by this.

**`total_comp_value(package)`** — `base + annual_bonus_pct/100*base + equity_grant/vesting_years +
signing_bonus` — is the one deterministic number used for (a) hard-clamping candidate/employer packages
to their sealed floor/budget (`clamp_candidate_package()`, `clamp_employer_package()` — same
"prompt asks nicely, code guarantees it" discipline as `CandidateAgent.floor`/`EmployerAgent`'s band
clamp), and (b) convergence detection. Documented explicitly as an approximation, not a real
compensation model — PTO/remote/start-date/cliff are negotiated but don't move this number.

**Convergence detection is a real gap that live testing caught, not a hypothetical:** `is_converged()`
(total comp within 2%) was written and unit-tested but never actually called from anywhere — a live
run walked away from a position that, by the numbers, had already converged (round 4→5: candidate
$261.5K vs employer $256.5K total comp, ~2% apart), because nothing told the employer agent that gap
was small enough to accept. Fixed by adding `package_mediator._currently_converged(session)`, computed
before every round from `session.candidate_current_package`/`employer_current_package`, and threading
a `converged_hint: bool` through `CandidateAgent.decide()`/`EmployerAgent.decide()` (Phase 2B agents
specifically — Phase 2A's scalar agents don't need this since gap_pct is already directly visible)
into `_build_messages()`, which appends an explicit "you're within 2%, consider accepting" system note
to that round's prompt only when true. Re-verified live afterward: a close-gap scenario now converges
in round 1; a genuinely-far-apart scenario (17.8% gap) correctly does *not* get the hint and negotiates
for real across all 5 rounds. If you add more convergence-driving logic to this vertical, verify it's
actually wired into a prompt somewhere, not just defined — a passing unit test for the pure function
does not mean the mediator calls it.

**`PackageCredential` (`credential.compute_package_credential()`)** reuses the exact same
`_capitulation_issues()`/`_convergence_issues()` helpers `compute_credential()` uses, just fed
`total_comp_value()` sequences instead of raw scalar values — same threshold constant
(`CAPITULATION_THRESHOLD = 0.40`), same "hard invariants in code, no LLM" principle.
`package.attested_package_terms()` mirrors `negotiation.attested_terms()`: hashes the private opening
package, discloses the agreed package (once terminal) in the clear, folds the credential hash in before
signing — same Step-P-before-final-re-attest ordering as everywhere else in this vertical.

**Reuses the Phase 2A/magic-link auth infrastructure verbatim:** `POST /start-agentic-package` calls
the same `_authorize_agentic_call()` (party token OR demo token) and the same
`demo_auth.record_and_check_spend()` per round — no new auth surface was added for this endpoint,
confirming the "any future agent-calling endpoint must add the same check" rule from `demo_auth.py`'s
docstring actually generalizes cleanly to a second endpoint.

**Hard clamp is a best-effort heuristic for the employer's budget overage, not a guarantee:**
`clamp_employer_package()` trims `signing_bonus` first to fit `total_comp_budget` — if base+equity
alone exceed budget, the clamped package can still be over. Documented in the function's own docstring
as a known limitation, not silently glossed over.

---

## Rate Limiting (`app/offercheck/rate_limit.py`)

Found while prepping the Phase 2C Phala deploy, not hypothetical: `POST /sessions` is intentionally
open, no login, per the original Phase 1 spec — but its response hands back **both**
`candidate_token` and `employer_token`. A script can, with zero credential: create a session, seal an
employer band with the token it just received, then call `start-agentic` with the candidate token —
fully self-authorized. Neither of the two existing gates stops this: `demo_auth._authorize_agentic_call()`
only checks "does this caller hold a valid token for *this* session," which a self-issued token
trivially satisfies; `demo_auth.record_and_check_spend()`'s 15-call cap is per-session, so a fresh
session resets it every time. Unbounded session creation therefore means unbounded real Claude spend.

**Fix:** in-memory, per-IP, fixed-window (1 hour) counters — `SESSION_CREATE_LIMIT = 10` on
`POST /sessions`, `AGENTIC_CALL_LIMIT = 5` on both `start-agentic` and `start-agentic-package`.
Both checks run as the first line of their handler, before `_get_session_or_404` and before auth —
a request that will fail auth anyway should still count against the IP's budget, since a scanner
probing with garbage tokens is exactly the traffic this is meant to stop.

`client_ip()` prefers `X-Forwarded-For`'s first hop over the direct socket peer, for when Phala's
ingress sits in front of the container as a reverse proxy. **Worth confirming after the first real
deploy** that Phala actually sets that header — if it doesn't, every request appears to come from
the proxy's own IP and the limiter degrades to a global limit rather than a per-client one.

Limits are hardcoded (`SESSION_CREATE_LIMIT`, `AGENTIC_CALL_LIMIT` module constants), not
env-var-driven — deliberately, so this fix required a rebuilt image but zero new Phala dashboard
entries. State is in-memory and ephemeral (lost on restart), same precedent as `demo_auth`'s
consumed-token set and spend-cap counters, and the session store itself.

**This is a code-level backstop, not a replacement for a hard budget limit on the Anthropic API
key itself in the Anthropic console** — that limit holds regardless of any bug in this file and is
outside what application code can guarantee. Set both.

Every existing offercheck test file's `autouse=True` state-reset fixture now also calls
`rate_limit.reset()` — without it, tests within the same pytest process share rate-limit buckets
(TestClient requests all appear to originate from the same host) and unrelated tests start failing
with 429s once the shared budget is exhausted.

**Pre-Twitter-launch pass found two more gaps in the same class**, both fixed the same way (a new
bucket + a `rate_limit.check_*` call as the first line of the handler):

- `POST /parse-offer-letter` (`PARSE_OFFER_LETTER_LIMIT = 3`) — this endpoint has **no auth
  whatsoever**, not even a party token (it isn't bound to a session yet, per its own docstring), and
  makes a real Claude call via `parsing.parse_offer_letter`. It was the single highest-priority gap
  found in this pass — same bug class as the `arcid2` drain this whole rate-limit module exists to
  prevent, but with an even lower bar (zero credential of any kind, not even a self-issued token).
- `candidate_move` / `employer_move` (`MOVE_LIMIT = 20`) — no Claude cost, so this is a griefing
  backstop, not a spend backstop: a party-token holder could otherwise script instant round-burning
  to force a session to premature `EXPIRED` before the other side ever gets to respond. Looser limit
  than the Claude-calling buckets on purpose — two humans sharing one IP genuinely exchanging 5
  rounds is normal traffic that must not 429.

**A third item from that same pass — re-confirming two *earlier*-flagged endpoints — turned out to
have never actually been fixed, not regressed:** `register_company_route` and `bulk_verify_route`
had zero `rate_limit.check_*` calls (confirmed by grepping every call site in `routes.py`, and by
`git log --all --grep` turning up no prior commit touching either). Both closed the same way:

- `POST /company/register` (`COMPANY_REGISTER_LIMIT = 5`) — unauthenticated by design (it's the
  signup endpoint, no API key exists yet to gate on), but was completely uncapped: unlimited
  signups grow `auth.py`'s in-memory `Company` store without bound, and each signup mints a fresh
  API key that unlocks the endpoint below.
- `POST /company/verify/bulk` (`BULK_VERIFY_LIMIT = 3`) — creates up to 50 sessions per call
  (`BulkVerifyRequest.max_length`) and never touched `SESSION_CREATE_LIMIT`'s bucket at all, so
  repeated calls had no backstop whatsoever. Deliberately a **call-count** bucket, not scaled
  per-session-created: reusing the 10/hour `SESSION_CREATE_LIMIT` bucket per session would make a
  single legitimate 50-candidate bulk call impossible on its own. This bucket instead caps repeated
  *calls* (worst case ~150 sessions/hour/IP), independent of the plain `/sessions` bucket.

Still open, not yet done: confirming live (not just via code read) that Phala's ingress actually
sets `X-Forwarded-For` — the existing docstring caveat above is unverified against a real
deployment; and confirming the Anthropic API key itself has a console-level spend cap set, which is
the backstop of last resort regardless of any bug in this file.

---

## Live Transcript, Post-Creation Opt-In, and Package-Mode Sync Fix

Three fixes to the agentic negotiation flow, requested together after live testing on the deployed
app surfaced real UX/correctness gaps — none were "wrong output" bugs, but all three left a party
watching a live negotiation with a confusing or stuck-looking screen.

**Round-value exposure boundary (`Session.agentic_mode_started_round`).** `SessionView.history`
(`RoundSummary`) used to strip `value` unconditionally, even for agentic-mode sessions, so a party
polling never saw the actual offer amounts the AI agents exchanged — even though those amounts already
legitimately cross the agent boundary per `offercheck_phase2_spec.md`'s own contract. Fixed by adding
`RoundSummary.value: float | None`. The exposure condition is deliberately more precise than just
`session.agentic_mode`: since a session can now pick up agentic mode *after* some human-driven rounds
already happened (via the opt-in fix below), a round a human made under the base flow's non-negotiable
gap%-only privacy contract must not retroactively become visible just because the session later
switches to AI. `Session.agentic_mode_started_round` (set once in `mediator.py`, at the top of
`run_agentic_negotiation()`, to `session.round_number + 1` — i.e. the first round number this call
will actually add) is that boundary; `_view_for()` only exposes `value` for rounds at or after it.
Package-mode rounds don't need this boundary at all — package negotiation is agentic-only by
construction (no human package-move endpoint exists anywhere in this vertical), so `PackageRoundDetail`
/ `SessionView.package_history` expose `package`/`total_comp` unconditionally.

**Post-creation agentic opt-in (`PATCH .../candidate/enable-agentic`, `PATCH .../employer/enable-agentic`).**
The original design only allowed sealing `candidate_floor`/`employer_authority_limit` at the one-shot
`POST /sessions` / `POST .../employer/band` moment — no way to opt in afterward. Fixed with two new
endpoints, callable any time before the session is terminal: single-set (409 if already sealed, same
"sealed" contract as the original creation-time fields), employer's variant additionally 412s if the
band isn't set yet (`employer_authority_limit` is meaningless without `band_max` to clamp against —
same precondition `mediator.build_agents()` already enforces at `start-agentic` time). A new
`SessionView.my_agentic_sealed: bool` field (viewer-scoped: `candidate_floor is not None` for the
candidate, `employer_authority_limit is not None` for the employer) lets the frontend show/hide its own
"Enable AI negotiation" button correctly, including across page reloads. The creation-time checkboxes
were removed from `CandidateNew.jsx` and `EmployerSession.jsx`'s band form; both session-view pages now
render an inline opt-in form gated on `!my_agentic_sealed`. **Scope note:** this covers the base scalar
floor/authority-limit opt-in only — full-package mode (Phase 2B) previously had its own opt-in nested
inside the same now-removed checkboxes and currently has no UI entry point at all. It's still fully
functional via the API and covered by tests (`test_offercheck_package.py`), just unreachable from
either session-view page until a package-mode opt-in modal is built — flagged, not silently dropped.

**Package-mode `SessionView` sync bug — the actual root cause of "employer shows waiting while
candidate has active buttons."** `apply_package_move()` (`app/offercheck/package.py`) only ever
mutates `session.package_state`/`package_round_number`, never the scalar `session.state` — by design,
package negotiation is a parallel state machine (see that module's docstring). But `SessionView` had
zero package-mode fields before this fix, so a party polling during/after a package AI negotiation saw
no progress at all: the scalar `state`/`turn`/`round_number` the frontend reads stayed frozen at
whatever they were before the package run started, even once package negotiation had already reached
`AGREED`. Fixed by adding `package_state`, `package_round_number`, `package_turn`, `package_history`,
and `package_agreed_package` to `SessionView` (`routes.py::_view_for`), and updating both
`CandidateSession.jsx` and `EmployerSession.jsx` to derive `isTerminal`/`myTurn` from the package
channel instead of the scalar one whenever `package_round_number > 0` — once package mode has actually
been used, it's the negotiation actually in progress for that session, and the scalar channel should be
treated as frozen/irrelevant from that point on.

Verified live against a running server (not just mocked `TestClient` tests): submitted a session
without sealing anything, PATCHed both `enable-agentic` endpoints, confirmed `agentic_ready` flipped
true with no sealed value ever appearing in any response body; confirmed a human-driven round's `value`
stays `null` to the other party even after that same session later runs agentic mode.

---

## Live 422 Fix, Package-Mode Opt-In Parity, Transcript UI Pass

**The 422 bug** (found from a real production screenshot): `start_agentic_route`/
`start_agentic_package_route` each had `body: AgenticStartRequest` (its own `token` field) *and* a
bare `token: str | None = None` function parameter — a same-name collision between a body field and
a query parameter. Production's error (`model_attributes_type`, "Input should be a valid dictionary
or object to extract fields from", `input` = the raw JSON-string body) is the textbook symptom of a
body resolving to a string instead of a parsed dict. Could not 100%-confirm root cause via
exact-version reproduction (this dev machine runs Python 3.14; `requirements.txt` pins
`pydantic==2.10.5`/`fastapi==0.115.6`, which has no prebuilt wheel for 3.14 — would need Python
3.11–3.13 to match production exactly). Fixed regardless by renaming to
`query_token: str | None = Query(default=None, alias="token")` — same external `?token=` contract,
zero internal ambiguity with `body.token`. Confirmed via grep that nothing in the frontend ever
actually sends `?token=` to either endpoint in practice (only the JSON body or `X-Demo-Token` header
are used) — the bare parameter was dead weight creating an unforced collision, so this was a safe fix
independent of whether it's the sole cause.

**That rename alone did not fix it** — the identical 422 reproduced again on the live app after that
fix was deployed. The bug never once reproduced in this codebase via pytest, `TestClient`, or direct
curl, only in the real browser-to-Phala round trip, which goes through a CORS preflight and a dstack
reverse proxy that none of those tools exercise — so the exact hop that re-wraps the body as a JSON
string is still unconfirmed. Rather than keep guessing, `start_agentic_route`/
`start_agentic_package_route` no longer let FastAPI auto-inject `body: AgenticStartRequest` at all;
both now call `_parse_agentic_start_body(request)`, which reads the raw body and — if it comes back
as a string instead of a dict — decodes it a second time before validating. This makes the endpoint
correct regardless of where in the chain the double-encoding happens, without needing to isolate it.
Verified live: a curl request sending the *exact* double-encoded shape from the production error
(`json.dumps(json.dumps({"token": ...}))` as the raw body) now completes a real negotiation instead
of 422ing. Locked in with `test_start_agentic_tolerates_a_double_json_encoded_body` in both
`tests/test_offercheck_agentic.py` and `tests/test_offercheck_package.py`.

**Package-mode opt-in parity** (`PATCH .../candidate/enable-agentic-package`, `PATCH
.../employer/enable-agentic-package`) — genuinely new endpoints, not just UI wiring, despite the
request describing it as "no new backend work needed." `package_agentic_ready` depends on
`candidate_package_ask` (a full package object) which the scalar `enable-agentic` endpoints never
touch, so reusing them literally couldn't have worked. The candidate endpoint asks the UI for one
number (`candidate_total_comp_floor`) and synthesizes `candidate_package_ask` server-side from the
already-known `candidate_ask` as `base` plus neutral defaults (`_DEFAULT_PACKAGE_TERMS` in
`routes.py`) for every other term. The employer endpoint needs no synthesis — `PackageEmployerAgent`
only needs `band_min`/`band_mid`/`band_max` (already set) plus the one new number,
`employer_total_comp_budget`. Both follow the same single-set/409/412 discipline as the scalar
endpoints. `SessionView.my_package_agentic_sealed` (viewer-scoped, mirrors `my_agentic_sealed`) lets
each side's button hide itself once sealed.

**Full transcript UI pass**: `RoundHistory` (chat-bubble — own moves right/teal, other party's
left/grey, monospace) and `PackageRoundHistory` (the existing per-term comparison table, now reused
for the *live* polled view, not just a just-completed result) replace the old plain-text round list
in both session-view pages. `SessionView.package_converged_hint` reuses `package.is_converged()`/
`total_comp_value()` — the same functions already feeding the agents' own prompts — to surface
"within 2% of total comp — consider accepting" to the human UI too. `AgenticPanel`/
`PackageAgenticPanel` now take `view` as a prop so the "Agents negotiating…" button shows a live
round counter + spinner during the blocking call — real progress, since the mediator mutates session
state each round and the independent polling loop keeps picking it up. Poll interval: 3000ms → 1500ms.

**Demo-link sync fix**: an employer opening a candidate's shared link during a solo demo run saw a
blank band form requiring a second, disconnected "Load demo data" click. The employer's band still
can't be auto-filled from the candidate's real numbers (core privacy mechanic — gap% would always be
0 otherwise), but for the demo-convenience path specifically: `CandidateNew.jsx` tags the generated
employer link with `&demo=1` when demo data was used; `EmployerSession.jsx` detects the flag and
auto-prefills (never auto-submits) the same independent demo band on load.

---

## Employer-Initiated Invites

Every prior Offer Check flow started with the candidate calling `POST /sessions`. This adds the
mirror image: an authenticated company (Phase 3 API key) opens a negotiation with
`POST /employer/new` before any candidate exists, gets back a shareable
`/offercheck/candidate/join/{invite_id}` link, and the candidate claims it later with
`POST /candidate/join/{invite_id}` — the same negotiation, just initiated from the other side.

**`app/offercheck/invites.py` is a fourth independent in-memory store**, alongside `store.py`'s
`Session` and `auth.py`'s `Company` — same no-DB, lost-on-restart precedent as everything else in
this vertical. An `EmployerInvite` is a *pending* record only: `id`, `company_id`,
`band_min`/`band_mid`/`band_max`, optional `requirements` (free text, shown only on the employer's
own dashboard, never to the candidate), optional `ats_candidate_ref`/`employer_authority_limit`/
`employer_priorities` (Phase 2A agentic pass-through), `status` (`PENDING_CANDIDATE` / `CLAIMED`),
and `session_id` (set once claimed).

**`store.create_session()` still runs exactly once, at claim time, and nothing about the state
machine changes.** `POST /candidate/join/{invite_id}` (`routes.py::join_invite_route`) calls
`store.create_session()` with the identical signature `POST /sessions` uses, just sourcing
`company_id`/`ats_candidate_ref`/`employer_authority_limit`/`employer_priorities` from the invite
instead of an `X-API-Key` header, then immediately calls the existing, unmodified
`negotiation.set_employer_band()` with the invite's band. That function only sets
`band_min`/`band_mid`/`band_max`/`band_set` — it does not touch `session.state` (state stays
`PENDING_EMPLOYER`, turn stays `"employer"`, exactly as it does when a human employer calls
`POST .../employer/band` by hand). The employer still has to make their own first actual move
(counter/accept/walk) — the invite only pre-seals the band, it doesn't pre-play a turn. This is
why `negotiation.py`, `store.py`'s `Session` dataclass, `app/tee/attestation.py`, and
`app/offercheck/agents/mediator.py` needed zero changes for this feature — the invite flow is
pure composition of existing public functions.

**`GET /employer/invite/{id}` is gated by the owning company's `X-API-Key`, not just the
`invite_id`** — once `CLAIMED`, it returns the session's `employer_token`, which is exactly what
`POST /sessions` hands the candidate directly for the employer side in the base flow. Requiring
the API key here (rather than treating the invite id as a bearer credential) keeps that token from
leaking to anyone who merely guesses or is handed the invite id.

**Not built, out of scope for this pass** (per the originating request's own explicit scope cut):
invite expiry, an employer-side "cancel this invite" action, and a "list my open invitations"
view. `GET /company/sessions` already lists claimed sessions once they exist; there is currently no
way to see *unclaimed* invites in the dashboard UI (the API (`GET /employer/invite/{id}`) supports
checking one invite at a time, given its id — `CompanyNew.jsx` uses exactly that after creating an
invite). Flagging these as real gaps, not silently dropped, if a future pass wants them.

---

## Offer Check Session UX — Attestation-First Gating, Human Decision Trace, Stage Spine, Spotlighted Next Action, Width Normalization

Five passes, requested and built in sequence. All frontend-only — confirmed via `git diff --stat`
after every single one of them that nothing under `app/` changed; every fix consumed endpoints and
`SessionView` fields that already existed.

**Attestation-first input gating**, ported from the "verify, then release" TEE UX pattern first
built for Dev Credential's `Setup.jsx` (DC-5). Both `CandidateSession.jsx` and `EmployerSession.jsx`
fetch `GET /api/attest` once on mount and disable every sensitive input (GitHub token, sealed
floor/authority-limit/budget) until it resolves, wrapped in an emerald "Inside the TEE" boundary
with `Intel TDX`/`DCAP verified` pills (`TeeInputBoundary`, `EnclaveStatusNote`, duplicated per file
per this vertical's established mirroring convention). **This deliberately does not reuse
`offercheckGetAttestation(sessionId, token)`** — that endpoint 409s until the session is terminal
(see "Offer Check Architecture" above), so gating a pre-negotiation input on it would permanently
lock the form before the negotiation that would resolve it has even happened. `getEnclaveAttestation()`
(`api.js`) wraps the *enclave-level* `GET /api/attest` instead — the same call core DealProof's own
docstring already calls "the first call a client makes... before sending any sensitive payload." The
existing post-terminal `AttestationPanel` (the session/negotiation receipt) is untouched.

Devcred's `Setup.jsx` got the same gating plus a redpill.ai-style **Verification Center**: a
collapsed `✓ TDX Verified` pill expands into an attestor row, three claim rows, an expandable raw-
evidence section (quote hex / MRENCLAVE / timestamp / a copy-pasteable curl command, all sourced
from `GET /api/attest`'s existing response shape — no backend change needed), and a "Verify Again"
button that re-fires the same call.

**Human decision trace.** `RoundHistory`'s chat-bubble trace used to end on the last agent move with
no acknowledgement of the human approval-gate outcome. Both files now append a "You · your decision"
bubble (amber, visually distinct from the teal/grey agent-move bubbles) once the viewer's own
`my_approval_vote`/`my_package_approval_vote` is set, plus a second, neutral-grey fallback bubble for
the case where the *other* party's unilateral decline resolved the session before the viewer ever
got a turn to vote. `negotiation.py::_resolve_approval()` short-circuits straight to `DECLINED` on a
single decline vote without waiting for the other side — confirmed via a live `TestClient` run
against the real backend (both parties' `SessionView` inspected directly), not assumed, before
either bubble shipped.

**`HowThisWorksStrip`** — a dismissible, jargon-free 5-line orientation strip at the top of each
page, local `useState` only, no persistence. Purely additive: doesn't touch panel order, copy
elsewhere on the page, or any `visible` condition.

**Stage spine + spotlighted next action** (`getNextAction()` / `getStageStatuses()` / `StageSpine` /
`ActionPanels`) replaced "show every applicable panel at once" with three complementary mechanisms:
a 5-stage tracker (`Verify → Choose mode → Negotiating → Decision → Proof`, with a "skip" visual
state for sessions where Verify never applies), one spotlighted recommended action, and an "Other
options" disclosure for everything else currently visible. **`getNextAction()` consumes the
component's own already-derived `isTerminal`/`pendingApproval`/`myTurn`/`packageActive` — it must
never re-derive that logic**, or the spotlight can silently disagree with which panels are actually
shown per the real `packageActive` hand-off rules. Its priority order was simulated against concrete
state objects (not just read) before shipping, which caught a real bug: gating "choose a negotiation
mode" on "have I sealed a track" alone meant a fully-manual respondent got told to "choose" forever,
even mid-turn, since a manual negotiator never seals anything — fixed by gating on
`negotiationStarted` (any round history at all, from either party) instead.

`ActionPanels` renders every item from **one stable, always-mounted, keyed list — never
conditionally re-parented between a spotlight wrapper and a collapsed section.** An earlier draft
did the latter; React remounts a component whose position in the tree changes between renders,
which would have silently discarded an in-progress typed floor value the instant a background poll
(every 1.5s) changed the recommendation. Only `className` (and an optional title in its own fixed
sibling slot) changes between spotlighted / collapsed-behind-toggle / hidden.

**Regression, caught and fixed after shipping — `collapsible` is a required field on every
`ActionPanels` item, not optional.** The first version hid *any* non-spotlighted item behind the
"Other options" toggle by default, with no distinction between an unresolved choice and a completed
status — so the verified-GitHub-credential summary (and the employer's read-only
`ProvenanceStatusPanel`) vanished the instant `getNextAction()` recommended something else. Verifying
the bug report's own diagnosis before patching also caught a second, unreported instance of the same
class: `AgenticPanel`/`PackageAgenticPanel`'s post-run result would have disappeared the moment
`pendingApproval` superseded `runSalary`/`runPackage` as the priority — i.e., right when the user
most needs to see the negotiated outcome before approving it. Fixed by splitting every item that has
both an actionable and a persistent-status sub-state (verify form vs. verified summary; an
enable-agentic CTA vs. its "waiting for the other side" banner) into two separate `ActionPanels`
entries — only the actionable one is ever `collapsible: true`.

**Container width.** Every Offer Check page wrapper (`CandidateSession`, `EmployerSession`,
`CompanyNew`, `CompanyRegister`, `CandidateNew`, `CandidateJoin`, `Dashboard`'s three pre-auth gate
states, `Demo`) is `max-w-3xl` (768px), up from `max-w-lg`/`max-w-md` (512px/448px) — per
`docs/design/luxe/SKILL.md`'s own dashboard-vs-prose content-width guidance. `Landing.jsx`'s hero
paragraph keeps its own `max-w-lg` — that's a prose-measure line-length constraint inside an already-
narrower centered marketing layout, not a page wrapper, and was confirmed as such by reading the
surrounding JSX (not assumed) before being left alone.

**Not verified in a live browser** for any of this — no Playwright/chromium available in this dev
environment, and installing one mid-task was judged a disproportionate detour. Verified instead via:
production build cleanliness (`npm run build`) after every change, `getNextAction()` priority-logic
simulation against concrete state objects covering every documented scenario plus edge cases found
along the way, and real backend `TestClient` calls to confirm `SessionView` field names/shapes
(`history[].actor`, `require_provenance_credential`, `my_agentic_sealed`, etc.) actually match what
the frontend reads. An actual cold click-through (Tina's original office-hours suggestion) is still
recommended before Demo Day.

---

## Deployment Notes

**`docker-compose.phala.yml` is gitignored** — it contains production env var placeholders and must not be committed. The file lives only on disk and is uploaded manually to the Phala dashboard. After any change, rebuild and push only the app image:
```
docker compose build app && docker compose push app
```
Memory service (`kkoci/dealproof-memory`) is unchanged — push only when `memory-service/` changes.

---

## What NOT to Build

- **Negotiation transcript Merkle tree** — rejected. TDX quote over final state is sufficient.
  Props Merkle (`app/props/verifier.py`) is different and stays.
- **TEE Postgres** — SQLite is inside the CVM trust boundary. A remote attested DB adds
  complexity with no security gain at current scale.
- **Fancy frontend before backend is complete** — frontend is lowest priority.
  Sequencing: piCreds locally → deploy to CVM → frontend last.

---

## Workflow Rules

### On every feature or fix

1. Write or update tests for the changed behaviour — run `pytest` and confirm 0 failures.
2. Run `pytest tests/ -v` before marking anything done.
3. Update the relevant section of `README.md` if phase status or test count changes.
4. Never break the resilience guarantees (memory/πCreds/DKIM/Auditor/Arbitrator all non-fatal).

### On errors

Note the root cause and fix in a comment or commit message. Keep `app/tee/` and
`app/memory/` changes conservative — these touch the attestation chain.

### On attestation changes

Any change to what goes into `report_data` (the SHA-256 payload sent to tappd) must update:
- `app/tee/attestation.py` — the hash construction
- `tests/test_tee.py` — the expected report_data
- `README.md` — the "What the TDX Quote Covers" section

---

## Test Payloads (PowerShell one-liners)

See **`PAYLOADS.md`** for the full reference: deal payloads, transcript ingest payloads,
and synthetic eval datasets (including the healthy-team / conflict-team corpora for Andrew).

Quick summary of what's in `PAYLOADS.md`:
- Standard deals (vision / medical / financial) with and without `seller_proof`
- Transcript ingest: `local`, `tinycloud`, and `direct` mode examples
- Real-transcript ingest: `rec-03bd0ce45a46ee5aa60175e1` (7 sentences, pre-hashed)
- Synthetic eval corpora: Eval 1 (healthy team), Eval 2 (conflict team), Eval 3 (summary-only),
  Eval 4 (mixed corpus stress test)
- End-to-end deal payloads using eval corpus roots as `data_hash`

Swagger UI: `http://localhost:8000/docs` → POST /api/deals/run → Try it out

All three payloads include `seller_proof` (activates `data_verification_attestation`).
`seller_email_eml` and escrow fields require real infrastructure and are not included here.

**Vision dataset**
```json
{
  "buyer_budget": 1000.0,
  "buyer_requirements": "10 GB COCO-style labelled image dataset for CV fine-tuning, min 500k images, 80 categories",
  "data_description": "10 GB curated COCO dataset, 520k images, bounding boxes and segmentation masks, quality-verified 2024",
  "data_hash": "bab5be0d0c6bf806abc221e5b11ae1e1ce358a36caf475a12f01ba28c100cd7f",
  "floor_price": 600.0,
  "seller_proof": {
    "root_hash": "bab5be0d0c6bf806abc221e5b11ae1e1ce358a36caf475a12f01ba28c100cd7f",
    "chunk_hashes": [
      "cdf9022fcd89c33c678d3953ca5a91a5f33dfa34a65a2726f9eb4065c1e4359e",
      "bc49012e270cf0efccb1bc84d65a01a10b69c0240ffa5faa2d444e63cae2e6f3",
      "23bf3cabce281a9f6a27b002861e55aca8cc7634d9f14bc42434ef43f7f61d16",
      "2b2c3dba6b61251fdb8e682c95025e7d2ad9787d15d8f3d8309c4540efffdd27",
      "8b7420713d60efa93a2d25f373b5a04d18bb3f70c93d266a961c77d3170f6012"
    ],
    "chunk_count": 5,
    "algorithm": "sha256"
  }
}
```

**Medical imaging**
```json
{
  "buyer_budget": 1200.0,
  "buyer_requirements": "10 GB DICOM medical imaging dataset for radiology AI, fully de-identified, HIPAA compliant, radiologist labels",
  "data_description": "10 GB de-identified DICOM dataset, 12000 studies chest/abdomen/brain MRI, double-blind radiologist labels, IRB-cleared 2024",
  "data_hash": "09f269cc45fd0121ecc5053f2bfc501715612d46bb4a673a22f7bde4ac770b87",
  "floor_price": 800.0,
  "seller_proof": {
    "root_hash": "09f269cc45fd0121ecc5053f2bfc501715612d46bb4a673a22f7bde4ac770b87",
    "chunk_hashes": [
      "956ef9a27e28823411fba7928ba0ad965a1488cb79e85f98093b94b6ea40f7ca",
      "4296bc42d027c79b78c2e9d133a3fd2295a80f9fcbcd61128b958be943227b44",
      "1926ec265e3c7efb9333dde8ef35478e9e7ba6e59d41ad469a99c0d248dc95cb",
      "010e38f35867157bfed572fb2744876b2c5b84500024485b9f7b6c800a3a0675",
      "3e8f0a0a77655beedd828bad7872f81ec28885bc5b0e38242e0d6497075f4775"
    ],
    "chunk_count": 5,
    "algorithm": "sha256"
  }
}
```

**Financial data — tight margin, arbitration likely on deadlock**
```json
{
  "buyer_budget": 560.0,
  "buyer_requirements": "5-year tick-by-tick FX data for quant model, EUR/USD and GBP/USD, bid/ask spread included",
  "data_description": "5-year FX tick data 2019-2024, 8 major pairs, level-2 order book, 2.1B rows, Tier-1 prime broker feed",
  "data_hash": "d3923cfa91f05d890dca0d9ec43d3b12f15dc22af586f60c53e2d24df68e2192",
  "floor_price": 500.0,
  "seller_proof": {
    "root_hash": "d3923cfa91f05d890dca0d9ec43d3b12f15dc22af586f60c53e2d24df68e2192",
    "chunk_hashes": [
      "55390a7df2151cf46a5f910a76777ab22a3b6d80f2aa9aab65c0c917e16eeed9",
      "9db68cbd4a100bf4b3a858e3a0bd206caa3036037dccb269ea35a24b34bbc557",
      "3a305e2fce951c2875f1319f277c08141ad20ca022c389994fb3b875817d0dcd",
      "1c97f34657872bc9d6fd5c3c38f695cf891f027c173191206ec3f60c93eb58bf",
      "417aaf6b45bbabebfeed588f2d1f6dafa5ed48b5082d68d8f0b6ecb140168143"
    ],
    "chunk_count": 5,
    "algorithm": "sha256"
  }
}
```

**Vision — standard agreement**
```json
{
  "buyer_budget": 1000.0,
  "buyer_requirements": "10 GB COCO-style labelled image dataset for CV fine-tuning, min 500k images, 80 categories",
  "data_description": "10 GB curated COCO dataset, 520k images, bounding boxes and segmentation masks, quality-verified 2024",
  "data_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "floor_price": 600.0
}
```

**Financial — tight margin, arbitration likely if agents deadlock**
```json
{
  "buyer_budget": 560.0,
  "buyer_requirements": "5-year tick-by-tick FX data for quant model, EUR/USD and GBP/USD, bid/ask spread included",
  "data_description": "5-year FX tick data 2019-2024, 8 major pairs, level-2 order book, 2.1B rows, Tier-1 prime broker feed",
  "data_hash": "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
  "floor_price": 500.0
}
```

**Medical — high-value, multi-round negotiation expected**
```json
{
  "buyer_budget": 1200.0,
  "buyer_requirements": "10 GB DICOM medical imaging dataset for radiology AI, fully de-identified, HIPAA compliant, radiologist labels",
  "data_description": "10 GB de-identified DICOM dataset, 12000 studies chest/abdomen/brain MRI, double-blind radiologist labels, IRB-cleared 2024",
  "data_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "floor_price": 800.0
}
```

**PowerShell one-liners**

**Vision dataset — standard agreement**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":1000.0,"buyer_requirements":"10 GB COCO-style labelled image dataset for CV fine-tuning, min 500k images, 80 categories","data_description":"10 GB curated COCO dataset, 520k images, bounding boxes and segmentation masks, quality-verified 2024","data_hash":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","floor_price":600.0}'
```

**Financial data — tight margin, arbitration likely if agents deadlock**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":560.0,"buyer_requirements":"5-year tick-by-tick FX data for quant model, EUR/USD and GBP/USD, bid/ask spread included","data_description":"5-year FX tick data 2019-2024, 8 major pairs, level-2 order book, 2.1B rows, Tier-1 prime broker feed","data_hash":"a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3","floor_price":500.0}'
```

**Medical imaging — high-value, multi-round negotiation expected**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":1200.0,"buyer_requirements":"10 GB DICOM medical imaging dataset for radiology AI, fully de-identified, HIPAA compliant, radiologist labels","data_description":"10 GB de-identified DICOM dataset, 12000 studies chest/abdomen/brain MRI, double-blind radiologist labels, IRB-cleared 2024","data_hash":"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824","floor_price":800.0}'
```

---

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/status` | Current phase, test count, what's next |
| `/flow` | Print the full _negotiate_deal() step sequence |
| `/attest` | Explain the full attestation chain (TDX + memory + πCreds) |
| `/test` | Run `pytest tests/ -v` and report failures |
| `/verify` | Cross-check implementation against README phase status |

---

## Research Papers

| Paper | URL |
|-------|-----|
| πCreds (Behavioral Integrity Credentials) | https://arxiv.org/pdf/2606.03771 |
| Props (Data Provenance) | https://arxiv.org/pdf/2410.20522 |
| NDAI (Negotiated Data Access) | https://arxiv.org/pdf/2502.07924 |


---

## Working style
- Do not ask clarifying questions before starting work
- Make reasonable assumptions and state them inline
- Only ask if genuinely blocked with no reasonable assumption available
- Prefer action over confirmation
