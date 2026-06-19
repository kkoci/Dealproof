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

## Test Suite (69 passed, 2 skipped — run with `pytest`, no Docker or tappd required)

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

## Deal Room Product (`product/deal-room` branch)

**Do not change the backend attestation flow, πCreds logic, or agent behavior.**
The product wraps what exists; it does not replace it.

### Phase 1 — Auth + Room Creation ✅ Complete

New backend files:
- `app/api/room_routes.py` — `/api/room/*` endpoints (seller register, buyer register, status poll)
- `app/api/room_schemas.py` — `SellerRegisterRequest`, `BuyerRegisterRequest`, `RoomCreateResponse`, `BuyerJoinResponse`, `RoomStatusResponse`

New db functions in `app/db.py`:
- `create_deal_rooms_table()`, `create_room()`, `get_room()`, `update_room_buyer()`

New frontend files:
- `frontend/src/pages/LandingPage.jsx` — seller registration + hero
- `frontend/src/pages/WaitingRoom.jsx` — split panel, polls `/status` every 3s, buyer join flow
- `frontend/src/api/roomApi.js` — room API calls
- `frontend/src/hooks/useAuth.js` — localStorage token store keyed by room_id

Design system colors added to `tailwind.config.js`: `dp-bg`, `dp-surface`, `dp-border`, `dp-teal`, `dp-amber`, `dp-red`, `dp-text`, `dp-muted`.

Token strategy: 64-char hex random token, stored in `deal_rooms.seller_token` / `buyer_token`. Expiry 2h, checked client-side via `dp_auth_{room_id}` in localStorage.

Route split in `App.jsx`: new pages (`/`, `/room/:room_id`) are full-screen standalone layouts. Legacy pages (`/deals`, `/create`, `/deal/:id`) keep the old NavBar layout via `LegacyLayout` + `Outlet`.

**Stop after Phase 1 — wait for instructions before building Phase 2 (Deal Configuration).**

### Phase 2 — Deal Configuration ✅ Complete

New endpoints in `app/api/room_routes.py`:
- `PUT /api/room/{room_id}/config` — seller only (`X-Room-Token`); saves `deal_payload` JSON to DB, status → `configuring`
- `POST /api/room/{room_id}/confirm` — seller or buyer; sets `seller_confirmed`/`buyer_confirmed`; both set → status `confirmed`

`floor_price` is always stripped from `GET /api/room/{room_id}/status` response before it reaches the client. Only the backend holds the real floor price for DealCreate construction (Phase 3).

New db functions: `save_room_config()`, `confirm_room_participant()` (returns `(seller_confirmed, buyer_confirmed)` tuple). ALTER TABLE migrations added to `create_deal_rooms_table()` for Phase 1 installs.

New frontend page: `frontend/src/pages/DealConfig.jsx` at `/room/:room_id/config`.
- Seller: full form (dataset type, description, asking price, floor price, budget, requirements, quality expandable, escrow toggle) + Save + Confirm
- Buyer: read-only summary (no floor price) + Confirm
- WaitingRoom auto-redirects to this page when status ≥ `configuring`
- Both confirmed → status `confirmed` → placeholder for Phase 3 negotiation trigger

`roomApi.js` additions: `saveRoomConfig(roomId, token, config)`, `confirmRoom(roomId, token)`.

**Stop after Phase 2 — wait for instructions before building Phase 3 (Live Negotiation View).**

### Phase 3 — Live Negotiation View ✅ Complete

New endpoints in `app/api/room_routes.py`:
- `POST /api/room/{room_id}/start` — seller or buyer; atomic `confirmed → running` transition; creates deal record; fires `_negotiate_and_complete_room()` as `BackgroundTask`; idempotent (second caller returns existing `deal_id`)

New db functions in `app/db.py`:
- `start_room_deal(room_id, deal_id)` — `UPDATE WHERE status='confirmed'`, returns bool (True = first caller wins)
- `update_room_status(room_id, status)` — set room to `complete` or `failed` after negotiation background task finishes

`_negotiate_and_complete_room()` in `room_routes.py`:
- Builds `DealCreate` from stored `deal_payload`; uses SHA-256 of `data_description` as placeholder `data_hash`
- Calls `_negotiate_deal(deal_id, deal_create)` (imported from `routes.py`)
- Marks room `complete` or `failed`

`roomApi.js` addition: `startRoomDeal(roomId, token)`.

New frontend files:
- `frontend/src/pages/NegotiationView.jsx` — 3-panel layout (transcript · trust stack · quality panel)
  - On mount: GET room status → if `confirmed` call `/start` → get `deal_id`; if already `running` use room's `deal_id`
  - Polls `GET /api/deals/{dealId}/status` every 2s until `agreed` or `failed`
  - Transcript rows revealed 380ms apart, fade+slide in; live elapsed timer; agreed price banner on close
  - "View Credential →" button on agreement → `/room/:room_id/credential` (Phase 4)
- `frontend/src/components/TrustStackBar.jsx` — 4-layer fill bars (TDX · DCAP · CONTEXTO · πCREDS); `600ms ease` width transition
- `frontend/src/components/QualityPanel.jsx` — SVG radial ring (completeness %), per-column null rate bars, schema consistency badge

`App.jsx` addition: `/room/:room_id/negotiate` → `NegotiationView`.
`DealConfig.jsx` update: redirects to `/negotiate` when status in `[confirmed, running, complete]`.

**Stop after Phase 3 — wait for instructions before building Phase 4 (Credential Display + Download).**

### Phase 4 — Credential Display + Download ✅ Complete

New frontend page: `frontend/src/pages/CredentialView.jsx` at `/room/:room_id/credential`.

Data flow:
- `getRoomStatus(room_id)` → `deal_id`
- `getDealStatus(deal_id)` → full `DealResult`
- Renders credential card; handles loading/error/no-deal states gracefully

Credential card sections:
- Header: "✓ DEAL ATTESTED" badge, ARBITRATED/πCREDS tags, SHARE + DOWNLOAD JSON buttons
- Key metrics: agreed price, round count, genuine negotiation flag
- Auditor summary (if `audit_report.summary` present)
- πCREDS conduct: `buyer_budget_respected`, `seller_floor_respected`, `no_sudden_capitulation`, `convergence_pattern_valid` + assessment text (if conduct cred present)
- Data quality: completeness %, verdict, issues, quality_hash (if `data_quality_report` present)
- Attestation hashes: TDX QUOTE (with VERIFY link → `/api/deals/{id}/dcap-verify`), PICREDS HASH, MEMORY PRE/POST/CTX, DATA VERIFY — each with inline COPY button
- Blockchain badges: Hedera tx, escrow deposit/release tx (shown only if present)

Post-deal actions: "← Start a new deal", "Export for audit →" (JSON download).
`App.jsx`: added `/room/:room_id/credential` → `CredentialView`.

**Stop after Phase 4 — wait for instructions before building Phase 5 (Dataset Upload).**

### Phase 5 — Dataset Upload ✅ Complete

New backend endpoint in `app/api/room_routes.py`:
- `POST /api/room/{room_id}/dataset` — seller only; accepts `.csv`, `.json`, `.jsonl` up to 50 MB
  - `_chunk_and_hash()`: splits into 1 MB chunks → SHA-256 each → `compute_merkle_root()`
  - `_quality_preview()`: parses up to 10,000 rows → null rates, completeness, issues, verdict
  - Returns: `corpus_root`, `seller_proof`, `file_size_bytes`, `chunk_count`, `filename`, `quality_preview`
- Updated `POST /{room_id}/start`: uses `corpus_root` + `seller_proof` + `quality_metrics` from `deal_payload` if present; falls back to description-hash for no-upload path
- `DataQualityMetrics` now imported and constructed in `/start` from `quality_metrics` dict
- `python-multipart==0.0.32` added to `requirements.txt`

Schema changes in `app/api/room_schemas.py`:
- `DealConfigRequest` gains optional: `corpus_root: str | None`, `seller_proof: dict | None`, `quality_metrics: dict | None`

New `uploadDataset(roomId, token, file)` in `frontend/src/api/roomApi.js` (raw FormData fetch, no Content-Type header).

Frontend changes in `frontend/src/pages/DealConfig.jsx`:
- Added `DatasetUpload` component (above seller form): drag-and-drop zone, auto-upload on file select, quality preview display
- `SellerConfigForm` gains `uploadResult` state + `useEffect` that auto-enables quality toggle and pre-fills thresholds
- `handleSave` includes `corpus_root`, `seller_proof`, `quality_metrics` in the config payload
- No-upload path (no file) is fully unaffected
