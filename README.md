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
                    TDX attestation quote
                    (hardware-signed proof)
                             │
                    DCAP quote parsing
                    (Phase 7: header + report_data)
                             │
                    On-chain escrow release
                    (DealProof.sol on Sepolia)
```

The TEE attestation is an Intel TDX quote verifiable by anyone against Intel's public certificate chain. It binds to the exact deal terms and data hash — if any of them differ, the quote is invalid.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    Phala Cloud CVM (Intel TDX)                     │
│                                                                    │
│  ┌─────────────┐    ┌──────────────────────────────────────────┐   │
│  │  FastAPI    │    │          Negotiation Loop                │   │
│  │  (uvicorn)  │───►│  BuyerAgent  ◄──────►  SellerAgent      │   │
│  └─────────────┘    │  (AsyncAnthropic)    (AsyncAnthropic)   │   │
│         │           └──────────────────────────────────────────┘   │
│         │                            │ agreed                      │
│         │           ┌────────────────▼─────────────────────────┐   │
│         │           │         Props Verifier                   │   │
│         │           │  validate_proof_structure()               │   │
│         │           │  compute_merkle_root(chunk_hashes)        │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ verified                   │
│         │           ┌──────────────────▼───────────────────────┐   │
│         │           │         TEE Attestation                  │   │
│         │           │  tappd: POST /prpc/Tappd.TdxQuote        │   │
│         │           │  report_data = SHA-256(deal terms)       │   │
│         │           └──────────────────┬───────────────────────┘   │
│         │                              │ TDX quote                 │
│  ┌──────▼──────┐    ┌──────────────────▼───────────────────────┐   │
│  │  SQLite     │◄───│         DealResult                       │   │
│  │  (aiosqlite)│    │  attestation + data_verification_att     │   │
│  └─────────────┘    └──────────────────────────────────────────┘   │
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
| Data provenance | Props-inspired Merkle root verification |
| Seller identity | DKIM email proof — `dkimpy` + `dnspython` (Phase 6) |
| DCAP inspection | TDX quote header parser — `app/tee/dcap.py` (Phase 7) |
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

### Docker + tappd simulator (full Phase 3 flow, fake TDX quotes)

The recommended local dev mode. The `phalanetwork/tappd-simulator` container mimics the real Phala CVM tappd API, returning structurally valid but not hardware-signed quotes.

```bash
cp .env.example .env
# Edit .env:  ANTHROPIC_API_KEY=sk-ant-...

docker compose up --build
```

- API: `http://localhost:8000`
- tappd simulator: `http://localhost:8090`

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

All 56+ tests pass without Docker or a running tappd. Every external call (Claude API, tappd, SQLite path) is either mocked or redirected to a temp file.

```
tests/test_agents.py          3 tests  — BuyerAgent + SellerAgent unit tests
tests/test_negotiation.py     4 tests  — Negotiation loop, combined attestation payload
tests/test_tee.py             8 tests  — KMS + TDX quote HTTP calls, report_data construction
tests/test_props.py          22 tests  — Props verifier: all pure helpers + failure paths + route gate
tests/test_e2e.py            10 tests  — Full HTTP stack end-to-end (TestClient + mocks)
tests/test_contract.py        0 tests  — Phase 4 stub
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

  On-chain escrow:  Phase 4 — not yet deployed
```

Available scenarios: `vision` (default), `medical`, `lidar`, `finance`, `nlp`

```bash
python demo.py --help
```

---

## API Reference

Base URL: `http://localhost:8000` (local) or `https://your-cvm.phala.network` (Phala Cloud)

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

Returns the negotiation TDX quote (covers `final_price + terms + data_hash` when proof was provided).

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
  "deal_id":                     "3f2e1d0c-...",
  "agreed":                       true,
  "final_price":                  730.0,
  "terms": {
    "access_scope":               "full",
    "duration_days":               365
  },
  "attestation":                  "0x04020000...",
  "data_verification_attestation": "0x04020000...",
  "dkim_verification": {
    "domain":          "acme.com",
    "verified":         true,
    "dns_unavailable":  false,
    "error":            null
  },
  "escrow_tx":    null,
  "completion_tx": null,
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
3. Fetches the DKIM public key from DNS and verifies the signature
4. Injects `[TEE-VERIFIED IDENTITY CREDENTIAL] seller represents acme.com` into the seller agent's system prompt
5. Stores `{domain, verified, dns_unavailable, error}` in the deal record

**Note:** Inside a Phala CVM, outbound DNS may be restricted by network policy. In that case, `dns_unavailable=true` is returned — the domain is still extracted but the cryptographic verification could not complete. The frontend shows a clear warning badge in this case.

---

## Props — How Seller Proof Generation Works

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

The TEE verifies:
1. `seller_proof.root_hash == data_hash` (advertised hash matches proof)
2. `SHA-256( N.to_bytes(4,'big') || chunk_hash[0] || ... || chunk_hash[N-1] ) == root_hash` (length-prefixed, defeating preimage attacks)
3. No duplicate chunk hashes (prevents padding with repeated entries)
4. Signs the result with a TDX quote — the buyer can verify independently.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# TEE (defaults work for docker compose)
DSTACK_SIMULATOR_ENDPOINT=http://localhost:8090
TEE_MODE=simulation   # or "production" on Phala Cloud

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
│   │   ├── seller.py        SellerAgent — Claude claude-sonnet-4-6 (Phase 6: verified_domain)
│   │   └── negotiation.py   run_negotiation() loop + TEE sign
│   ├── api/
│   │   ├── routes.py        All HTTP endpoints (Phase 6: DKIM step, DCAP endpoint)
│   │   └── schemas.py       Pydantic models (Phase 6: DealCreate.seller_email_eml, DCAPVerification)
│   ├── tee/
│   │   ├── attestation.py   sign_result() → POST /prpc/Tappd.TdxQuote
│   │   ├── kms.py           get_signing_key() → POST /prpc/Tappd.DeriveKey
│   │   └── dcap.py          Phase 7: TDX quote header parser
│   ├── dkim/
│   │   ├── __init__.py      Package exports
│   │   └── verifier.py      Phase 6: DKIM email proof verification (dkimpy + dnspython)
│   ├── props/
│   │   └── verifier.py      verify_data_authenticity() + Merkle root
│   └── contract/
│       └── escrow.py        web3.py escrow (Phase 4)
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
│   ├── test_agents.py       Unit — buyer/seller agents
│   ├── test_negotiation.py  Unit — negotiation loop
│   ├── test_tee.py          Unit — KMS + attestation HTTP calls
│   ├── test_props.py        Unit — Props verifier (22 tests)
│   ├── test_e2e.py          E2E  — full HTTP stack (TestClient)
│   └── test_contract.py     Phase 4 escrow tests
├── demo.py                  CLI demo script
├── Dockerfile               Python 3.11-slim, uvicorn
├── docker-compose.yml       app + dstack-simulator
├── requirements.txt         All Python deps (incl. dkimpy, dnspython)
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

**What to check in the quote:**
1. The quote signature is valid (signed by CPU hardware key → chains to Intel root CA)
2. `MRTD` register matches the expected Docker image measurement
3. `REPORTDATA[0:32]` equals `SHA-256(canonical JSON of your deal terms or verification payload)`

---

## License

[MIT](LICENSE)
