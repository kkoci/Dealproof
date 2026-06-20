# DealProof

**Verifiable AI negotiation for private data access — powered by Claude + Phala TEE.**

Two AI agents (buyer and seller) negotiate a data deal entirely inside an Intel TDX Trusted Execution Environment. When they agree, the hardware produces a cryptographic attestation quote that proves: (1) the negotiation was private, (2) the data was what the seller claimed, and (3) the exact price and terms agreed. No one — not the platform, not the server operator, not an attacker — can tamper with the result.

---

## The Problem

Private dataset markets break on trust. A buyer cannot verify the data before paying. A seller cannot trust the buyer not to dispute the price after delivery. Any intermediary platform can manipulate the negotiation or lie about the outcome. Traditional escrow requires trusting a third party.

## The Solution

DealProof moves the entire negotiation into a hardware-secured enclave:

```
Buyer ──► AI Agent ──► TEE (Intel TDX) ◄── AI Agent ◄── Seller
                             │                     │
                    DKIM email proof       Seller identity
                    (verified domain       credential injected
                     inside TEE)           into agent context
                             │
                    Props data verification
                    (Merkle proof of dataset)
                             │
                    Contexto memory sidecar
                    (attested state A → B)
                             │
                    πCreds audit
                    (policy + conduct credentials)
                             │
                    TDX attestation quote
                    (hardware-signed proof)
                             │
                    DCAP quote parsing
                    (header + report_data)
                             │
                    On-chain escrow release
                    (DealProof.sol on Sepolia)
```

The TEE attestation is an Intel TDX quote verifiable by anyone against Intel's public certificate chain. It binds to the exact deal terms, data hash, memory state transition, and πCreds hash — if any of them differ, the quote is invalid.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    Phala Cloud CVM (Intel TDX)                     │
│                                                                    │
│  ┌─────────────┐    ┌──────────────────────────────────────────┐   │
│  │  FastAPI    │───►│  DKIM Verifier  (Step 0 — optional)      │   │
│  │  (uvicorn)  │    │  verify_email_proof() via DoH 1.1.1.1    │   │
│  └─────────────┘    │  verified_domain → SellerAgent prompt    │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │                           │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │  Props Verifier  (Step 1 — optional)     │   │
│         │           │  compute_merkle_root(chunk_hashes)        │   │
│         │           │  → data_verification_attestation (TDX)   │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │                           │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │  Contexto Memory — pre-deal (port 4011)  │   │
│         │           │  search_memories() → inject into agents  │   │
│         │           │  get_memory_hash() → hash A              │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ context + hash A          │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │         Negotiation Loop                 │   │
│         │           │  BuyerAgent  ◄──────►  SellerAgent       │   │
│         │           │  (AsyncAnthropic)    (AsyncAnthropic)    │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ agreed                    │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │  Contexto Memory — post-deal (if agreed) │   │
│         │           │  add_memories() → store outcome          │   │
│         │           │  get_memory_hash() → hash B              │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ hash A → B                │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │  πCreds Auditor  (if agreed)             │   │
│         │           │  audit_agent_policy() × 2               │   │
│         │           │  audit_deal_conduct()                    │   │
│         │           │  hash_credentials() → picreds_hash       │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ picreds_hash              │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │  TEE Attestation  (if agreed)            │   │
│         │           │  tappd: POST /prpc/Tappd.TdxQuote        │   │
│         │           │  report_data = SHA-256(                  │   │
│         │           │    deal + hashA + hashB + picreds_hash   │   │
│         │           │    + audit_hash + ctx_hash + write_hash) │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ TDX quote                 │
│  ┌──────▼──────┐    ┌──────────────────▼───────────────────────┐   │
│  │  SQLite     │◄───│         DealResult                       │   │
│  │  (aiosqlite)│    │  attestation + data_verification_att     │   │
│  └─────────────┘    │  memory_hash (A) + memory_hash_post (B)  │   │
│                     │  picreds + picreds_hash                  │   │
│                     │  memory_context_hash + memory_write_hash │   │
│                     └──────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
         │
         │ (Phase 4)
         ▼
┌────────────────────┐
│  DealProof.sol     │
│  Sepolia testnet   │
│  escrow + release  │
└────────────────────┘
```

### Stack

| Layer | Technology |
|-------|-----------|
| AI agents | Claude claude-sonnet-4-6 via `anthropic.AsyncAnthropic` |
| TEE runtime | Phala Cloud CVM (Intel TDX) |
| TEE attestation | dstack tappd — `POST /prpc/Tappd.TdxQuote` |
| Data provenance | Props-inspired Merkle root verification + transcript corpus hashing |
| Seller identity | DKIM email proof — `dkimpy` + DNS-over-HTTPS (Phase 6) |
| DCAP inspection | TDX quote header parser — `app/tee/dcap.py` (Phase 7) |
| Attested memory | Contexto `@ekai/memory` sidecar (Phase 8) |
| πCreds | LLM-inferred policy + conduct credentials (Phase 9) |
| Auditor agent | Read-only TEE compliance witness |
| Arbitrator agent | Deadlock resolver — price clamped to [floor, budget] |
| TinyCloud | Listen transcript store (KV + SQL) — ETHGlobal NYC integration |
| DataCredentialAgent | TEE-attested team dynamics credential from meeting corpus |
| Hedera HCS | Autonomous deal outcome publishing — `hiero_sdk_python` |
| Arc | On-chain credential anchoring via ArcIDRegistry |
| ENS | Agent identity reverse resolution — `GET /api/ens/agents` |
| Frontend | React 18 + Vite 5 + Tailwind CSS (Phase 6) |
| API framework | FastAPI + uvicorn |
| Persistence | SQLite via aiosqlite |
| Smart contract | Solidity (DealProof.sol) on Sepolia — Phase 4 |

---

## Quick Start

> For a complete step-by-step guide including Docker, Sepolia escrow, and Phala Cloud deployment, see **[QUICKSTART.md](QUICKSTART.md)**.

### Prerequisites

- Python 3.11+
- An Anthropic API key (get one at console.anthropic.com)
- Docker + Docker Compose (for TEE simulator mode)

### Frontend (React)

The `frontend/` directory contains a Vite + React + Tailwind UI that connects to the backend.

```bash
cd frontend
npm install
npm run dev        # starts at http://localhost:5173
```

In `frontend/.env` (copy from `.env.example`):
```
VITE_API_URL=http://localhost:8000
```

The Vite dev server proxies `/api` and `/health` to the backend automatically — no CORS issues in development.

For production, set `VITE_API_URL` to your Phala Cloud CVM URL and deploy `frontend/` to Vercel (the included `vercel.json` handles SPA routing).

---

### Local — no Docker, no TEE

The simplest way to run. Uses the Phase 1/2 flow — negotiation works, but attestation is not available without tappd.

```bash
git clone <repo>
cd Dealproof

cp .env.example .env
# Edit .env and set:  ANTHROPIC_API_KEY=sk-ant-...

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Server is live at `http://localhost:8000`.

Run the demo:
```bash
python demo.py --no-proof
```

### Docker + tappd simulator (full flow, fake TDX quotes)

The recommended local dev mode. The `phalanetwork/tappd-simulator` container mimics the real Phala CVM tappd API. The `memory-service` container runs the Contexto memory sidecar.

```bash
cp .env.example .env
# Edit .env:  ANTHROPIC_API_KEY=sk-ant-...
# Optional:   OPENAI_API_KEY=... or GOOGLE_API_KEY=... (for memory embeddings)

docker compose up --build
```

- API: `http://localhost:8000`
- tappd simulator: `http://localhost:8090`
- Contexto memory sidecar: `http://localhost:4011`

Run the demo:
```bash
python demo.py
python demo.py --scenario medical
python demo.py --two-step
```

### Phala Cloud CVM (real Intel TDX hardware)

On a real CVM the TDX quotes are signed by the CPU's hardware key and verifiable against Intel's public certificate chain.

```bash
# 1. Build and push your image
docker build -t yourdockerhubuser/dealproof:latest .
docker push yourdockerhubuser/dealproof:latest

# 2. Create a CVM on https://cloud.phala.network
#    - Point at your image
#    - Set environment variable: ANTHROPIC_API_KEY=sk-ant-...
#    - All other settings default correctly (tappd binds to localhost:8090 inside CVM)

# 3. Get your CVM's public URL from the dashboard, then:
python demo.py --url https://your-cvm.phala.network
python demo.py --url https://your-cvm.phala.network --scenario lidar
```

The only difference between simulator and production is what `DSTACK_SIMULATOR_ENDPOINT` points at. No code changes needed.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

69 tests pass, 2 skipped (live integration tests) — run with `pytest`, no Docker or tappd required. Every external call (Claude API, tappd, SQLite, memory sidecar) is either mocked or redirected to a temp file.

```
tests/test_agents.py          3 tests  — BuyerAgent + SellerAgent unit tests
tests/test_negotiation.py     4 tests  — Negotiation loop, combined attestation payload
tests/test_tee.py            10 tests  — KMS + TDX quote HTTP calls, report_data construction, GET /api/attest
tests/test_props.py          23 tests  — Props verifier: all pure helpers + failure paths + route gate
tests/test_dkim_verifier.py  19 tests  — DKIM email proof: parsing, DNS-over-HTTPS, verification paths
tests/test_memory.py          4 tests  — Contexto memory client: add, search, hash, sidecar-down resilience
tests/test_picreds.py        11 tests  — πCreds: deterministic constraint checks (5 pure) + auditor + credentials + failure
tests/test_e2e.py            13 tests  — Full HTTP stack end-to-end (TestClient + mocks)
tests/test_contract.py        8 tests  — Phase 4 escrow: on-chain create/complete/refund
```

**Resilience guarantees tested explicitly:**
- Memory sidecar down → deal proceeds, `memory_attested: false`
- πCreds audit fails → deal proceeds, `picreds: null`, `picreds_attested: false`
- DKIM verification fails → deal proceeds, `dkim_verification.verified: false`

---

## Example: `POST /api/deals/run`

The minimal happy-path payload. Copy-paste into curl or the `/docs` Swagger UI at `http://localhost:8000/docs`.

```bash
curl -s -X POST http://localhost:8000/api/deals/run \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_budget": 120.0,
    "buyer_requirements": "US demographic data segmented by age group for market research",
    "data_description": "US census demographic dataset split into three regional chunks",
    "data_hash": "8eb0d327402f025f76800c61c5e5a8a9eb7f4dd75b828aa75fb1bec12a0aeead",
    "floor_price": 60.0,
    "seller_proof": {
      "algorithm": "sha256",
      "chunk_count": 3,
      "chunk_hashes": [
        "7dbc0ac52b859c0da1e912cc0540efac34f317fca0c58ecadc2e335eb5f05489",
        "d923d226228953d6d1fad35e9b9906c6d54c591df2d7b26800f9b47ca64df35e",
        "535c41b0c21e5c19d4fcd921605c512abf054b15e6bda09c631c164bcbce3235"
      ],
      "root_hash": "8eb0d327402f025f76800c61c5e5a8a9eb7f4dd75b828aa75fb1bec12a0aeead"
    }
  }' | python -m json.tool
```

`data_hash` must equal `seller_proof.root_hash` (they are the same hash). Use `generate_seller_proof.py` to compute consistent values for your own dataset chunks:

```bash
python generate_seller_proof.py
```

**Skip verification** (no `seller_proof`):

```bash
curl -s -X POST http://localhost:8000/api/deals/run \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_budget": 80.0,
    "buyer_requirements": "Financial time-series data for backtesting",
    "data_description": "Daily OHLCV stock data, S&P500, 2015-2023",
    "data_hash": "473287f8298dba7163a897908958f7c0eae733e25d2e027992ea2edc9bed2fa8",
    "floor_price": 40.0
  }' | python -m json.tool
```

**Expected response shape (agreed deal):**

```json
{
  "deal_id": "3f2e1d0c-...",
  "agreed": true,
  "final_price": 89.0,
  "terms": {
    "access_scope": "full",
    "duration_days": 365
  },
  "attestation": "sim_quote:9f86d081...",
  "data_verification_attestation": "sim_quote:a3f1e2d4...",
  "dkim_verification": null,
  "memory_hash": "aa...bb:cc...dd",
  "memory_hash_post": "ee...ff:gg...hh",
  "memory_attested": true,
  "picreds": [
    {
      "type": "DealProofCredential",
      "credential_type": "policy",
      "subject": "buyer_agent",
      "deal_id": "3f2e1d0c-...",
      "code_hash": "sha256-of-system-prompt",
      "audit_result": {
        "claims": ["Never offer above budget"],
        "hard_constraints": ["Never offer above budget"],
        "guidelines": ["Open at 60% of budget"],
        "assessment": "Buyer agent constrained to negotiate within budget."
      },
      "issued_at": 1749300000
    },
    {
      "type": "DealProofCredential",
      "credential_type": "policy",
      "subject": "seller_agent",
      "deal_id": "3f2e1d0c-...",
      "code_hash": "sha256-of-seller-system-prompt",
      "audit_result": { "..." : "..." },
      "issued_at": 1749300000
    },
    {
      "type": "DealProofCredential",
      "credential_type": "conduct",
      "subject": "deal",
      "deal_id": "3f2e1d0c-...",
      "code_hash": "",
      "audit_result": {
        "buyer_budget_respected": true,
        "seller_floor_respected": true,
        "no_collusion_detected": true,
        "genuine_negotiation": true,
        "findings": ["Buyer remained within budget. Seller held floor throughout."],
        "assessment": "Both agents complied with their constraints."
      },
      "issued_at": 1749300000
    }
  ],
  "picreds_hash": "64-char-sha256-hex",
  "picreds_attested": true,
  "transcript": [
    {
      "round": 1,
      "role": "seller",
      "action": "offer",
      "price": 100.0,
      "terms": {},
      "reasoning": "Opening at high anchor..."
    },
    {
      "round": 1,
      "role": "buyer",
      "action": "counter",
      "price": 72.0,
      "terms": {},
      "reasoning": "Countering below budget..."
    }
  ]
}
```

---

## Demo

The `demo.py` CLI script runs a complete negotiation and prints every round live.

```
╔══════════════════════════════════════════════════════════════════╗
║         DealProof — Verifiable AI Data Negotiation               ║
║   Powered by Claude claude-sonnet-4-6 + Phala TEE (Intel TDX)    ║
╚══════════════════════════════════════════════════════════════════╝

  Scenario:       Labelled Vision Dataset
  Buyer budget:   $1,000.00   Seller floor:  $600.00
  Server:         http://localhost:8000
  Props verification: enabled

  ✓ Server healthy  |  TEE mode: simulation (tappd-simulator)

  [Props] Generated seller proof for 5 data chunks
  [Props] Root hash: a3f1e2d4b5c6789012345678...

  ⠹ Running verification + negotiation inside TEE…  4.2s

─────────────────────── TRANSCRIPT ──────────────────────────

  [Round 1]  SELLER  OFFER      $840.00  Premium curated dataset…
  [Round 1]  BUYER   COUNTER    $600.00  Above budget, need justif…
  [Round 2]  SELLER  COUNTER    $760.00  Meeting halfway, high qual…
  [Round 2]  BUYER   COUNTER    $700.00  Closer, reasonable ask…
  [Round 3]  SELLER  COUNTER    $730.00  Final offer…
  [Round 3]  BUYER   ACCEPT     $730.00  Within budget, terms OK…

──────────────────────── RESULT ─────────────────────────────

  ✓ Deal agreed  at  $730.00
  Access scope: full   Duration: 365 days

  Data Verification Attestation (Props / TDX):
  0x04020000000000000a0f00…  [512 bytes, Intel TDX quote]

  Deal Attestation (Negotiation / TDX):
  0x04020000000000000a0f00…  [512 bytes, Intel TDX quote]

  Both quotes independently verifiable via Intel DCAP root CA.
  On a real Phala Cloud CVM, submit to: https://proof.phala.network

  Contexto Memory (Phase 8):  ✓ attested
  Pre-deal  (A):  aa3f1e2d4b5c6789…
  Post-deal (B):  bb9f86d081884c7d…
  State transition A→B is covered by the Deal Attestation TDX quote.

  πCreds — Privately Inferred Credentials (Phase 9):  ✓ attested
  buyer_agent    [policy]   Buyer agent constrained to negotiate within budget.
  seller_agent   [policy]   Seller agent holds floor; opens with premium anchor.
  deal           [conduct]  Both agents complied with their constraints.
  Combined hash:  c3d4e5f6a7b8c9d0…  [in TDX report_data]

  On-chain escrow:  Phase 4 — not yet deployed
```

Available scenarios: `vision` (default), `medical`, `lidar`, `finance`, `nlp`

```bash
python demo.py --help
```

---

## API Reference

Base URL: `http://localhost:8000` (local) or `https://your-cvm.phala.network` (Phala Cloud)

### `GET /api/attest`

Pre-flight attestation handshake. **Call this before sending any sensitive payload.** Verify the returned TDX quote against Intel DCAP — confirm `mrenclave` matches your expected build measurement — then proceed to `POST /api/deals/run`.

**Response (200):**
```json
{
  "quote": "0x04020000...",
  "mrenclave": "sha384-hex-or-null",
  "timestamp": 1749300000
}
```

---

### `POST /api/deals`

Create a deal. Stores the full payload in SQLite. Returns immediately.

**Request body:**
```json
{
  "buyer_budget":       1000.0,
  "buyer_requirements": "10GB labelled image dataset...",
  "data_description":   "COCO-style dataset, verified 2024",
  "data_hash":          "a3f1e2d4...64 hex chars",
  "floor_price":        600.0,
  "seller_proof": {
    "root_hash":    "a3f1e2d4...64 hex chars",
    "chunk_hashes": ["<sha256>", "<sha256>", "..."],
    "chunk_count":  5,
    "algorithm":    "sha256"
  },
  "seller_email_eml": "<base64-encoded .eml file>",
  "seller_address":   "0xABCD...",
  "escrow_amount_eth": 0.01
}
```

`seller_proof`, `seller_email_eml`, `seller_address`, and `escrow_amount_eth` are all optional.
- `seller_proof`: enables Props Merkle verification inside the TEE
- `seller_email_eml`: enables DKIM email identity proof (see **DKIM Email Proof** section below)
- `seller_address` + `escrow_amount_eth`: enables on-chain escrow (Phase 4)

**Response (201):**
```json
{"deal_id": "3f2e1d0c-...", "status": "pending"}
```

---

### `POST /api/deals/{deal_id}/negotiate`

Run Props verification + negotiation for a previously created deal.

**Response (200):** See `DealResult` below.
**Response (400):** Seller proof verification failed.
**Response (409):** Deal is not in pending status.

---

### `POST /api/deals/run`

Convenience endpoint: create + verify + negotiate in one call.

Same request body as `POST /api/deals`. Same response as `/negotiate`.

---

### `GET /api/deals/{deal_id}/status`

**Response (200):**
```json
{
  "deal_id": "3f2e1d0c-...",
  "status": "agreed",
  "result": { ...DealResult... }
}
```

Status values: `pending` | `negotiating` | `agreed` | `failed` | `verification_failed`

---

### `GET /api/deals/{deal_id}/attestation`

Returns the negotiation TDX quote (covers `final_price + terms + data_hash + memory_hash + picreds_hash` when all features are active).

**Response (200):**
```json
{
  "deal_id": "3f2e1d0c-...",
  "attestation": "0x04020000..."
}
```

---

### `GET /api/deals/{deal_id}/dcap-verify`

Phase 7: Parse and inspect the raw TDX attestation quote for a deal.

**Response (200):**
```json
{
  "deal_id": "3f2e1d0c-...",
  "mode": "simulation",
  "version": 4,
  "tee_type": "TDX",
  "qe_vendor_id": "939a7233f79c4ca9940a0db3957f0607",
  "report_data_hex": "9f86d081884c7d659a2feaa0...",
  "deal_terms_hash": "9f86d081884c7d659a2feaa0...",
  "verification_status": "simulation_only",
  "error": null
}
```

`verification_status` values:
- `simulation_only` — quote is from the tappd simulator; hardware verification not possible
- `dcap_header_parsed` — real TDX quote; header fields extracted (full DCAP chain verification is Phase 7 on-chain)
- `invalid_quote` — quote bytes could not be parsed

---

### `GET /api/deals/{deal_id}/verification`

Returns the Props data verification record. Only present when `seller_proof` was submitted.

**Response (200):**
```json
{
  "deal_id": "3f2e1d0c-...",
  "verification": {
    "verified": true,
    "data_hash": "a3f1e2d4...",
    "chunk_count": 5,
    "attestation": "0x04020000..."
  }
}
```

---

### `GET /health`

```json
{"status": "ok", "tee_mode": "simulation"}
```

---

### `DealResult` schema

```json
{
  "deal_id":                       "3f2e1d0c-...",
  "agreed":                         true,
  "final_price":                    730.0,
  "terms": {
    "access_scope":                 "full",
    "duration_days":                 365
  },
  "attestation":                    "0x04020000...",
  "data_verification_attestation":  "0x04020000...",
  "dkim_verification": {
    "domain":          "acme.com",
    "verified":         true,
    "dns_unavailable":  false,
    "error":            null
  },
  "memory_hash":      "<buyer_hash>:<seller_hash>",
  "memory_hash_post": "<buyer_hash_post>:<seller_hash_post>",
  "memory_attested":  true,
  "picreds": [...],
  "picreds_hash":          "64-char-sha256-hex",
  "picreds_attested":      true,
  "memory_context_hash":   "64-char-sha256-hex",
  "memory_write_hash":     "64-char-sha256-hex",
  "escrow_tx":             null,
  "completion_tx":    null,
  "transcript": [
    {
      "round":     1,
      "role":      "seller",
      "action":    "offer",
      "price":     840.0,
      "terms":     {},
      "reasoning": "Premium dataset, opening price"
    }
  ]
}
```

`dkim_verification` is `null` when `seller_email_eml` was not provided.
`memory_hash` / `memory_hash_post` / `memory_attested` are set only when the Contexto sidecar is reachable.
`picreds` / `picreds_hash` / `picreds_attested` are set only when the πCreds audit succeeds.
`memory_context_hash` — SHA-256 of the recalled memories injected into agent prompts; proves what the agents remembered before negotiating.
`memory_write_hash` — SHA-256 of the outcome written to memory post-deal; proves this specific deal caused the A→B state transition.

---

## Contexto — Attested Memory

### What It Is

DealProof integrates the [Contexto](https://github.com/ekaics/contexto) `@ekai/memory` package as a sidecar service running alongside the FastAPI app inside the Phala CVM. It gives the buyer and seller agents persistent memory across deals — so they can learn pricing patterns, counterparty behaviors, and dataset characteristics over time.

The memory sidecar runs at `http://localhost:4011` inside the enclave and exposes three endpoints:

| Endpoint | Description |
|----------|-------------|
| `POST /memory/:agentId/add` | Store deal outcome as agent memory |
| `GET /memory/:agentId/search?q=...` | Recall relevant past context before negotiation |
| `GET /memory/:agentId/hash` | SHA-256 of all stored memory rows |

### Memory Flow Per Deal

```
1. Search:   buyer + seller recall relevant past deals → inject into system prompts
2. Snapshot: capture memory_hash (state A) before negotiation starts
3. Negotiate: agents use past context to inform pricing and strategy
4. Store:    agreed outcome saved as memory for both agents
5. Snapshot: capture memory_hash_post (state B) after storing
6. Attest:   both hashes included in TDX report_data
```

### What the TDX Quote Covers

```json
{
  "final_price": 730.0,
  "terms": { "access_scope": "full", "duration_days": 365 },
  "data_hash": "8eb0d327...",
  "data_verified": true,
  "memory_hash":      "<buyer_hash_A>:<seller_hash_A>",
  "memory_hash_post": "<buyer_hash_B>:<seller_hash_B>",
  "memory_attested": true,
  "picreds_hash": "64-char-sha256"
}
```

This establishes a **complete state-transition proof**:

> "The attestation proves that agent code (MRTD) executed on memory state A, produced outcome Y, and arrived at memory state B — all in one hardware-signed quote."

### Resilience

The memory integration is fully non-fatal. If the sidecar is down or returns an error, the deal proceeds normally — `memory_attested: false` in the response. No deal is ever blocked by memory unavailability.

### Running the Memory Sidecar Locally

The sidecar runs automatically in `docker compose up`. For local Python dev without Docker:

```bash
cd memory-service
npm install
node dist/server.js   # starts on port 4011
```

Set `MEMORY_SERVICE_URL=http://localhost:4011` in `.env` (this is the default).

**Embedding provider** (optional — memory still works without embeddings, falling back to exact-match search):

```bash
# Pick whichever key you have — the sidecar auto-detects
OPENAI_API_KEY=sk-...         # recommended
GOOGLE_API_KEY=...            # alternative
OPENROUTER_API_KEY=...        # alternative
```

---

## πCreds — Privately Inferred Credentials

> Paper: [Privately Inferred Credentials (πCreds)](https://arxiv.org/pdf/2606.03771)

### What They Are

After each successful deal, the TEE runs a Claude-powered compliance audit over the negotiation using `app/picreds/auditor.py`. This produces three **Privately Inferred Credentials (πCreds)**:

| Credential | Subject | What It Certifies |
|------------|---------|-------------------|
| `policy` | `buyer_agent` | Rules the buyer agent is bound by (from system prompt audit) |
| `policy` | `seller_agent` | Rules the seller agent is bound by (from system prompt audit) |
| `conduct` | `deal` | Whether both agents complied with constraints throughout the negotiation |

### How It Works

```
1. audit_agent_policy("buyer",  buyer.system_prompt)   → policy claims, hard constraints
2. audit_agent_policy("seller", seller.system_prompt)  → policy claims, hard constraints
3. audit_deal_conduct(transcript, budget, floor, price) → compliance verdict
4. make_credential(...)  × 3                           → structured DealProofCredential dicts
5. hash_credentials([cred1, cred2, cred3])             → combined SHA-256
6. picreds_hash embedded in TDX report_data            → hardware-attested
```

The system prompt is never returned — only the auditor's certified claims. A verifier can confirm the audit ran on the same execution as the deal without seeing the raw prompt.

### Credential Structure

```json
{
  "type": "DealProofCredential",
  "credential_type": "policy",
  "subject": "buyer_agent",
  "deal_id": "3f2e1d0c-...",
  "code_hash": "<sha256-of-system-prompt>",
  "audit_result": {
    "claims": ["Never offer above budget", "Open at 60% of budget"],
    "hard_constraints": ["Never offer above budget"],
    "guidelines": ["Open at 60% of budget"],
    "assessment": "Buyer agent constrained to negotiate within budget."
  },
  "issued_at": 1749300000
}
```

### Resilience

πCreds are non-fatal. If the audit call fails, the deal completes normally with `picreds: null` and `picreds_attested: false`.

---

## DKIM Email Proof — Seller Identity Verification

Phase 6 adds a seller identity layer: the seller can upload an email they control (any email sent from their company domain), and the TEE verifies the DKIM signature before negotiation starts. The verified domain is injected into the seller agent's system prompt as an immutable TEE-verified credential.

**Privacy guarantee:** The raw email body is discarded immediately after DKIM verification. Only the domain name and verified flag are retained in the deal record.

**How to use:**

```python
import base64

# Read a .eml file from your email client (Thunderbird: Save As, Apple Mail: Save As)
with open("company_email.eml", "rb") as f:
    eml_b64 = base64.b64encode(f.read()).decode()

payload = {
    "buyer_budget": 1000.0,
    # ... other fields ...
    "seller_email_eml": eml_b64,
}
```

**What the TEE does:**
1. Decodes the base64 `.eml` bytes
2. Extracts the `d=` tag from the `DKIM-Signature` header to identify the domain
3. Fetches the DKIM public key via DNS-over-HTTPS (Cloudflare 1.1.1.1 — works inside Phala CVM where UDP port 53 is blocked)
4. Injects `[TEE-VERIFIED IDENTITY CREDENTIAL] seller represents acme.com` into the seller agent's system prompt
5. Stores `{domain, verified, dns_unavailable, error}` in the deal record

**Note:** `dns_unavailable=true` is returned when the DoH lookup cannot complete. The domain is still extracted but the cryptographic signature check could not finish. The frontend shows a clear warning badge in this case.

---

## Props — How Seller Proof Generation Works

> Paper: [Props: Privacy-Preserving Proof of Data Authenticity](https://arxiv.org/pdf/2410.20522)

The seller generates their proof before creating the deal:

```python
import hashlib

# Split dataset into ordered chunks
chunks = [dataset[i:i+chunk_size] for i in range(0, len(dataset), chunk_size)]

# Hash each chunk
chunk_hashes = [hashlib.sha256(c).hexdigest() for c in chunks]

# Compute length-prefixed flat Merkle root
# The 4-byte length prefix defeats preimage attacks (N×32-byte single-chunk collision)
length_prefix = len(chunk_hashes).to_bytes(4, "big")
raw = length_prefix + b"".join(bytes.fromhex(h) for h in chunk_hashes)
root_hash = hashlib.sha256(raw).hexdigest()

seller_proof = {
    "root_hash":    root_hash,
    "chunk_hashes": chunk_hashes,
    "chunk_count":  len(chunks),
    "algorithm":    "sha256",
}

# data_hash in DealCreate must equal root_hash
```

Or just run `python generate_seller_proof.py` to get ready-to-paste JSON for multiple scenarios.

The TEE verifies:
1. `seller_proof.root_hash == data_hash` (advertised hash matches proof)
2. `SHA-256( N.to_bytes(4,'big') || chunk_hash[0] || ... || chunk_hash[N-1] ) == root_hash` (length-prefixed, defeating preimage attacks)
3. No duplicate chunk hashes (prevents padding with repeated entries)
4. Signs the result with a TDX quote — the buyer can verify independently.

---

## TinyCloud — Live Transcript Corpus

DealProof connects to [TinyCloud Listen](https://listen.tinycloud.xyz) — a TEE-hosted transcript workspace — to pull meeting recordings as the dataset being negotiated. The data flows through `POST /api/transcripts/ingest` then `POST /api/deals/run`.

### Three ingest modes

| Mode | How | Auth | Use when |
|------|-----|------|----------|
| `direct` | Inline conversations in request body | None | Tests, synthetic data |
| `local` | Reads `TinyCloud/feed/conversations.json` + `TinyCloud/feed/transcripts/*.json` | None | Development, offline |
| `tinycloud` | Live HTTP fetch via the bridge (port 4098) | Bridge handles `tc` auth | Production, fresh data |

### Local mode — quick start

Bulk-download the corpus once from your authenticated `tc` session:

```bash
cd TinyCloud/feed
bun install
# authenticate once (opens browser)
bunx tc init --name listen --host https://node.tinycloud.xyz
# grant read caps
bunx tc auth request --profile listen --cap "tinycloud.sql:applications:xyz.tinycloud.listen/conversations:read" --grant --yes
bunx tc auth request --profile listen --cap "tinycloud.kv:applications:xyz.tinycloud.listen/:get,list,metadata" --grant --yes
```

Then save the corpus (449 conversations, ~225 transcripts):

```bash
# All conversation rows
bunx tc --json sql query "SELECT * FROM conversation" \
  --space applications --db xyz.tinycloud.listen/conversations --profile listen \
  | python3 -c "
import json,sys; r=json.loads(sys.stdin.read()); rows=[dict(zip(r['columns'],row)) for row in r['rows']]; open('conversations.json','w').write(json.dumps(rows,indent=2))
"

# All transcript blobs → transcripts/<id>.json  (PowerShell)
New-Item -ItemType Directory -Force -Path transcripts | Out-Null
$keys = (bunx tc kv list --prefix "xyz.tinycloud.listen/transcript" --space applications --profile listen --json | ConvertFrom-Json).keys
foreach ($key in $keys) {
    $id = $key.Split('/')[-1]
    bunx tc kv get $key --space applications --raw --profile listen | Out-File -Encoding utf8 "transcripts\$id.json"
}
```

Ingest into DealProof:

```bash
curl -s -X POST http://localhost:8000/api/transcripts/ingest \
  -H "Content-Type: application/json" \
  -d '{"corpus_id": "listen-corpus-v1", "mode": "local"}' | python -m json.tool
```

The response includes `corpus_root` and `seller_proof` — paste them directly into `POST /api/deals/run` as `data_hash` and `seller_proof`.

### Bridge mode — live TinyCloud connection

The TinyCloud node requires UCAN delegation auth plus a specific TLS fingerprint (JA3) that Python's httpx cannot satisfy. `TinyCloud/bridge.ts` is a thin Bun shim that wraps the `tc` CLI and exposes a plain HTTP API on port 4098 that DealProof can reach.

Start the bridge (from `TinyCloud/feed` where the `tc` binary lives):

```bash
cd TinyCloud/feed
TC_BIN=./node_modules/.bin/tc bun run ../bridge.ts
# [bridge] listening on 0.0.0.0:4098
```

Then ingest live:

```bash
curl -s -X POST http://localhost:8000/api/transcripts/ingest \
  -H "Content-Type: application/json" \
  -d '{"corpus_id": "listen-live-v1", "mode": "tinycloud"}' | python -m json.tool
```

`tinycloud_host` defaults to `http://localhost:4098` (the bridge). To call the node directly, set `tinycloud_host` to `https://node.tinycloud.xyz` and pass the UCAN delegation token as `tinycloud_session_token`.

### How the corpus becomes a deal

```
TinyCloud/feed/conversations.json       449 conversation rows (SQL)
TinyCloud/feed/transcripts/rec-*.json   225 transcript blobs (KV)
       ↓  POST /api/transcripts/ingest  (local or tinycloud mode)
       hash_transcript() per conversation  →  per-conversation SHA-256
       compute_corpus_root(hashes)          →  Merkle root
       → corpus_root  + seller_proof        →  stored in SQLite
       ↓  POST /api/deals/run  (data_hash = corpus_root)
       TEE agents negotiate the transcript corpus as the data product
       TDX quote over deal terms + Merkle root  →  attested DealResult
       ↓  POST /api/deals/{id}/credential
       DataCredentialAgent assesses the corpus   →  TeamDynamicsCredential
       TDX quote + Arc anchor + Hedera HCS       →  verifiable on-chain
```

### Key source files

| File | Role |
|------|------|
| `app/props/transcript_hasher.py` | `hash_sentence()`, `hash_transcript()`, `compute_corpus_root()` — the Merkle pipeline |
| `app/api/routes.py:682` | `_hash_conversation()` — sentences-first, summary fallback |
| `app/api/routes.py:704` | `ingest_corpus()` — `direct` / `tinycloud` / `local` mode dispatch |
| `app/agents/data_credential.py` | `DataCredentialAgent` — LLM assessment of team dynamics from corpus |
| `TinyCloud/bridge.ts` | Bun HTTP proxy wrapping `tc` CLI for Python ↔ TinyCloud auth bridge |
| `TinyCloud/feed/` | Pinned `tc` CLI + saved corpus files (`conversations.json`, `transcripts/`) |
| `TinyCloud/TINYCLOUD_WORKFLOW.md` | Full auth setup, session patch, troubleshooting |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# TEE (defaults work for docker compose)
DSTACK_SIMULATOR_ENDPOINT=http://localhost:8090
TEE_MODE=simulation   # or "production" on Phala Cloud

# Contexto memory sidecar (defaults work for docker compose)
MEMORY_SERVICE_URL=http://memory-service:4011

# Embedding provider for memory (pick one — memory works without embeddings too)
OPENAI_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=

# Blockchain (Phase 4 — leave blank until Phase 4 deploy)
RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
PRIVATE_KEY=
CONTRACT_ADDRESS=

# App
DEBUG=true
LOG_LEVEL=INFO
```

---

## Project Structure

```
Dealproof/
├── app/
│   ├── main.py              FastAPI app + lifespan + CORS middleware
│   ├── config.py            Pydantic Settings (reads .env)
│   ├── db.py                SQLite persistence (aiosqlite)
│   ├── agents/
│   │   ├── buyer.py         BuyerAgent — Claude claude-sonnet-4-6
│   │   ├── seller.py        SellerAgent — Claude claude-sonnet-4-6 (verified_domain)
│   │   └── negotiation.py   run_negotiation() loop + TEE sign
│   ├── api/
│   │   ├── routes.py        All HTTP endpoints + memory + πCreds orchestration
│   │   └── schemas.py       Pydantic models (DealCreate, DealResult, PiCred, etc.)
│   ├── tee/
│   │   ├── attestation.py   sign_result() → POST /prpc/Tappd.TdxQuote
│   │   ├── kms.py           get_signing_key() → POST /prpc/Tappd.DeriveKey
│   │   └── dcap.py          Phase 7: TDX quote header parser
│   ├── dkim/
│   │   ├── __init__.py      Package exports
│   │   └── verifier.py      Phase 6: DKIM email proof verification (dkimpy + DoH)
│   ├── props/
│   │   └── verifier.py      verify_data_authenticity() + Merkle root
│   ├── memory/
│   │   ├── __init__.py      Package exports
│   │   └── client.py        Phase 8: Contexto memory sidecar client (httpx)
│   ├── picreds/
│   │   ├── __init__.py      Package exports
│   │   ├── auditor.py       Phase 9: LLM audit — policy + conduct
│   │   └── credential.py    Phase 9: make_credential(), hash_credentials()
│   └── contract/
│       └── escrow.py        web3.py escrow (Phase 4)
├── memory-service/          Contexto @ekai/memory sidecar (Node.js/TypeScript)
│   ├── src/server.ts        Express HTTP server (port 4011)
│   ├── Dockerfile           Node 20 slim
│   └── vendor/memory/       @ekai/memory package (vendored for Docker)
├── frontend/                Phase 6: React + Vite + Tailwind UI
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js       (proxies /api + /health to localhost:8000)
│   ├── vercel.json          (SPA rewrite for Vercel deploy)
│   └── src/
│       ├── App.jsx          React Router setup
│       ├── api.js           All fetch calls (reads VITE_API_URL)
│       ├── pages/
│       │   ├── Home.jsx     Landing page + health status
│       │   ├── CreateDeal.jsx  Deal form + DKIM upload
│       │   └── DealView.jsx    Live transcript + result + DCAP inspect
│       └── components/
│           ├── TranscriptFeed.jsx
│           ├── AttestationCard.jsx
│           └── StatusBadge.jsx
├── contracts/
│   ├── DealProof.sol        Solidity escrow contract (Phase 4)
│   └── hardhat.config.js    Hardhat config for Sepolia deploy
├── tests/
│   ├── test_agents.py       Unit — buyer/seller agents (3)
│   ├── test_negotiation.py  Unit — negotiation loop (4)
│   ├── test_tee.py          Unit — KMS + attestation + GET /api/attest (10)
│   ├── test_props.py        Unit — Props verifier (23)
│   ├── test_dkim_verifier.py Unit — DKIM email proof (19)
│   ├── test_memory.py       Unit — Contexto memory client (4)
│   ├── test_picreds.py      Unit — πCreds auditor + credentials (6)
│   ├── test_e2e.py          E2E  — full HTTP stack (13)
│   └── test_contract.py     Unit — Phase 4 escrow (8)
├── generate_seller_proof.py Generates ready-to-paste seller_proof JSON for all scenarios
├── verify_attestation.py    Client-side attestation verification script
├── demo.py                  CLI demo script
├── Dockerfile               Python 3.11-slim, uvicorn
├── docker-compose.yml       app + dstack-simulator + memory-service
├── requirements.txt         All Python deps (incl. dkimpy, httpx)
├── .env.example             Environment variable template
└── IMPLEMENTATION.md        Phase-by-phase plan
```

---

## Phase Status

| Phase | What | Status |
|-------|------|--------|
| 1 | FastAPI scaffold, Claude agents, negotiation loop | ✅ Complete |
| 2 | TEE integration — dstack tappd, TDX quotes, SQLite persistence, AsyncAnthropic | ✅ Complete |
| 3 | Props layer — Merkle proof verification, data hash binding, combined attestation | ✅ Complete |
| 4 | Smart contract — DealProof.sol on Sepolia, web3.py escrow | ✅ Complete |
| 5 | Polish & demo — CLI script, README, E2E tests | ✅ Complete |
| 6 | React frontend (Vite + Tailwind), DKIM email identity proof, CORS | ✅ Complete |
| 7 | DCAP quote parsing (header + report_data extraction); full on-chain cert chain verification | 🔄 Partial — quote parsing done; on-chain verifier contract pending |
| 8 | Contexto attested memory — sidecar integration, memory_hash A→B in TDX attestation, 90 tests | ✅ Complete |
| 9 | πCreds — LLM-inferred policy + conduct credentials attested in TDX quote | ✅ Complete |
| 10 | Auditor agent — read-only TEE compliance witness; credential_hash in TDX report_data | ✅ Complete |
| 11 | Arbitrator agent — deadlock resolution; arbitrated settlement attested in TDX quote | ✅ Complete |
| 12 | DCAP on-chain verifier contract | 🔜 Pending |
| **ETHGlobal NYC** | **TinyCloud Integration** | |
| M1 | Transcript corpus hasher — `app/props/transcript_hasher.py` | ✅ Complete |
| M2 | `POST /api/transcripts/ingest` — direct + tinycloud (bridge) + local modes | ✅ Complete |
| M3 | DataCredentialAgent — TEE-attested team dynamics credential | ✅ Complete |
| M4 | `POST /api/deals/{id}/credential` — attested TeamDynamicsCredential | ✅ Complete |
| M5 | Tests — transcript hasher + ingestion + credential endpoint | ✅ Complete |
| M6 | Arc on-chain credential anchoring — ArcIDRegistry.register() | ✅ Complete |
| M7 | Hedera HCS autonomous deal outcome publishing — hiero_sdk_python | ✅ Complete |
| M8 | ENS agent identity — reverse resolution + `GET /api/ens/agents` | ✅ Complete |
| M9 | ETHGlobal NYC prize submission copy — ETHGLOBAL_SUBMISSIONS.md | ✅ Complete |
| **product/fundraising-credential** | **Fundraising Diligence Vertical** | |
| F1 | `app/fundraising/` package — metrics hasher + ingest endpoint + DB table | ✅ Complete |
| F2 | `MetricsInspectorAgent` (deterministic) + `MetricsEvaluatorAgent` (LLM) | ✅ Complete |
| F3 | `FundraisingDiligenceCredential` + evaluate endpoint + TDX attestation | ✅ Complete |
| F4 | Synthetic fixtures + `tests/test_fundraising.py` (18+ tests, SCAE scenarios) | 🔜 Pending |
| F5 | Frontend: diligence dashboard + before/after demo view | 🔜 Pending |

---

## ETHGlobal NYC — TinyCloud Demo Flow

DealProof integrates with [TinyCloud Listen](https://github.com/TinyCloudLabs/listen) — meeting transcripts stored in a TEE-native KV/SQL store on Phala.

```
# 1. Ingest transcript corpus (direct mode or live TinyCloud)
POST /api/transcripts/ingest
  { "corpus_id": "...", "mode": "direct", "conversations": [...] }
  → corpus_root, seller_proof

# 2. Negotiate data access inside TEE
POST /api/deals/run
  { "buyer_budget": 1000, "data_hash": <corpus_root>, "seller_proof": ..., "floor_price": 600 }
  → deal agreed + TDX attestation + Hedera HCS timestamp

# 3. Issue TEE-attested team dynamics credential
POST /api/deals/{id}/credential
  → TeamDynamicsCredential { decision_velocity, collaboration_balance,
                             commitment_count, execution_signal, ... }
     + TDX quote + Arc anchor

# 4. Verify on-chain
GET /api/deals/{id}/hedera   → HashScan link (Hedera testnet)
GET /api/deals/{id}/arc      → ArcIDRegistry agentId
GET /api/ens/agents          → ENS names for all deal participants
```

**Prize targets:** ENS ($4k) · Arc ($2k) · Hedera ($3k) · Unlink ($1k) · World ($2.5k)

**Narrative:** A PE firm evaluates a startup without seeing raw transcripts. DealProof negotiates access inside a TEE, a credential agent reads the corpus still inside the enclave, and issues a signed credential: *"This team reaches decisions in under 2 meetings, balanced contribution, 11 concrete commitments."* The investor gets the credential + TDX attestation + Arc anchor + Hedera timestamp. The transcripts never leave.

See [`ETHGLOBAL_SUBMISSIONS.md`](ETHGLOBAL_SUBMISSIONS.md) for full prize submission copy.

---

## Verifying an Attestation

A TDX attestation quote returned by the API can be verified by any party:

**Using Phala's online verifier:**
Submit the hex quote to `https://proof.phala.network` (requires real Phala Cloud CVM — simulator quotes will not pass hardware verification).

**Using Intel DCAP:**
```bash
# The quote is a standard DCAP quote structure
# Verify using: https://github.com/intel/SGXDataCenterAttestationPrimitives
```

**Using the included client script:**
```bash
python verify_attestation.py --url https://your-cvm.phala.network --deal-id 3f2e1d0c-...
```

**What to check in the quote:**
1. The quote signature is valid (signed by CPU hardware key → chains to Intel root CA)
2. `MRTD` register matches the expected Docker image measurement
3. `REPORTDATA[0:32]` equals `SHA-256(canonical JSON of deal terms + memory hashes + picreds_hash)`

---

## References

| Paper | Relevance |
|-------|-----------|
| [Privately Inferred Credentials (πCreds)](https://arxiv.org/pdf/2606.03771) | Theoretical basis for the πCreds audit — LLM-inferred, TEE-attested policy and conduct credentials |
| [Props: Privacy-Preserving Proof of Data Authenticity](https://arxiv.org/pdf/2410.20522) | Merkle-based data provenance scheme used in the Props verification layer |
| [NDAI: Non-Disclosure AI](https://arxiv.org/pdf/2502.07924) | Broader framework for private AI computation with hardware attestation — motivates the overall DealProof architecture |

---

## License

[MIT](LICENSE)
