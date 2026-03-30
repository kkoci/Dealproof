# DealProof — Claude Code Context & Next 5 Days Plan

## What is DealProof

TEE-based AI agent negotiation protocol. Two Claude agents (buyer + seller) negotiate access to a private dataset inside a Phala Cloud Confidential VM (Intel TDX). When they agree, dstack tappd produces a hardware-signed TDX attestation quote. A Props-inspired Merkle proof verifies the data before negotiation begins. The data hash is bound into the same attestation as the negotiation outcome.

**Live deployment:** https://0bc9321b172c1ff571bf9966bd44573ef3e103ac-8000.dstack-pha-prod9.phala.network/docs/
**GitHub:** https://github.com/kkoci/Dealproof

## Research Foundation

Built on two IC3 Shape Rotator papers:
1. **NDAI Agreements** (Miller et al.) — AI agent negotiation inside TEEs, cryptographic attestation of outcomes
2. **Props for ML Security** (Juels & Koushanfar) — authenticated data provenance via Merkle proofs

DealProof is the only project that bridges both papers in a single unified attestation.

## Current Architecture

```
Buyer ──► AI Agent ──► TEE (Intel TDX / Phala Cloud) ◄── AI Agent ◄── Seller
                              │
                     Props data verification
                     (Merkle proof of dataset)
                              │
                     TDX attestation quote
                     (hardware-signed proof)
                              │
                     On-chain escrow release
                     (DealProof.sol on Sepolia)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| AI agents | Claude Sonnet via AsyncAnthropic |
| TEE runtime | Phala Cloud CVM (Intel TDX) |
| TEE attestation | dstack tappd — POST /prpc/Tappd.TdxQuote |
| Data provenance | Props-inspired Merkle root verification |
| API framework | FastAPI + uvicorn |
| Persistence | SQLite via aiosqlite |
| Smart contract | Solidity (DealProof.sol) on Sepolia |

## Project Structure

```
Dealproof/
├── app/
│   ├── main.py              FastAPI app + lifespan
│   ├── config.py            Pydantic Settings
│   ├── db.py                SQLite persistence
│   ├── agents/
│   │   ├── buyer.py         BuyerAgent — Claude Sonnet
│   │   ├── seller.py        SellerAgent — Claude Sonnet
│   │   └── negotiation.py   run_negotiation() loop + TEE sign
│   ├── api/
│   │   ├── routes.py        All HTTP endpoints
│   │   └── schemas.py       Pydantic request/response models
│   ├── tee/
│   │   ├── attestation.py   sign_result() → TdxQuote
│   │   └── kms.py           get_signing_key() → DeriveKey
│   ├── props/
│   │   └── verifier.py      Merkle root verification (22 tests)
│   └── contract/
│       └── escrow.py        web3.py integration (Phase 4 complete)
├── contracts/
│   ├── DealProof.sol        Solidity escrow contract
│   └── hardhat.config.js
├── tests/
│   ├── test_agents.py       3 tests
│   ├── test_negotiation.py  4 tests
│   ├── test_tee.py          8 tests
│   ├── test_props.py        22 tests
│   ├── test_e2e.py          10 tests
│   └── test_contract.py     9 tests
├── demo.py                  CLI demo script
├── Dockerfile
└── docker-compose.yml
```

## Phase Status

| Phase | What | Status |
|-------|------|--------|
| 1 | FastAPI scaffold, Claude agents, negotiation loop | ✅ Complete |
| 2 | TEE integration — dstack tappd, TDX quotes, SQLite | ✅ Complete |
| 3 | Props layer — Merkle proof, data hash binding, combined attestation | ✅ Complete |
| 4 | Smart contract — DealProof.sol on Sepolia, web3.py escrow | ✅ Complete |
| 5 | Polish — CLI demo, README, E2E tests | ✅ Complete |
| 6 | Frontend — React UI with wallet connection | 🚧 In progress (scaffold built) |
| 7 | DCAP verification — Full Intel DCAP (Option B) | ✅ Complete (2026-03-30) |

## Test Suite (56 passing)

```
tests/test_agents.py       3 tests  — BuyerAgent + SellerAgent unit tests
tests/test_negotiation.py  4 tests  — Negotiation loop, attestation payload
tests/test_tee.py          8 tests  — KMS + TDX quote HTTP calls
tests/test_props.py       22 tests  — Props verifier: all helpers + failure paths
tests/test_e2e.py         10 tests  — Full HTTP stack (TestClient + mocks)
tests/test_contract.py     9 tests  — Phase 4 escrow contract tests
```

Run with: `pytest tests/ -v`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/deals | Create deal |
| POST | /api/deals/{id}/negotiate | Run negotiation |
| POST | /api/deals/run | Create + negotiate in one call |
| GET | /api/deals/{id}/status | Get status + transcript |
| GET | /api/deals/{id}/attestation | Get TDX quote |
| GET | /api/deals/{id}/verification | Get Props verification |
| GET | /health | Health check |

## Key Technical Details

### Props Merkle Construction (load-bearing)
```python
# Flat concatenation with 4-byte length prefix
length_prefix = len(chunk_hashes).to_bytes(4, "big")
raw = length_prefix + b"".join(bytes.fromhex(h) for h in chunk_hashes)
root_hash = hashlib.sha256(raw).hexdigest()
```
The length prefix is load-bearing (not defensive redundancy) because DealProof uses flat concatenation not a binary tree. Without it, second-preimage attacks are possible.

### TDX Attestation Binding
Deal terms (price, access_scope, duration_days, data_hash) → canonical JSON → SHA-256 → REPORTDATA[0:32] → TDX quote. Anyone can verify by recomputing SHA-256(terms) and comparing to REPORTDATA.

### Dual Attestation
Two separate TDX quotes per deal:
1. Props quote — covers data verification (data_hash, verified, chunk_count)
2. Deal quote — covers negotiation outcome (final_price, terms, data_hash)

Both quotes independently verifiable via Intel DCAP root CA.

### Phase 4 — Smart Contract (Sepolia)
- DealProof.sol deployed on Sepolia testnet
- Escrow holds buyer funds
- completeDeal() releases payment on valid TEE attestation
- refund() returns funds if negotiation fails
- Current: using Phala's attestation verification (Option A)
- Future: full Intel DCAP on-chain verification (Option B)

---

## NEXT 5 DAYS PLAN (March 26–31, 2026)

### Priority 1: Frontend (Days 1-3)
Build a minimal React frontend. Judges and users should be able to run a deal without touching the CLI.

**Required screens:**
1. Home — connect wallet (wagmi + RainbowKit), show live Phala deployment status
2. Create Deal — form for buyer_budget, floor_price, buyer_requirements, data_description, optional seller_proof
3. Deal Running — live negotiation transcript updating in real time (poll /api/deals/{id}/status)
4. Deal Result — show agreed price, terms, attestation hex, Props verification result, link to verify on Phala Trust Center
5. Health status — show TEE mode (simulation/production)

**Tech choices:**
- React + Vite
- wagmi + RainbowKit for wallet connection
- Tailwind CSS
- Fetch API polling for live transcript updates
- Deploy on Vercel

**Reference:** Look at TBVH (https://tbvh-puce.vercel.app/) for UX inspiration — they solved the wallet connection and deal flow UI already. Do not copy, but use as reference for flow.

**Key difference from TBVH:** Show the Props verification result prominently — this is DealProof's unique feature that TBVH doesn't have.

### Priority 2: DCAP Verification (Days 3-4) ✅ COMPLETE (2026-03-30)

Full Intel DCAP verification implemented in `app/tee/dcap.py`.

**Option A (old):** Trust Phala's root cert — Phala says the hardware is genuine.
**Option B (done):** Verify the TDX quote directly against Intel's public PKI — no Phala trust required.

**What was implemented:**
Four-step verification chain in `parse_tdx_quote()`:
1. **cert_chain_valid** — Extract PCK cert chain (Type 5) from QE Certification Data. Verify each cert signed by the next. Confirm root CN is "Intel SGX Root CA" and is self-signed. No hardcoded cert bytes needed — pins to Intel's identity by subject + self-signature.
2. **qe_sig_valid** — Verify QE Report ECDSA-P256 signature using PCK public key. Proves the Quoting Enclave is Intel-signed.
3. **att_key_binding_valid** — Verify QE REPORTDATA[0:32] == SHA-256(att_key_64bytes || qe_auth_data). Proves the attestation key is cryptographically bound to this Intel platform.
4. **td_sig_valid** — Verify ECDSA-P256 signature over Header||TD_Report_Body using the ATT key. Proves the quote content (including deal_terms_hash) has not been tampered with.

**`intel_verified=True`** only when all four pass. This is the full trustless path.

**Files changed:**
- `app/tee/dcap.py` — complete rewrite with 4-step verification
- `app/api/schemas.py` — `DCAPVerification` gains: `cert_chain_valid`, `qe_sig_valid`, `att_key_binding_valid`, `td_sig_valid`, `intel_verified`, `pck_cert_subject`; new `verification_status` values: `dcap_partial`, `dcap_fully_verified`
- `requirements.txt` — added `cryptography>=42.0.0`

**Quote structure reference (TDX v4, ECDSA-P256):**
- `[0:48]` Header, `[48:632]` TD Report (REPORTDATA at +400), `[632:636]` Sig len, `[636:]` Sig data
- Sig data: ecdsa_sig(64) | att_key(64) | qe_report(384) | qe_sig(64) | auth_size(2) | auth_data(N) | cert_type(2) | cert_size(4) | cert_data(M)

**Endpoint:** `GET /api/deals/{id}/dcap-verify` — returns full DCAPVerification JSON including all four check results.

### Priority 3: DKIM Email Proof (Day 4-5)
Add email-based seller credential verification inside the TEE.

**How it works:**
- Seller uploads .eml file as proof of authenticity
- TEE verifies DKIM signature (cryptographic signature email providers attach to outgoing emails)
- If valid, TEE knows email genuinely came from claimed domain
- Email content injected into seller agent's system prompt as TEE-verified context
- After negotiation completes (any outcome), email body deleted — only domain + verified flag retained

**Reference:** TBVH implemented this — see their repo at https://github.com/deepsp94/tbvh for implementation reference.

**Why add this:** Sellers can prove they represent a company (DKIM from company.com domain) without revealing their identity. Strengthens the trust model significantly.

### Priority 4: Accelerator Application (Day 5)
Submit the IC3 Shape Rotator Accelerator application by March 31, 2026.
Form: https://docs.google.com/forms/d/e/1FAIpQLSd7TEFCFsX9Hwg3YmL76mo8YK3uQN5NZ4WIndYzvJS2jUspSQ/viewform

**Key answers to update once frontend is live:**
- 3.9 (biggest gap): Update to remove frontend gap — it's done
- 3.10 (critical blockers): Update to remove frontend blocker
- 3.13 (demo links): Add frontend URL
- 6.2 (availability): Confirm no conflicts

**Accelerator details:**
- 10-week program: May 1 – July 4, 2026
- $50k per graduating team
- IC3 + Flashbots + Blockchain Builders Fund + The Convent
- Demo Day: July 3, 2026 (NYC, tentative)
- Open to non-finalists — Andrew Miller confirmed this publicly

**Potential collaborators to mention:**
- Joanne Muthoni (TrustVerify) — her DCAP layer fills DealProof Phase 7
- Justin Gaffney (ProvaTrust) — AI agent auditability is complementary, already in contact on Discord

---

## Medium Post (Write This Week)

Title: "Building a TEE-based AI Negotiation Protocol on Intel TDX — Implementing NDAI Agreements and Props for ML Security"

Structure:
1. The problem — Arrow's Information Paradox in private data markets
2. The solution — TEE + AI agents + Props verification
3. The Props implementation — Merkle construction, length-prefix defence, why it's load-bearing
4. What working with dstack/tappd actually looks like
5. The dual attestation — one quote binding negotiation + data proof
6. What Phase 4 (DCAP) looks like next
7. Lessons learned

Post to: Medium, then share in IC3 Shape Rotator Discord (#general), tag @Phala Network, tag @IC3 on LinkedIn.

---

## Environment Variables Required

```
# Required
ANTHROPIC_API_KEY=sk-ant-...

# TEE (defaults work for docker compose)
DSTACK_SIMULATOR_ENDPOINT=http://localhost:8090
TEE_MODE=simulation   # or "production" on Phala Cloud

# Blockchain (Phase 4)
RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
PRIVATE_KEY=
CONTRACT_ADDRESS=

# App
DEBUG=true
LOG_LEVEL=INFO
```

---

## Competitive Context

**Shape Rotator Hackathon results (March 25, 2026):**

TEE & AI Track:
- 🥇 ProvaTrust (Justin Gaffney) — $2000 — AI agent auditability, "nobody can prove what agents did"
- 🥈 TBVH (Anantdeep Singh Parihar) — $1000 — NDAI marketplace, DKIM verification, React frontend

Cryptographic Primitives & Identity:
- 🥇 Pramaana (Columbia University) — $2000 — Post-quantum anonymous identity, ASC paper
- 🥈 TrustVerify (Joanne Muthoni) — $1000 — TEE attestation binding to cloud infrastructure, DCAP UI

DeFi & Mechanism Design:
- 🥇 PrrGuard (Ibrahim Abdulkarim) — $2000 — Oracle attack detection, Prrr paper
- 🥈 ThetaSwap (Juan Serrano) — $1000 — Adverse competition oracle

**DealProof's differentiation vs finalists:**
- vs TBVH: DealProof has Props data verification — TBVH doesn't. Buyer can negotiate and pay but has no cryptographic guarantee data matches what was agreed.
- vs TrustVerify: Complementary, not competing. TrustVerify's DCAP layer is DealProof's Phase 7.
- vs ProvaTrust: Different angle — ProvaTrust proves what agents did after the fact, DealProof makes the negotiation itself trustless in real time.
- Unique: Only project bridging NDAI Agreements + Props in a single unified attestation.

---

## Contacts Made Post-Hackathon

- **Justin Gaffney (ProvaTrust)** — Discord friend request sent/accepted, looking for teammates, applying to accelerator
- **Joanne Muthoni (TrustVerify)** — DM planned, DCAP collaboration opportunity

---

## Demo Scenarios

Available via `python demo.py --scenario X`:
- `vision` (default) — labelled image dataset
- `medical` — medical imaging data
- `lidar` — autonomous vehicle sensor data
- `finance` — financial time series
- `nlp` — text corpus

Bad proof scenario: `python demo.py --no-proof` then submit tampered root_hash → returns 400.
