# DealProof — Claude Code Guide

## Project

**DealProof** is a verifiable AI negotiation system. Two Claude Sonnet agents (buyer + seller)
negotiate a data deal entirely inside an Intel TDX Trusted Execution Environment on Phala Cloud.
When they agree, the CPU produces a cryptographic DCAP attestation quote — hardware-signed proof
that neither agent cheated, the data was what the seller claimed, and the deal terms are tamper-proof.

Trust stack: TDX enclave (environment) → DCAP attestation (code) → Contexto memory (attested
inputs) → πCreds behavioral credentials (attested conduct).

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
| Data provenance | Props-inspired Merkle root verification |
| Seller identity | DKIM email proof — `dkimpy` + DNS-over-HTTPS |
| Attested memory | Contexto `@ekai/memory` sidecar (port 4011) |
| πCreds | LLM-inferred policy + conduct credentials |
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

Step M1  Contexto memory pre-deal
           search_memories() → inject context into agent prompts
           get_memory_hash() → memory_hash (state A)

Step 3   Negotiation loop
           BuyerAgent ↔ SellerAgent (AsyncAnthropic)

Step M2  (if agreed) Contexto memory post-deal
           add_memories() for both agents
           get_memory_hash() → memory_hash_post (state B)

Step P   (if agreed) πCreds audit
           audit_agent_policy() × 2
           audit_deal_conduct()
           hash_credentials() → picreds_hash
           Re-attest: SHA-256(deal + hashA + hashB + picreds_hash) → TDX quote

Step 3b  (if agreed) On-chain escrow release

Step 4   Persist DealResult to SQLite, return response
```

Props verification runs BEFORE the negotiation loop. Memory is split: recall before,
store after. πCreds and post-deal memory only run on agreement.

---

## Key Files

```
app/api/routes.py          All HTTP endpoints + full _negotiate_deal() orchestration
app/api/schemas.py         DealCreate, DealResult, PiCred Pydantic models
app/agents/buyer.py        BuyerAgent (claude-sonnet-4-6)
app/agents/seller.py       SellerAgent (claude-sonnet-4-6, accepts verified_domain)
app/agents/negotiation.py  run_negotiation() loop + first-pass sign_result()
app/tee/attestation.py     sign_result() → POST /prpc/Tappd.TdxQuote
app/tee/dcap.py            TDX quote header parser (Phase 7)
app/props/verifier.py      Props Merkle verification
app/dkim/verifier.py       DKIM email proof (dkimpy + DoH)
app/memory/client.py       Contexto sidecar client (search, add, get_memory_hash)
app/picreds/auditor.py     LLM audit: audit_agent_policy(), audit_deal_conduct()
app/picreds/credential.py  make_credential(), hash_credentials()
demo.py                    CLI demo — prints transcript + attestations + memory + πCreds
memory-service/            Contexto @ekai/memory sidecar (Node.js, port 4011)
frontend/                  React 18 + Vite 5 + Tailwind (outdated — rebuild pending)
```

---

## DealResult Response Fields

```
attestation                   TDX quote (re-attested after πCreds if agreed)
data_verification_attestation TDX quote from Props verification
dkim_verification             {domain, verified, dns_unavailable, error} or null
memory_hash                   pre-deal buyer:seller hash (state A)
memory_hash_post              post-deal buyer:seller hash (state B)
memory_attested               bool
picreds                       list[DealProofCredential] — policy×2, conduct×1
picreds_hash                  SHA-256 of all credentials, embedded in TDX report_data
picreds_attested              bool
transcript                    list of negotiation rounds
```

---

## Test Suite (95 tests — all pass without Docker or tappd)

```
tests/test_agents.py          3   BuyerAgent + SellerAgent unit tests
tests/test_negotiation.py     4   Negotiation loop, combined attestation payload
tests/test_tee.py            10   KMS + TDX quote HTTP calls + GET /api/attest
tests/test_props.py          23   Props verifier: helpers + failure paths + route gate
tests/test_dkim_verifier.py  19   DKIM: parsing + DNS-over-HTTPS + verification paths
tests/test_memory.py          4   Contexto client: add, search, hash, sidecar-down
tests/test_picreds.py        11   πCreds: constraint checks (5 pure) + auditor + credentials + failure
tests/test_e2e.py            13   Full HTTP stack end-to-end (TestClient + mocks)
tests/test_contract.py        8   Phase 4 escrow: create/complete/refund
```

**Resilience guarantees:**
- Memory sidecar down → deal proceeds, `memory_attested: false`
- πCreds audit fails → deal proceeds, `picreds: null`, `picreds_attested: false`
- DKIM fails → deal proceeds, `dkim_verification.verified: false`

Run tests: `pytest tests/ -v` (no Docker, no tappd required)

---

## Phase Status

| Phase | What | Status |
|-------|------|--------|
| 1–6 | Scaffold, TEE, Props, escrow, polish, DKIM + React frontend | ✅ Complete |
| 7 | DCAP quote parsing — header done; on-chain verifier contract pending | 🔄 Partial |
| 8 | Contexto attested memory — sidecar + memory_hash A→B in TDX quote | ✅ Complete |
| 9 | πCreds — LLM policy + conduct credentials attested in TDX quote | ✅ Complete |

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

1. Write or update tests for the changed behaviour — all 90 must still pass.
2. Run `pytest tests/ -v` before marking anything done.
3. Update the relevant section of `README.md` if phase status or test count changes.
4. Never break the resilience guarantees (memory/πCreds/DKIM all non-fatal).

### On errors

Note the root cause and fix in a comment or commit message. Keep `app/tee/` and
`app/memory/` changes conservative — these touch the attestation chain.

### On attestation changes

Any change to what goes into `report_data` (the SHA-256 payload sent to tappd) must update:
- `app/tee/attestation.py` — the hash construction
- `tests/test_tee.py` — the expected report_data
- `README.md` — the "What the TDX Quote Covers" section

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
