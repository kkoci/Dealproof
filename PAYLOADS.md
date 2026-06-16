# DealProof — Payloads, Evals & Synthetic Datasets

Reference for every request payload you might send to DealProof.
All payloads are copy-paste ready for `http://localhost:8000`.

---

## Quick reference

| Payload | Endpoint | Section |
|---------|----------|---------|
| Vision dataset deal | `POST /api/deals/run` | [Standard deals](#standard-deals) |
| Medical imaging deal | `POST /api/deals/run` | [Standard deals](#standard-deals) |
| Financial FX deal (tight margin) | `POST /api/deals/run` | [Standard deals](#standard-deals) |
| Ingest local corpus (no network) | `POST /api/transcripts/ingest` | [Transcript corpus ingest](#transcript-corpus-ingest) |
| Ingest via bridge (live TinyCloud) | `POST /api/transcripts/ingest` | [Transcript corpus ingest](#transcript-corpus-ingest) |
| Ingest single real transcript | `POST /api/transcripts/ingest` | [Transcript corpus ingest](#transcript-corpus-ingest) |
| Deal over real transcript corpus | `POST /api/deals/run` | [Deals over real corpora](#deals-over-real-corpora) |
| Eval: healthy team dynamics | `POST /api/transcripts/ingest` | [Synthetic evals](#synthetic-evals) |
| Eval: conflict-heavy team | `POST /api/transcripts/ingest` | [Synthetic evals](#synthetic-evals) |
| Eval: summary-only corpus | `POST /api/transcripts/ingest` | [Synthetic evals](#synthetic-evals) |

---

## Standard deals

These hit `POST /api/deals/run` directly with a synthetic `data_hash` — no TinyCloud
corpus needed. Include `seller_proof` to activate Props Merkle verification + a
second TDX attestation quote.

### Vision dataset — standard agreement

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

### Medical imaging — high-value, multi-round

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

### Financial FX — tight margin, arbitration likely on deadlock

Floor ($500) and budget ($560) are only $60 apart. If agents don't converge in
`max_rounds`, ArbitratorAgent activates and the response will have `"arbitrated": true`.

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

---

## Transcript corpus ingest

`POST /api/transcripts/ingest` computes a Merkle root over the corpus.
The response `corpus_root` + `seller_proof` plug directly into `POST /api/deals/run`.

### Mode: local (no network, uses TinyCloud/feed/ files)

Run after bulk-downloading the corpus (see `TinyCloud/TINYCLOUD_WORKFLOW.md` § Step 6).

```json
{
  "corpus_id": "listen-corpus-v1",
  "mode": "local"
}
```

Override the path if the default auto-discovery doesn't work:

```json
{
  "corpus_id": "listen-corpus-v1",
  "mode": "local",
  "local_corpus_path": "/absolute/path/to/TinyCloud/feed"
}
```

Expected response: ~385 hashable conversations, mix of transcript + summary.

### Mode: tinycloud (live fetch via bridge)

Start the bridge first: `TC_BIN=./node_modules/.bin/tc bun run ../bridge.ts`

```json
{
  "corpus_id": "listen-live-v1",
  "mode": "tinycloud"
}
```

Override host to call the TinyCloud node directly (requires UCAN delegation token):

```json
{
  "corpus_id": "listen-direct-v1",
  "mode": "tinycloud",
  "tinycloud_host": "https://node.tinycloud.xyz",
  "tinycloud_session_token": "<paste Authorization header from ~/.tinycloud/profiles/listen/session.json>"
}
```

### Mode: direct — one real conversation inline

This is conversation `rec-03bd0ce45a46ee5aa60175e1` from the actual TinyCloud corpus
(recorder source, 7 sentences, 2026-05-08). Hashes are pre-computed and deterministic.

```json
{
  "corpus_id": "single-real-transcript",
  "mode": "direct",
  "conversations": [
    {
      "id": "rec-03bd0ce45a46ee5aa60175e1",
      "title": "TX00 MIC042 20260508 050638 orig",
      "source": "recorder",
      "started_at": "2026-05-08T05:06:38.000Z",
      "sentences": [
        {
          "index": 0,
          "speaker_id": "speaker-a",
          "speaker_name": "Speaker A",
          "text": "I'm getting very competitive with my deals. So the thing I noticed, the deals are getting more competitive. They used to be more cooperative.",
          "start_time": 1559.077,
          "end_time": 1587.108,
          "language": null
        },
        {
          "index": 1,
          "speaker_id": "speaker-b",
          "speaker_name": "Speaker B",
          "text": "Hey.",
          "start_time": 1587.318,
          "end_time": 1587.511,
          "language": null
        },
        {
          "index": 2,
          "speaker_id": "speaker-a",
          "speaker_name": "Speaker A",
          "text": "Oh, hey. Hey, how are you? Good, good. Are you heading out?",
          "start_time": 1587.656,
          "end_time": 1591.416,
          "language": null
        },
        {
          "index": 3,
          "speaker_id": "speaker-b",
          "speaker_name": "Speaker B",
          "text": "Yeah, I think we are.",
          "start_time": 1591.755,
          "end_time": 1592.594,
          "language": null
        },
        {
          "index": 4,
          "speaker_id": "speaker-a",
          "speaker_name": "Speaker A",
          "text": "Yeah. Are you coming back? Maybe. Are you ever going to give me employee permissions to Little Salem? Honestly, at this point, yeah. Book me a hotel and I'll make it happen.",
          "start_time": 1593.956,
          "end_time": 1608.413,
          "language": null
        },
        {
          "index": 5,
          "speaker_id": "speaker-b",
          "speaker_name": "Speaker B",
          "text": "I wanted to tell you, la manda here throwing our birthday this Saturday at Igo's. So if you want to come by, it's Saturday from 7 PM onwards.",
          "start_time": 1608.671,
          "end_time": 1624.295,
          "language": null
        },
        {
          "index": 6,
          "speaker_id": "speaker-a",
          "speaker_name": "Speaker A",
          "text": "Okay, come whenever. Okay, thank you. For sure. Bye-bye.",
          "start_time": 1624.521,
          "end_time": 1628.534,
          "language": null
        }
      ]
    }
  ]
}
```

Expected response:

```json
{
  "corpus_id": "single-real-transcript",
  "conversation_count": 1,
  "corpus_root": "b750f83533f74f083d495ec52b3d9e67b37ff77ca120338756f74edeaba2284a",
  "seller_proof": {
    "root_hash": "b750f83533f74f083d495ec52b3d9e67b37ff77ca120338756f74edeaba2284a",
    "chunk_hashes": ["6f79b21fea4fc56fadd0937e05dc6eda4977c026908c318f2d0514637de50d8b"],
    "chunk_count": 1,
    "algorithm": "sha256"
  },
  "summaries_available": 0
}
```

---

## Deals over real corpora

Two-step flow: ingest first (get `corpus_root`), then run a deal with it.

### Step 1 — ingest the full local corpus

```json
{
  "corpus_id": "listen-corpus-v1",
  "mode": "local"
}
```

Save the `corpus_root` from the response (should be deterministic across runs
for the same downloaded corpus).

### Step 2 — run a deal over the corpus

```json
{
  "buyer_budget": 4000.0,
  "buyer_requirements": "Full TinyCloud Listen transcript corpus — 449 meetings, team dynamics data for org analytics",
  "data_description": "449 recorder + Fireflies meeting recordings, 206 with full transcripts, 179 with Fireflies AI summaries, date range 2025-2026",
  "data_hash": "<corpus_root from Step 1>",
  "floor_price": 2500.0,
  "seller_proof": {
    "root_hash": "<corpus_root from Step 1>",
    "chunk_hashes": ["<chunk_hashes array from Step 1 seller_proof>"],
    "chunk_count": "<conversation_count from Step 1>",
    "algorithm": "sha256"
  }
}
```

Then issue a credential:

```
POST /api/deals/{deal_id}/credential
```

No body needed — the deal_id links to the ingested corpus.

---

## Synthetic evals

Self-contained corpora with pre-computed deterministic hashes. No TinyCloud
auth or network needed. Designed for testing DataCredentialAgent, πCreds
auditing, and the full attestation pipeline.

### Eval 1 — Healthy team dynamics

Three short conversations showing good collaboration: clear ownership, unblocking
behaviour, constructive retro. DataCredentialAgent should return positive indicators
for psychological safety, decision quality, and participation balance.

**Step 1: ingest**

```json
{
  "corpus_id": "eval-healthy-team",
  "mode": "direct",
  "conversations": [
    {
      "id": "eval-healthy-c1",
      "title": "Sprint review — week 23",
      "source": "recorder",
      "started_at": "2026-06-02T10:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"alice","speaker_name":"Alice","text":"Alright, let's kick off. What did we ship this week?","start_time":0,"end_time":4,"language":"en"},
        {"index":1,"speaker_id":"bob","speaker_name":"Bob","text":"Backend rate limiter is live. Zero production incidents.","start_time":5,"end_time":9,"language":"en"},
        {"index":2,"speaker_id":"carol","speaker_name":"Carol","text":"Frontend pagination merged and deployed. Users are happy.","start_time":10,"end_time":13,"language":"en"},
        {"index":3,"speaker_id":"alice","speaker_name":"Alice","text":"Any blockers heading into next sprint?","start_time":14,"end_time":16,"language":"en"},
        {"index":4,"speaker_id":"bob","speaker_name":"Bob","text":"Nothing blocking. I could use Carol's input on the new API contract.","start_time":17,"end_time":20,"language":"en"},
        {"index":5,"speaker_id":"carol","speaker_name":"Carol","text":"Happy to sync after this. Put an invite on my cal.","start_time":21,"end_time":24,"language":"en"},
        {"index":6,"speaker_id":"alice","speaker_name":"Alice","text":"Great collaboration. Let's keep this cadence.","start_time":25,"end_time":27,"language":"en"}
      ]
    },
    {
      "id": "eval-healthy-c2",
      "title": "Scope creep discussion",
      "source": "recorder",
      "started_at": "2026-06-04T14:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"dave","speaker_name":"Dave","text":"I want to flag a concern about scope creep on the auth module.","start_time":0,"end_time":5,"language":"en"},
        {"index":1,"speaker_id":"alice","speaker_name":"Alice","text":"Good catch Dave. What specifically?","start_time":6,"end_time":8,"language":"en"},
        {"index":2,"speaker_id":"dave","speaker_name":"Dave","text":"We added three features nobody approved. I'd like a decision framework.","start_time":9,"end_time":14,"language":"en"},
        {"index":3,"speaker_id":"alice","speaker_name":"Alice","text":"Agreed. Let's formalise a lightweight RFC process. Anyone against?","start_time":15,"end_time":18,"language":"en"},
        {"index":4,"speaker_id":"bob","speaker_name":"Bob","text":"Sounds good. I'll draft a template.","start_time":19,"end_time":21,"language":"en"},
        {"index":5,"speaker_id":"carol","speaker_name":"Carol","text":"I'll review it before it goes out.","start_time":22,"end_time":24,"language":"en"},
        {"index":6,"speaker_id":"alice","speaker_name":"Alice","text":"Perfect. We'll adopt it next sprint.","start_time":25,"end_time":27,"language":"en"}
      ]
    },
    {
      "id": "eval-healthy-c3",
      "title": "Sprint retrospective",
      "source": "recorder",
      "started_at": "2026-06-06T16:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"alice","speaker_name":"Alice","text":"Retro time. What went well?","start_time":0,"end_time":3,"language":"en"},
        {"index":1,"speaker_id":"bob","speaker_name":"Bob","text":"The on-call rotation worked. No alert fatigue.","start_time":4,"end_time":8,"language":"en"},
        {"index":2,"speaker_id":"carol","speaker_name":"Carol","text":"Pair programming sessions were super useful.","start_time":9,"end_time":12,"language":"en"},
        {"index":3,"speaker_id":"dave","speaker_name":"Dave","text":"Documentation quality improved a lot.","start_time":13,"end_time":16,"language":"en"},
        {"index":4,"speaker_id":"alice","speaker_name":"Alice","text":"And what should we change?","start_time":17,"end_time":19,"language":"en"},
        {"index":5,"speaker_id":"bob","speaker_name":"Bob","text":"Standups are too long. Let's cap at ten minutes.","start_time":20,"end_time":23,"language":"en"},
        {"index":6,"speaker_id":"alice","speaker_name":"Alice","text":"Done. Starting Monday. Good team.","start_time":24,"end_time":26,"language":"en"}
      ]
    }
  ]
}
```

Expected ingest response:

```json
{
  "corpus_id": "eval-healthy-team",
  "conversation_count": 3,
  "corpus_root": "fe649b818f657c70501a3accbe3e2d153c222f94ce2b340af812f7939e3fae1a",
  "seller_proof": {
    "root_hash": "fe649b818f657c70501a3accbe3e2d153c222f94ce2b340af812f7939e3fae1a",
    "chunk_hashes": [
      "71a82bb4023e39de7899209769d6e16ddca576afc0444a0186075e69c6725c1c",
      "f8ee854430d11fc6aa07969c4291fae854e66cb12ba80f572207b1c046555a2b",
      "5a2773d53f9d83348f3d67e551b7bf6da3798b9784a6ea127a15f1d5944e0f1d"
    ],
    "chunk_count": 3,
    "algorithm": "sha256"
  },
  "summaries_available": 0
}
```

**Step 2: deal**

```json
{
  "buyer_budget": 800.0,
  "buyer_requirements": "Team dynamics corpus for org analytics — 3 sprint meetings, collaboration patterns",
  "data_description": "3 recorded team meetings showing sprint velocity, scope management, and retrospective cadence",
  "data_hash": "fe649b818f657c70501a3accbe3e2d153c222f94ce2b340af812f7939e3fae1a",
  "floor_price": 500.0,
  "seller_proof": {
    "root_hash": "fe649b818f657c70501a3accbe3e2d153c222f94ce2b340af812f7939e3fae1a",
    "chunk_hashes": [
      "71a82bb4023e39de7899209769d6e16ddca576afc0444a0186075e69c6725c1c",
      "f8ee854430d11fc6aa07969c4291fae854e66cb12ba80f572207b1c046555a2b",
      "5a2773d53f9d83348f3d67e551b7bf6da3798b9784a6ea127a15f1d5944e0f1d"
    ],
    "chunk_count": 3,
    "algorithm": "sha256"
  }
}
```

---

### Eval 2 — Conflict-heavy team dynamics

Three conversations dominated by one individual, unresolved interpersonal tension,
and blocked collaboration. DataCredentialAgent should surface negative indicators:
low psychological safety, dominant speaker imbalance, unresolved blockers.

**Step 1: ingest**

```json
{
  "corpus_id": "eval-conflict-team",
  "mode": "direct",
  "conversations": [
    {
      "id": "eval-conflict-c1",
      "title": "Architecture decision aftermath",
      "source": "recorder",
      "started_at": "2026-06-03T09:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"mike","speaker_name":"Mike","text":"Why wasn't I included in the architecture decision? Again.","start_time":0,"end_time":5,"language":"en"},
        {"index":1,"speaker_id":"sarah","speaker_name":"Sarah","text":"You were on PTO Mike.","start_time":6,"end_time":8,"language":"en"},
        {"index":2,"speaker_id":"mike","speaker_name":"Mike","text":"That's not an excuse. I should have been consulted async.","start_time":9,"end_time":14,"language":"en"},
        {"index":3,"speaker_id":"sarah","speaker_name":"Sarah","text":"We had a deadline. We made a call.","start_time":15,"end_time":17,"language":"en"},
        {"index":4,"speaker_id":"mike","speaker_name":"Mike","text":"A bad call. This is going to create tech debt.","start_time":18,"end_time":22,"language":"en"},
        {"index":5,"speaker_id":"sarah","speaker_name":"Sarah","text":"We can revisit. But not here.","start_time":23,"end_time":25,"language":"en"},
        {"index":6,"speaker_id":"mike","speaker_name":"Mike","text":"Fine. But I want this documented.","start_time":26,"end_time":28,"language":"en"}
      ]
    },
    {
      "id": "eval-conflict-c2",
      "title": "Access blocker standoff",
      "source": "recorder",
      "started_at": "2026-06-05T11:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"sarah","speaker_name":"Sarah","text":"Status update.","start_time":0,"end_time":2,"language":"en"},
        {"index":1,"speaker_id":"lee","speaker_name":"Lee","text":"I'm blocked. Still waiting on access from Mike.","start_time":3,"end_time":7,"language":"en"},
        {"index":2,"speaker_id":"mike","speaker_name":"Mike","text":"I'll get to it when I get to it.","start_time":8,"end_time":10,"language":"en"},
        {"index":3,"speaker_id":"lee","speaker_name":"Lee","text":"It's been four days Mike.","start_time":11,"end_time":13,"language":"en"},
        {"index":4,"speaker_id":"sarah","speaker_name":"Sarah","text":"Mike, this is blocking the sprint.","start_time":14,"end_time":16,"language":"en"},
        {"index":5,"speaker_id":"mike","speaker_name":"Mike","text":"My plate is full. You should have planned better.","start_time":17,"end_time":21,"language":"en"},
        {"index":6,"speaker_id":"sarah","speaker_name":"Sarah","text":"I'll escalate this. Meeting over.","start_time":22,"end_time":24,"language":"en"}
      ]
    },
    {
      "id": "eval-conflict-c3",
      "title": "Deadline disagreement",
      "source": "recorder",
      "started_at": "2026-06-07T15:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"sarah","speaker_name":"Sarah","text":"We need to talk about the Q2 deadline.","start_time":0,"end_time":4,"language":"en"},
        {"index":1,"speaker_id":"mike","speaker_name":"Mike","text":"We can't hit it. Full stop.","start_time":5,"end_time":8,"language":"en"},
        {"index":2,"speaker_id":"lee","speaker_name":"Lee","text":"I disagree. With scope cuts it's doable.","start_time":9,"end_time":13,"language":"en"},
        {"index":3,"speaker_id":"mike","speaker_name":"Mike","text":"Lee has no idea what's in the backlog.","start_time":14,"end_time":17,"language":"en"},
        {"index":4,"speaker_id":"lee","speaker_name":"Lee","text":"I have the same backlog view as you Mike.","start_time":18,"end_time":21,"language":"en"},
        {"index":5,"speaker_id":"sarah","speaker_name":"Sarah","text":"Let's focus. What specifically can we cut?","start_time":22,"end_time":25,"language":"en"},
        {"index":6,"speaker_id":"mike","speaker_name":"Mike","text":"Ask Lee. He thinks he knows everything.","start_time":26,"end_time":29,"language":"en"}
      ]
    }
  ]
}
```

Expected ingest response:

```json
{
  "corpus_id": "eval-conflict-team",
  "conversation_count": 3,
  "corpus_root": "eccbbfa021c3b3bee79abbd0cc948ac19ef4333d5423f4d3dcd7a3961bfae790",
  "seller_proof": {
    "root_hash": "eccbbfa021c3b3bee79abbd0cc948ac19ef4333d5423f4d3dcd7a3961bfae790",
    "chunk_hashes": [
      "8afa274612c355ef6f0669d5cf16b296b7dc97e0b9e8ea9ef7b6fab5d3048409",
      "68045abbef0e705ff358f5472f8f15ed2ae0306fec86559f85fe48079b9ba9fb",
      "5ad3f7f114b93f6e6e0a0354c4b6a936ba8d28d5b32665d7d833bc33dee4bd5a"
    ],
    "chunk_count": 3,
    "algorithm": "sha256"
  },
  "summaries_available": 0
}
```

**Step 2: deal**

```json
{
  "buyer_budget": 600.0,
  "buyer_requirements": "Team dynamics corpus — 3 engineering meetings, conflict and collaboration patterns",
  "data_description": "3 recorded meetings showing interpersonal friction, unresolved blockers, and escalation patterns",
  "data_hash": "eccbbfa021c3b3bee79abbd0cc948ac19ef4333d5423f4d3dcd7a3961bfae790",
  "floor_price": 350.0,
  "seller_proof": {
    "root_hash": "eccbbfa021c3b3bee79abbd0cc948ac19ef4333d5423f4d3dcd7a3961bfae790",
    "chunk_hashes": [
      "8afa274612c355ef6f0669d5cf16b296b7dc97e0b9e8ea9ef7b6fab5d3048409",
      "68045abbef0e705ff358f5472f8f15ed2ae0306fec86559f85fe48079b9ba9fb",
      "5ad3f7f114b93f6e6e0a0354c4b6a936ba8d28d5b32665d7d833bc33dee4bd5a"
    ],
    "chunk_count": 3,
    "algorithm": "sha256"
  }
}
```

---

### Eval 3 — Summary-only corpus (no transcripts)

One Fireflies-style conversation with only an AI-generated summary, no sentences.
Tests the `_hash_conversation` summary-fallback path in `routes.py:694-700`.
DataCredentialAgent receives only the summary text — useful for verifying the
fallback doesn't crash the assessment.

**Step 1: ingest**

```json
{
  "corpus_id": "eval-summary-only",
  "mode": "direct",
  "conversations": [
    {
      "id": "eval-summary-c1",
      "title": "Weekly product sync — Fireflies recording",
      "source": "fireflies",
      "started_at": "2026-06-02T09:00:00Z",
      "summary": "Weekly product sync. Team aligned on roadmap priorities for Q3. Backend team will deliver the new rate-limiting feature by end of week. Frontend team completed pagination work. No major blockers identified. Decision: adopt RFC process for scope changes starting next sprint.",
      "sentences": []
    }
  ]
}
```

Expected ingest response:

```json
{
  "corpus_id": "eval-summary-only",
  "conversation_count": 1,
  "corpus_root": "863ed44a8fc4392e1a0dc51d02527694f4c8e50eef2187c9f02fc14fd9f3c57b",
  "seller_proof": {
    "root_hash": "863ed44a8fc4392e1a0dc51d02527694f4c8e50eef2187c9f02fc14fd9f3c57b",
    "chunk_hashes": ["b0f4ec3da318a8106984ca50e371645813ca266d3487fcd4093183f131b67753"],
    "chunk_count": 1,
    "algorithm": "sha256"
  },
  "summaries_available": 1
}
```

---

### Eval 4 — Mixed corpus (stress test for the hashing pipeline)

One conversation with a transcript + one with only a summary + one that should be
skipped (no transcript, no summary). Tests that:
- `_hash_conversation` prefers sentences over summary when both are present
- Conversations with no hashable content are silently skipped (not a hard error)
- `conversation_count` in the response equals 2, not 3

```json
{
  "corpus_id": "eval-mixed-corpus",
  "mode": "direct",
  "conversations": [
    {
      "id": "eval-mixed-c1",
      "title": "Has transcript",
      "source": "recorder",
      "started_at": "2026-06-01T10:00:00Z",
      "sentences": [
        {"index":0,"speaker_id":"a","speaker_name":"A","text":"We shipped the feature.","start_time":0,"end_time":3,"language":"en"},
        {"index":1,"speaker_id":"b","speaker_name":"B","text":"Looks good on staging.","start_time":4,"end_time":6,"language":"en"}
      ]
    },
    {
      "id": "eval-mixed-c2",
      "title": "Has summary only",
      "source": "fireflies",
      "started_at": "2026-06-02T10:00:00Z",
      "summary": "Team reviewed the deployment pipeline. Agreed to add smoke tests before production pushes.",
      "sentences": []
    },
    {
      "id": "eval-mixed-c3",
      "title": "Will be skipped — no content",
      "source": "fireflies",
      "started_at": "2026-06-03T10:00:00Z",
      "sentences": []
    }
  ]
}
```

Expected: `conversation_count: 2` (the third is skipped with a server-side warning log).

---

## PowerShell one-liners

Standard deals — copy-paste into any terminal:

```powershell
# Vision
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":1000.0,"buyer_requirements":"10 GB COCO-style labelled image dataset","data_description":"10 GB curated COCO dataset, 520k images","data_hash":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","floor_price":600.0}'

# Medical
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":1200.0,"buyer_requirements":"10 GB DICOM medical imaging dataset, HIPAA compliant","data_description":"10 GB de-identified DICOM dataset, radiologist labels","data_hash":"2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824","floor_price":800.0}'

# Financial FX (tight margin)
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/deals/run" -ContentType "application/json" -Body '{"buyer_budget":560.0,"buyer_requirements":"5-year tick FX data, EUR/USD and GBP/USD","data_description":"FX tick data 2019-2024, 8 major pairs, Tier-1 feed","data_hash":"a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3","floor_price":500.0}'

# Local corpus ingest
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/transcripts/ingest" -ContentType "application/json" -Body '{"corpus_id":"listen-corpus-v1","mode":"local"}'

# Eval: healthy team (ingest)
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/transcripts/ingest" -ContentType "application/json" -Body '{"corpus_id":"eval-healthy-team","mode":"direct","conversations":[{"id":"eval-healthy-c1","title":"Sprint review","source":"recorder","started_at":"2026-06-02T10:00:00Z","sentences":[{"index":0,"speaker_id":"alice","speaker_name":"Alice","text":"What did we ship this week?","start_time":0,"end_time":3,"language":"en"},{"index":1,"speaker_id":"bob","speaker_name":"Bob","text":"Rate limiter is live, zero incidents.","start_time":4,"end_time":7,"language":"en"}]}]}'
```
