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
app/dkim/verifier.py       DKIM email proof (dkimpy + DoH)
app/memory/client.py       Contexto sidecar client (search, add, get_memory_hash)
app/picreds/auditor.py     LLM audit: audit_agent_policy(), audit_deal_conduct()
app/picreds/constraints.py Deterministic constraint checks (no LLM) — authoritative booleans
app/picreds/credential.py  make_credential(), hash_credentials()
demo.py                    CLI demo — transcript + attestations + memory + πCreds + auditor + arbitrator
memory-service/            Contexto @ekai/memory sidecar (Node.js, port 4011)
frontend/                  React 18 + Vite 5 + Tailwind (outdated — rebuild pending)

--- Offer Check vertical (vertical/hr-offer-check branch) — see build_spec_offer_check.md
    and offercheck_phase2_spec.md (agentic layer — different numbering scheme, see README) ---
app/offercheck/schemas.py     CompetingOffer, ConsistencyCheck, SessionView, AttestationReceipt, DcapVerification, OfferLetterExtraction, Company/Bulk/Credential/Agentic schemas
app/offercheck/verifier.py    check_consistency() — software-only plausibility check, no LLM/TEE
app/offercheck/negotiation.py Pure state machine + attestation hashing: apply_move(), attested_terms(), competing_offer_hash()
app/offercheck/store.py       In-memory Session store (no DB, no auth beyond opaque tokens) — company_id/credential/attestation/candidate_floor/employer_authority_limit fields
app/offercheck/auth.py        In-memory Company store (Phase 3) — register_company(), get_company_by_api_key(), connect_ats()
app/offercheck/credential.py  OfferVerifiedCredential — deterministic capitulation/convergence checks, no LLM (mirrors app/picreds/constraints.py)
app/offercheck/billing.py     Pricing tiers (individual/team/growth/enterprise) + record_verification_usage() (StripeNotConfigured-gated)
app/offercheck/parsing.py     PDF offer-letter parsing (Phase 2) — pypdf text extraction + Claude field extraction
app/offercheck/integrations/  greenhouse.py, lever.py (outbound notify + HMAC webhook verify), workday.py (deliberate stub)
app/offercheck/agents/        candidate_agent.py, employer_agent.py (mirror app/agents/buyer.py, seller.py), mediator.py (mirrors app/agents/negotiation.py)
app/offercheck/demo_auth.py   Magic-link auth — stateless HMAC tokens, single-use consumption, per-session spend cap, startup fail-fast
app/offercheck/routes.py      POST /api/offercheck/sessions, /parse-offer-letter, /employer/band, /employer/move, /candidate/move, /company/register,
                               /company/ats-connect, /company/verify/bulk, /integrations/{provider}/webhook/{company_id}, /sessions/{id}/start-agentic,
                               /auth/demo-link; GET /sessions/{id}, /attest, /dcap-verify, /credential, /company/sessions, /auth/verify
frontend/src/pages/offercheck/  Landing, CandidateNew (+ PDF upload + AI-negotiation floor), CandidateSession, EmployerSession, Demo (magic-link spectator view)
                                 (+ attestation/credential panel + agentic panel), CompanyRegister, Dashboard
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

## Test Suite (215 passed, 2 skipped — run with `pytest`, no Docker or tappd required)

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
tests/test_offercheck.py     29   Offer Check: consistency checks, revision-loop state machine, privacy, attestation, PDF parsing, HTTP e2e
tests/test_offercheck_phase3.py 34   Offer Check: company auth, credential, billing, ATS integrations, bulk verify, webhooks, HTTP e2e
tests/test_offercheck_agentic.py 13  Offer Check: CandidateAgent/EmployerAgent clamps, mediator convergence, reasoning-never-crosses-boundary, HTTP e2e
tests/test_offercheck_demo_auth.py 23  Offer Check: HMAC token roundtrip/tamper/expiry, single-use, spend cap, demo-link + verify + gated start-agentic HTTP e2e
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
| OC-P6 | Agentic Phase 2B — full compensation package negotiation | 🔜 Pending |
| OC-P7 | Agentic Phase 2C — real Phala Cloud TDX deployment for the agent loop (currently: simulation-mode reasoning, same as the rest of this vertical) | 🔜 Pending |
| OC-P8 | Magic-link auth — gates every Claude-calling endpoint, single-use tokens, spend cap, startup fail-fast | ✅ Complete |

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
