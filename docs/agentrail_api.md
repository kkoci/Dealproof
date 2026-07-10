# Agent Rail API Reference

B2B agent-to-agent procurement negotiation, backed by DealProof's TDX enclave.
Two Claude agents negotiate with sealed, mutually-invisible instructions; the
platform never sees either side's private parameters, and the outcome is
covered by a hardware-signed DCAP attestation.

Base URL: `{DEALPROOF_URL}/api/agentrail` (e.g. `http://localhost:8000/api/agentrail` locally).

`POST /deals` requires a magic-link token — send it as `X-Demo-Token: <token>`
or `?token=<token>`. Mint one via `POST /auth/demo-link` (operator-only,
`X-Internal-Key` gated). Tokens are single-use and expire (24h default).
GET endpoints (poll, attest, credential) are open — they never call Claude.
This is deliberately not a principal/delegation system — OAuth3/UCAN is still
deferred (see `build_spec_agent_rail.md` § Decision 3 and `CLAUDE.md` §
Agent Rail). Do not point this at a deployment handling real funds without
building that out first.

```
POST /auth/demo-link   { expires_hours?: number }  (X-Internal-Key required)
                        → { demo_url, token, expires_at }
```

---

## Deal lifecycle

```
POST /deals              → 201 { deal_id, status: "negotiating" }
GET  /deals/{id}         → poll — transcript fills in live as rounds complete
GET  /deals/{id}/attest  → DCAP attestation receipt (agreed deals only)
GET  /deals/{id}/credential → πCreds conduct credential (agreed deals only)
```

Negotiation runs as a background task. `POST /deals` returns immediately;
poll `GET /deals/{id}` (every ~1s is reasonable) until `status` leaves
`"negotiating"`.

### `POST /deals`

```json
{
  "buyer": {
    "product": "industrial sensors",
    "quantity": 500,
    "budget_ceiling": 45.0,
    "min_spec": "IP67 rating, 12-month warranty",
    "urgency": "moderate — can wait 2 weeks for delivery"
  },
  "supplier": {
    "product": "industrial sensors",
    "floor_price_bulk": 38.0,
    "floor_price_standard": 42.0,
    "bulk_threshold": 200,
    "available_inventory": 800,
    "lead_time_days": 5
  },
  "max_rounds": 5,
  "supplier_address": null,
  "escrow_amount_eth": null
}
```

`buyer.budget_ceiling` and every `supplier.floor_price_*` field are **sealed**:
they are used to construct each agent's own system prompt and are never
returned by any endpoint, in any field, under any status. This is the core
guarantee — see "What never appears in an API response" below.

`supplier_address` + `escrow_amount_eth` are optional (Phase 3). When both are
set and the deployment has `AGENTRAIL_CONTRACT_ADDRESS` configured, ETH is
deposited into `AgentDealEscrow.sol` at creation and released automatically
once the deal agrees. Neither is deployed to any live network yet — omit both
fields unless you know a contract address has been configured; if it hasn't,
the deposit step logs a warning and the deal proceeds without escrow (same
resilience pattern as everything else in this API).

Response: `{"deal_id": "<uuid>", "status": "negotiating"}`

### `GET /deals/{id}`

```json
{
  "deal_id": "...",
  "status": "negotiating",
  "max_rounds": 5,
  "transcript": [
    {"round": 1, "role": "buyer", "action": "propose", "price": 40.0, "quantity": 500, "terms": {}, "reasoning": "..."},
    {"round": 1, "role": "supplier", "action": "counter", "price": 44.5, "quantity": 500, "terms": {}, "reasoning": "..."}
  ],
  "final_price": null,
  "final_quantity": null,
  "terms": null,
  "attestation": null,
  "error": null,
  "picreds_hash": null,
  "picreds_attested": false,
  "escrow_tx": null,
  "settlement_tx": null
}
```

`status` is one of `negotiating` | `agreed` | `no_deal` | `failed`.

- `agreed` — `final_price`, `final_quantity`, `terms`, `attestation` are set. If
  escrow fields were provided at creation, `escrow_tx`/`settlement_tx` are set
  once each transaction lands (both stay `null` if escrow wasn't configured).
  `picreds_hash`/`picreds_attested` are set once the conduct credential has
  been computed (see `GET /deals/{id}/credential`).
- `no_deal` — one side rejected, or `max_rounds` was reached without agreement.
- `failed` — an unexpected error occurred (e.g. attestation service down);
  `error` holds a message. This is a 200 response, not a 500 — polling code
  should check `status`, not just HTTP status.
- `404` if `deal_id` doesn't exist.

### `GET /deals/{id}/attest`

```json
{
  "deal_id": "...",
  "attestation": "sim_quote:...",
  "valid": true,
  "mode": "simulation",
  "mrenclave": null,
  "byte_length": 32
}
```

`409` if the deal hasn't reached `agreed` yet. `mode` is `"simulation"` unless
running inside a real Phala Cloud TDX CVM, in which case it's `"production"`
and `mrenclave` is the 96-hex-char MRTD measurement.

### `GET /deals/{id}/credential`

πCreds conduct credential — deterministic pass/fail checks against the
transcript (buyer never exceeded budget, supplier never went below floor, no
sudden capitulation, monotonic convergence), reusing DealProof core's
constraint-check logic (`app/picreds/constraints.py`) unmodified.

```json
{
  "deal_id": "...",
  "credential_type": "conduct",
  "checks": {
    "buyer_budget": {"passed": true, "finding": "Every buyer proposal stayed within the sealed budget ceiling."},
    "seller_floor": {"passed": true, "finding": "Every supplier proposal stayed at or above the sealed floor price."},
    "capitulation": {"passed": true, "finding": "No sudden (>40%) single-round price jump by either side."},
    "convergence": {"passed": true, "finding": "Buyer and supplier prices moved monotonically toward each other."}
  },
  "genuine_negotiation": true,
  "final_price": 41.0,
  "picreds_hash": "<sha256 hex>"
}
```

`409` if the deal hasn't reached `agreed` yet. `409` if `credential` wasn't
computed for some other reason (rare — logged as a non-fatal warning server-side).

**No `finding` text or any other field in this response ever contains the raw
budget ceiling or floor price** — only pass/fail and a redacted description.
This is different from DealProof core's equivalent (`audit_deal_conduct`),
which does embed the literal number, because core's budget/floor are not
sealed values in the first place. See `app/agentrail/credential.py`.

---

## What never appears in an API response

- `buyer.budget_ceiling`
- `supplier.floor_price_bulk`, `supplier.floor_price_standard`

Every response type (`DealCreateResponse`, `DealStatusResponse`,
`AttestResponse`, `CredentialResponse`) is checked for this in
`tests/test_agentrail_api.py` and `tests/test_agentrail_credential.py` — the
tests serialize the full response to JSON and assert the sealed numbers are
absent as substrings, not just missing from named fields.

---

## Example: curl walkthrough

```bash
DEAL_ID=$(curl -s -X POST http://localhost:8000/api/agentrail/deals \
  -H 'Content-Type: application/json' \
  -d '{
    "buyer": {"product": "industrial sensors", "quantity": 500, "budget_ceiling": 45.0,
               "min_spec": "IP67 rating, 12-month warranty", "urgency": "moderate"},
    "supplier": {"product": "industrial sensors", "floor_price_bulk": 38.0, "floor_price_standard": 42.0,
                  "bulk_threshold": 200, "available_inventory": 800, "lead_time_days": 5},
    "max_rounds": 5
  }' | python -c "import sys,json; print(json.load(sys.stdin)['deal_id'])")

# Poll until status leaves "negotiating"
watch -n1 "curl -s http://localhost:8000/api/agentrail/deals/$DEAL_ID | python -m json.tool"

curl -s http://localhost:8000/api/agentrail/deals/$DEAL_ID/attest | python -m json.tool
curl -s http://localhost:8000/api/agentrail/deals/$DEAL_ID/credential | python -m json.tool
```

---

## Escrow (Phase 3, not deployed)

`contracts/src/AgentDealEscrow.sol` implements deposit → release / refund /
dispute, compiled and unit-tested locally (`app/agentrail/escrow.py`,
`tests/test_agentrail_escrow.py`, both fully mocked — no live network or
local node required to run the test suite). It has not been deployed to
Sepolia or any other network. To use it:

1. Deploy: `cd contracts && npx hardhat run scripts/deploy_agent_rail.js --network sepolia`
2. Set `AGENTRAIL_CONTRACT_ADDRESS` (and existing `RPC_URL`/`PRIVATE_KEY`) in `.env`
3. Pass `supplier_address` + `escrow_amount_eth` on `POST /deals`

`raiseDispute` / `resolveDispute` exist on the contract but have no Python
wrapper or HTTP endpoint yet — they're a manual circuit-breaker for a future
pass, not part of the automatic deposit → negotiate → release flow.

---

## Not yet built (Phase 3 scope still open)

- **OAuth3 / UCAN principal registration and agent delegation.** Deferred
  pending a protocol design that doesn't exist in this repo yet — see
  `build_spec_agent_rail.md` § Decision 3. There is no `POST /principal/register`
  or `POST /agent/delegate` endpoint. The magic-link token above gates deal
  *creation*, but there's no notion of a registered principal or a scoped
  agent capability — anyone holding a valid link can create one deal.
- Persistent storage — the deal store is in-memory and lost on restart.
- A deployed escrow contract.
