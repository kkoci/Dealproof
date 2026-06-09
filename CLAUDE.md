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
| Data provenance | Props-inspired Merkle root verification |
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
           Re-attest: SHA-256(deal + hashA + hashB + picreds_hash + audit_credential_hash) → TDX quote

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
app/tee/attestation.py     sign_result() → POST /prpc/Tappd.TdxQuote
app/tee/dcap.py            TDX quote header parser (Phase 7)
app/props/verifier.py      Props Merkle verification
app/dkim/verifier.py       DKIM email proof (dkimpy + DoH)
app/memory/client.py       Contexto sidecar client (search, add, get_memory_hash)
app/picreds/auditor.py     LLM audit: audit_agent_policy(), audit_deal_conduct()
app/picreds/constraints.py Deterministic constraint checks (no LLM) — authoritative booleans
app/picreds/credential.py  make_credential(), hash_credentials()
demo.py                    CLI demo — transcript + attestations + memory + πCreds + auditor + arbitrator
memory-service/            Contexto @ekai/memory sidecar (Node.js, port 4011)
frontend/                  React 18 + Vite 5 + Tailwind (outdated — rebuild pending)
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
audit_report                  {genuine_negotiation, monotonic_convergence, within_bounds,
                               round_count, final_price, summary, credential_hash} or null
arbitrated                    bool — true when ArbitratorAgent resolved a deadlock
memory_context_hash           SHA-256 of recalled memories injected into agent prompts
                               proves what the agents remembered, not just that state changed
memory_write_hash             SHA-256 of outcome_messages written to memory post-deal
                               proves this deal caused the A→B state transition
transcript                    list of negotiation rounds
```

---

## Test Suite (102 tests — all pass without Docker or tappd)

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
| 12 | DCAP on-chain verifier contract | 🔜 Next |

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
    genuine_negotiation: bool   # authentic back-and-forth vs scripted
    monotonic_convergence: bool # buyer up / seller down throughout
    within_bounds: bool         # final_price ∈ [floor_price, buyer_budget]
    round_count: int
    final_price: float
    summary: str                # one-sentence characterisation
    credential_hash: str        # SHA-256(fields, sort_keys=True) — in TDX report_data
```

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

1. Write or update tests for the changed behaviour — all 102 must still pass.
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

Three scenarios covering normal agreement, tight-margin negotiation (likely arbitration), and medical data.

Swagger UI: `http://localhost:8000/docs` → POST /api/deals/run → Try it out

**Vision — full payload (Props verification + all optional fields activated)**
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
Note: `data_hash` must equal `seller_proof.root_hash`. Root hash is `SHA-256(4-byte-length-prefix + concat(bytes(chunk_hash) for each chunk))`.

PowerShell one-liner (full payload with Props):
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":1000.0,"buyer_requirements":"10 GB COCO-style labelled image dataset for CV fine-tuning, min 500k images, 80 categories","data_description":"10 GB curated COCO dataset, 520k images, bounding boxes and segmentation masks, quality-verified 2024","data_hash":"bab5be0d0c6bf806abc221e5b11ae1e1ce358a36caf475a12f01ba28c100cd7f","floor_price":600.0,"seller_proof":{"root_hash":"bab5be0d0c6bf806abc221e5b11ae1e1ce358a36caf475a12f01ba28c100cd7f","chunk_hashes":["cdf9022fcd89c33c678d3953ca5a91a5f33dfa34a65a2726f9eb4065c1e4359e","bc49012e270cf0efccb1bc84d65a01a10b69c0240ffa5faa2d444e63cae2e6f3","23bf3cabce281a9f6a27b002861e55aca8cc7634d9f14bc42434ef43f7f61d16","2b2c3dba6b61251fdb8e682c95025e7d2ad9787d15d8f3d8309c4540efffdd27","8b7420713d60efa93a2d25f373b5a04d18bb3f70c93d266a961c77d3170f6012"],"chunk_count":5,"algorithm":"sha256"}}'
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
