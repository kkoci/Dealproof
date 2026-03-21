# DealProof — Quickstart Guide

Everything you need to go from zero to a running deal, step by step.

---

## What you need before starting

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com)
- Git

That's it for the basic local flow. Everything else (Node.js, Docker, wallet) is only needed for the optional on-chain escrow section.

---

## 1. Clone the repo

```bash
git clone https://github.com/<your-username>/dealproof.git
cd dealproof
```

---

## 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs FastAPI, uvicorn, the Anthropic SDK, web3, aiosqlite, and pytest.

---

## 3. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` in any text editor. Fill in:

```
ANTHROPIC_API_KEY=sk-ant-...        ← paste your Anthropic key here
TEE_MODE=simulation                 ← leave this as-is for local use
```

Leave everything else blank for now — they are only needed for the on-chain escrow flow.

---

## 4. Start the server

```bash
uvicorn app.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Open your browser at **http://localhost:8000/health** — you should see:
```json
{"status": "ok", "version": "0.5.0"}
```

---

## 5. Open the API docs

Go to **http://localhost:8000/docs**

This is the interactive Swagger UI. You can use it to fire deals directly from the browser without writing any code.

---

## 6. Generate a test payload

In a second terminal, run:

```bash
python generate_seller_proof.py
```

This prints ready-to-paste JSON payloads for 10 test scenarios. Copy the **Scenario A** block — it is the full happy path with a 3-chunk dataset.

---

## 7. Run your first deal

In the Swagger UI:

1. Click **POST /api/deals/run** to expand it
2. Click **Try it out**
3. Paste the Scenario A JSON into the request body
4. Click **Execute**

The agents will negotiate for a few seconds. The response includes:
- `"agreed": true` — negotiation succeeded
- `"final_price"` — the agreed price
- `"attestation"` — TEE attestation (a mock hash in simulation mode)
- `"data_verification_attestation"` — Merkle proof of the dataset, also attested

---

## 8. Run the test suite

```bash
pytest tests/ -v
```

All 49 tests should pass. No network calls are made — everything is mocked.

---

## Optional: Run with Docker

If you have Docker installed:

```bash
docker compose up --build
```

This starts two containers:
- `app` — the FastAPI server on port 8000
- `dstack-simulator` — a local Phala tappd simulator on port 8090

In Docker mode, `TEE_MODE` is automatically set to `simulation` and the attestation calls go to the local simulator instead of a real enclave.

---

## Optional: Deploy the smart contract to Sepolia

You need Node.js and a funded Sepolia wallet for this.

### Step 1 — Install Hardhat

```bash
cd contracts
npm install
```

### Step 2 — Fill in the remaining `.env` values

```
RPC_URL=https://sepolia.infura.io/v3/<your-infura-key>
PRIVATE_KEY=<your-wallet-private-key>
```

Get a free Infura key at https://app.infura.io

Get free Sepolia ETH at https://sepolia-faucet.pk910.de (proof-of-work, no requirements — mine until you have 0.05 ETH)

### Step 3 — Compile and deploy

```bash
npx hardhat compile
npx hardhat run scripts/deploy.js --network sepolia
```

The output prints a contract address. Paste it into `.env`:

```
CONTRACT_ADDRESS=0x...
```

### Step 4 — Run a deal with escrow

Add these fields to your Scenario A payload:

```json
"seller_address": "0x<your-wallet-address>",
"escrow_amount_eth": 0.001
```

The response will now include:
- `"escrow_tx"` — transaction hash of the ETH deposit
- `"completion_tx"` — transaction hash of the payment release

Verify both on **https://sepolia.etherscan.io**

---

## Optional: Deploy to Phala Cloud (real Intel TDX)

This runs DealProof inside a real hardware enclave. The `attestation` field in the response will be a genuine TDX quote instead of a mock.

### Step 1 — Push the Docker image

```bash
docker build -t <your-dockerhub-username>/dealproof:latest .
docker push <your-dockerhub-username>/dealproof:latest
```

### Step 2 — Create a CVM on Phala Cloud

1. Go to https://cloud.phala.network and sign in
2. Add credits (minimum $5 account balance required)
3. Click **Deploy** and paste this docker-compose, filling in your values:

```yaml
services:
  app:
    image: <your-dockerhub-username>/dealproof:latest
    ports:
      - "8000:8000"
    volumes:
      - /var/run/tappd.sock:/var/run/tappd.sock
    environment:
      - ANTHROPIC_API_KEY=<your-anthropic-key>
      - TEE_MODE=production
      - RPC_URL=https://sepolia.infura.io/v3/<your-infura-key>
      - PRIVATE_KEY=<your-wallet-private-key>
      - CONTRACT_ADDRESS=<your-contract-address>
```

4. Wait for status to change from **Starting** to **Running** (2–5 minutes)
5. Your CVM URL is shown on the dashboard — open `<url>/health` to confirm it's live

In production mode the `attestation` field contains a real Intel TDX quote that can be verified against Phala's TEE public key.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
| `ANTHROPIC_API_KEY not set` | Check your `.env` file exists and has the key filled in |
| `500` on `/api/deals/run` | Check server logs — likely a missing API key or tappd connection issue |
| `400 Merkle root mismatch` | Use payloads from `generate_seller_proof.py` — don't edit the hashes manually |
| `422 buyer_budget below floor_price` | This is intentional (Scenario G) — use a payload where budget > floor |
| Phala CVM `PR_END_OF_FILE_ERROR` | CVM is still starting — wait 2–3 more minutes and retry |
