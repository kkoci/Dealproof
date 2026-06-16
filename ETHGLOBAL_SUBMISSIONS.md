# DealProof — ETHGlobal NYC Prize Submissions

## Prize Summary

| Prize | Amount | One-liner |
|-------|--------|-----------|
| ENS | $4,000 | AI negotiating agents have ENS-resolvable identities — buyer and seller addresses reverse-resolve to human-readable names, visible in every deal response |
| Arc | $2,000 | TeamDynamicsCredentials anchored on Arc via ArcIDRegistry.register() — TDX-attested team credentials get permanent on-chain identity records |
| Hedera | $3,000 | Every deal outcome (agreed or failed) is autonomously published to Hedera HCS — immutable timestamped record of every AI negotiation, verifiable on HashScan |
| Unlink | $1,000 | Privacy-by-design negotiation protocol — transcripts never leave the TEE, started pre-event at IC3 |
| World | $2,500 | Live working product on Phala Cloud CVM with real Intel TDX attestation and 109 passing tests |

**Total addressable: $12,500**

---

## ENS — $4,000

**How DealProof uses ENS:**

DealProof gives AI negotiating agents verifiable on-chain identities via ENS.
When a buyer and seller agent negotiate inside a TEE on Phala Cloud, their
Ethereum wallet addresses are reverse-resolved to ENS names — turning `0xabc...`
into `alice.eth`. The deal record includes both the cryptographic TDX attestation
AND the human-readable ENS identity of each participant.

Every `DealResult` response includes `buyer_ens` and `seller_ens` fields.
`GET /api/ens/agents` returns the full list of deal participants with their ENS
names across all negotiations. AI agents are no longer anonymous — they have
names, and those names are on-chain.

**Implementation:** web3.py ENS reverse resolution (`w3.ens.name(address)`),
public Ethereum mainnet RPC, `asyncio.to_thread` for non-blocking integration.
Graceful fallback — no ENS name is not an error, deal proceeds normally.

**Endpoints:**
- `GET /api/ens` — DealProof ENS identity metadata
- `GET /api/ens/agents` — all deal participants with resolved ENS names

---

## Arc — $2,000

**How DealProof uses Arc:**

DealProof anchors TEE-attested `TeamDynamicsCredentials` on Arc via
`ArcIDRegistry.register()`. After two agents negotiate access to a team's
meeting transcripts and a deal is agreed, a `DataCredentialAgent` reads the
corpus inside the TEE and issues a structured credential covering decision
velocity, collaboration balance, commitment count, and execution signal.

This credential — plus its TDX DCAP attestation quote — is submitted to the
ArcIDRegistry contract. The DCAP quote's `report_data` field contains the
credential hash. The operator key signs this report_data, which the
`DCAPVerifier` uses to recover `attestedSigner`. The resulting `agentId`
(`keccak256(mrtd, reportData, attestedSigner)`) becomes the permanent
on-chain anchor for this credential.

ArcID continuity: DealProof extends the ArcID agent identity model from
individual agents to agent-negotiated team credentials. The same registry
that identifies AI agents now anchors what those agents produced.

**Implementation:** web3.py, ArcIDRegistry.sol ABI, Phala TDX DCAP attestation,
`asyncio.to_thread`. Non-fatal — deal and credential still issued if Arc is
unavailable.

**Endpoints:**
- `POST /api/deals/{id}/credential` — issues credential, anchors on Arc
- `GET /api/deals/{id}/arc` — returns Arc transaction hash and record ID

---

## Hedera — $3,000

**How DealProof uses Hedera:**

Every DealProof negotiation outcome — agreed or failed — is autonomously
published to a Hedera Consensus Service topic without any human intervention.
The HCS message includes:

```json
{
  "deal_id": "...",
  "outcome": "agreed | failed",
  "attestation_hash": "SHA-256 of TDX quote",
  "timestamp": "2026-06-13T14:00:00Z"
}
```

Once submitted, this becomes part of Hedera's immutable consensus record.
Every AI negotiation has a permanent, publicly verifiable timestamp on Hedera —
independent of Phala, independent of DealProof's own database. Anyone can
verify when a deal resolved, without trusting the operator.

**Implementation:** `hiero_sdk_python` (`TopicMessageSubmitTransaction`),
Hedera testnet, `asyncio.to_thread`. Non-fatal — deal result returned
regardless of Hedera availability.

**Endpoints:**
- `GET /api/deals/{id}/hedera` — transaction ID + direct HashScan link
  (`https://hashscan.io/testnet/transaction/{id}`)

---

## Unlink — $1,000

**Privacy-by-design from the ground up:**

DealProof is built as a privacy-preserving protocol at every layer:

- **Negotiation runs entirely inside Intel TDX TEE** on Phala Cloud — agents
  and their reasoning never leave the enclave
- **Transcripts (TinyCloud meeting data) are processed inside the enclave** —
  the corpus is ingested, hashed, and assessed by `DataCredentialAgent` without
  the raw content being returned to any caller
- **DKIM email proofs** verify seller identity without revealing email content
- **Contexto attested memory** stores deal outcomes but agents never expose
  raw recalled context — only the hash of what was injected is attested
- **TDX attestation** proves the code ran correctly without revealing inputs —
  verifiers get the proof, not the data

Project started pre-event at IC3 (Initiative for CryptoCurrencies & Contracts),
building on the NDAI paper (Negotiated Data Access Infrastructure,
https://arxiv.org/pdf/2502.07924) and the πCreds paper
(Behavioral Integrity Credentials, https://arxiv.org/pdf/2606.03771).

---

## World — $2,500

**Live working product:**

DealProof is deployed and running on Phala Cloud CVM with real Intel TDX
attestation — not a simulation, not a demo environment. Every deal response
includes a real DCAP TDX quote verifiable against Intel's PKI.

**What's live:**
- Full buyer ↔ seller agent negotiation inside TEE
- Props data provenance verification (separate TDX quote)
- Contexto attested memory — cross-deal agent learning
- πCreds — deterministic conduct constraints + LLM policy credentials
- AuditorAgent — independent TEE compliance witness
- ArbitratorAgent — deadlock resolution inside the enclave
- TinyCloud integration — ingest real meeting transcripts, issue team credentials
- Arc on-chain credential anchoring
- Hedera HCS deal outcome publishing
- ENS agent identity resolution
- 109 tests passing without Docker or tappd

**Stack:** Claude Sonnet 4.6 · Phala Cloud TDX · dstack tappd · FastAPI ·
Contexto @ekai/memory · hiero_sdk_python · web3.py · ArcIDRegistry

---

## Demo Flow

```
# Step 1 — Ingest TinyCloud corpus (Sam's meeting data)
POST /api/transcripts/ingest
  { corpus_id, mode: "tinycloud", tinycloud_session_token }
  → corpus_root, seller_proof

# Step 2 — Negotiate data access inside TEE
POST /api/deals/run
  { buyer_budget, buyer_requirements, data_hash: corpus_root,
    floor_price, seller_proof, buyer_address, seller_address }
  → deal_result + attestation + hedera_transaction_id + buyer_ens + seller_ens

# Step 3 — Issue attested team dynamics credential
POST /api/deals/{id}/credential
  → TeamDynamicsCredential + TDX quote + arc_tx_hash

# Step 4 — Verify on-chain
GET /api/deals/{id}/arc      → Arc transaction hash + agentId
GET /api/deals/{id}/hedera   → Hedera tx ID + HashScan link
GET /api/ens/agents          → ENS names for all deal participants
```

---

## Investor Narrative

> "A PE firm wants to evaluate a startup team before writing a cheque.
> The team doesn't hand over raw meeting transcripts.
> DealProof negotiates access terms inside a TEE — both sides attested on Phala.
> Once agreed, a credential agent reads the transcripts still inside the enclave
> and issues a signed credential: 'This team reaches decisions in under 2 meetings,
> balanced contribution across founders, 11 concrete commitments in 30 days.'
> The investor gets the credential + TDX attestation + Arc anchor + Hedera timestamp.
> The transcripts never leave."
