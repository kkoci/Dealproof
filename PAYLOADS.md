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
| IoT sensor dataset (quality-aware deal) | `POST /api/deals/run` | [Structured datasets](#structured-datasets) |
| Full kitchen-sink (every field active) | `POST /api/deals/run` | [Full kitchen-sink payload](#full-kitchen-sink-payload) |

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

---

## Structured datasets

Real data product payloads that exercise the full quality-assessment pipeline:
`seller_proof` (Props Merkle) + `quality_metrics` (DataQualityAgent) + negotiation.

### IoT industrial sensor dataset — quality-aware deal

500-row dataset generated with `random.seed(42)`. Contains 7 columns, 5 chunks of 100
rows each. Intentional quality issues baked in so the buyer has something to negotiate on.

**Dataset facts:**
- 500 rows, 5-minute interval sensor readings, 20 devices (SEN-001 … SEN-020)
- Columns: `timestamp`, `device_id`, `temperature_c`, `humidity_pct`, `pressure_hpa`, `vibration_ms2`, `label`
- `pressure_hpa`: 12.4% null (62 rows) — sensor dropout
- `vibration_ms2`: 6.2% null (31 rows) — sensor dropout
- Label distribution: 84.2% `normal`, 15.8% `anomaly`
- All other columns: 0% null, schema valid

**Chunk hashes** (SHA-256 of `json.dumps(rows, sort_keys=True).encode()` per 100-row batch):

| Chunk | Hash |
|-------|------|
| 0 (rows 0–99) | `77089eda09c00d5fccabc1690e1a9e295c9ca71c2b7a205c6416bad89c1f005a` |
| 1 (rows 100–199) | `8ea0fedbb4445f3915faa8f210995cb8ca0fc60a5d0793a4c32ab29009ded72d` |
| 2 (rows 200–299) | `80c47114a42474f2ca72c11e1132cacc12ac8ae1ce4586c8198f634f488f05b2` |
| 3 (rows 300–399) | `b1b3bec0955ffd86c3ead621abd8338dd455711dcc8698312de64cf44b014077` |
| 4 (rows 400–499) | `d744683c6a0d8910e809bda6c01734f0c4e32947bc1c5a9e133fbd04cba19340` |

**Merkle root:** `65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca`

To regenerate: `python scripts/generate_iot_dataset.py` (produces the same hashes with `random.seed(42)`).

---

**Full deal payload** — Props verification + DataQualityAgent quality assessment + negotiation.
The buyer receives TEE-attested quality findings (null rates, label imbalance) in its system
prompt and can negotiate down based on them. Expected outcome: buyer cites 12.4% null in
pressure column to justify a price below the seller's opening ask.

```json
{
  "buyer_budget": 800.0,
  "buyer_requirements": "500-row industrial IoT sensor dataset for anomaly detection model training — need labelled records with temperature, humidity, pressure and vibration readings",
  "data_description": "500-row industrial IoT sensor dataset, 7 columns, 5-minute intervals, 20 devices, SHA-256 chunked. Note: 12.4% null rate in pressure_hpa column and 6.2% in vibration_ms2 due to sensor dropouts during collection.",
  "data_hash": "65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
  "floor_price": 500.0,
  "seller_proof": {
    "root_hash": "65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
    "chunk_hashes": [
      "77089eda09c00d5fccabc1690e1a9e295c9ca71c2b7a205c6416bad89c1f005a",
      "8ea0fedbb4445f3915faa8f210995cb8ca0fc60a5d0793a4c32ab29009ded72d",
      "80c47114a42474f2ca72c11e1132cacc12ac8ae1ce4586c8198f634f488f05b2",
      "b1b3bec0955ffd86c3ead621abd8338dd455711dcc8698312de64cf44b014077",
      "d744683c6a0d8910e809bda6c01734f0c4e32947bc1c5a9e133fbd04cba19340"
    ],
    "chunk_count": 5,
    "algorithm": "sha256"
  },
  "quality_metrics": {
    "row_count": 500,
    "column_names": ["timestamp", "device_id", "temperature_c", "humidity_pct", "pressure_hpa", "vibration_ms2", "label"],
    "null_rates": {
      "pressure_hpa": 0.124,
      "vibration_ms2": 0.062
    },
    "label_column": "label",
    "label_distribution": {
      "normal": 0.842,
      "anomaly": 0.158
    },
    "schema_valid": true,
    "additional_notes": "Null values in sensor columns are due to connectivity dropouts, not data corruption. Remaining rows are complete."
  }
}
```

**Actual live response** (deal `d0ec6d0f`, agreed at $630, 2 rounds):

> Attestation blobs truncated to `"<hex>"` for readability — full values in the actual API response.

```json
{
  "deal_id": "d0ec6d0f-e76c-459e-81e5-a49dec3c8a00",
  "agreed": true,
  "final_price": 630,
  "terms": { "access_scope": "full dataset", "duration_days": 30 },
  "attestation": "<hex>",
  "data_verification_attestation": "<hex>",
  "escrow_tx": null,
  "completion_tx": null,
  "dkim_verification": null,
  "memory_hash": "566880b89f42e5c5993a828d3375de5113af2bbb87b285521524759e2984d35a:c6165f84fd59465f10a8ff4442d6446576f5e1e3fe9152556357c3cde1888862",
  "memory_hash_post": "7ff7d410920afa7361a94f222234e36f7b40dfde3b1cad01e19b0addb5f850c9:c6165f84fd59465f10a8ff4442d6446576f5e1e3fe9152556357c3cde1888862",
  "memory_attested": true,
  "picreds_hash": "2728bc6ff42961ff174297531e790659224873a9abd497ea0decf5b2f8cc1265",
  "picreds_attested": true,
  "audit_report": {
    "genuine_negotiation": true,
    "round_count": 2,
    "final_price": 630,
    "summary": "Both parties demonstrated authentic adversarial positioning through meaningful concessions across multiple rounds, with the seller moving from 720 to 665 to 630 and the buyer anchoring low at 560 before accepting the seller's final concession, reflecting genuine strategic back-and-forth rather than scripted capitulation.",
    "credential_hash": "f4b891564c3d9a89d89aee24208c6a27395b349a36a063d3de4de88c8066bdb9"
  },
  "audit_error": null,
  "arbitrated": false,
  "memory_context_hash": "1f015e08c7e50c3668fefdea2d3a5fdcefc1a94763314c55a6674ad9bfb73d14",
  "memory_write_hash": "50e9aa13a4e345f7645b71071ac6264dad0bc36a9f7456a50e5cbea92c66ada9",
  "hedera_transaction_id": "0.0.9224782@1781653288.271583795",
  "data_quality_report": {
    "completeness_score": 0.974,
    "schema_consistent": true,
    "label_distribution": { "normal": 0.842, "anomaly": 0.158 },
    "quality_issues": [
      "12.4% null rate in pressure_hpa column due to sensor connectivity dropouts",
      "6.2% null rate in vibration_ms2 column due to sensor connectivity dropouts",
      "Label imbalance: 84.2% normal vs 15.8% anomaly — may affect anomaly detection model training"
    ],
    "overall_quality": "medium",
    "summary": "This 500-row IoT sensor dataset is schema-consistent with moderate completeness (97.4% average across all columns), but exhibits notable null rates in pressure_hpa (12.4%) and vibration_ms2 (6.2%) from sensor dropouts, and a class imbalance favoring normal labels (84.2%) that warrants attention for anomaly detection use cases.",
    "quality_hash": "755a2928eb8051f860e8fc84c3496617d89e102c4358565cd479f3d5787f23bb"
  },
  "quality_attested": true,
  "buyer_ens": null,
  "seller_ens": null,
  "transcript": [
    {
      "round": 1, "role": "seller", "action": "offer", "price": 720,
      "terms": { "access_scope": "full dataset", "duration_days": 30 },
      "reasoning": "Based on our prior engagement where you accepted 675.0 for the TinyCloud meeting corpus, I know you're comfortable in the 650-700 range and move to agreement relatively quickly. I'm opening at 720.0 for this industrial IoT sensor dataset — a modest premium over our last deal, reflecting the different data type and structured sensor telemetry value. I want to be transparent upfront: the TEE-verified quality credential flags a 12.4% null rate in pressure_hpa and 6.2% in vibration_ms2 due to sensor dropouts, plus a class imbalance (84.2% normal vs 15.8% anomaly) that may affect anomaly detection training. I've already factored these limitations into this price — it's fair given the 500-row structured dataset with 20 devices at 5-minute intervals, SHA-256 integrity verified, and 97.4% overall completeness. Full dataset access, 30-day duration, same terms structure as last time."
    },
    {
      "round": 1, "role": "buyer", "action": "counter", "price": 560,
      "terms": { "access_scope": "full dataset", "duration_days": 30 },
      "reasoning": "I appreciate the transparency on quality issues, and I'm using them directly in my valuation. The TEE-verified credential flags real problems: 12.4% null rate in pressure_hpa and 6.2% in vibration_ms2 from sensor dropouts mean I'll need to impute or drop a significant share of records — reducing effective usable data below the 500-row nominal count. The class imbalance (84.2% normal vs 15.8% anomaly) is a meaningful concern for anomaly detection training specifically, potentially requiring oversampling or synthetic augmentation work on my end. These aren't minor issues — they add downstream cost and effort. While I recall our prior engagement moved smoothly near 675 for the TinyCloud corpus, that was clean meeting data. This dataset carries documented quality deficiencies that warrant a lower baseline. I'm opening at 560 — fair given the medium-quality credential and the real imputation burden I'm taking on."
    },
    {
      "round": 1, "role": "seller", "action": "counter", "price": 665,
      "terms": { "access_scope": "full dataset", "duration_days": 30 },
      "reasoning": "I appreciate the detailed pushback and you're right that the quality issues are real — I already priced them in at my opening. But 560 undervalues this dataset materially. The 97.4% overall completeness is solid for industrial IoT telemetry, which routinely sees higher dropout rates in production. The null rates are documented and localized to two columns — the SHA-256 chunked integrity verification means what you get is exactly what's attested. The class imbalance at 15.8% anomaly rate is actually reasonable for real-world industrial anomaly data — synthetic datasets often have to simulate this artificially. I'm coming down to 665 — a meaningful concession from 720, and just below our previous deal price, reflecting the quality delta you've correctly identified."
    },
    {
      "round": 2, "role": "seller", "action": "counter", "price": 630,
      "terms": { "access_scope": "full dataset", "duration_days": 30 },
      "reasoning": "I'll meet you closer to the middle. Moving from 665 to 630 is a genuine concession — that's 90 down from my opening. 630 is still below our last deal price of 675 for the TinyCloud corpus, reflecting my acknowledgment that the documented null rates and class imbalance do carry real downstream cost for you. But the dataset has real structural value: 20 devices, 5-minute resolution, 500 rows of time-series telemetry, cryptographically verified integrity. The quality issues are disclosed and bounded, not hidden surprises. 630, full dataset, 30 days — let's close."
    },
    {
      "round": 2, "role": "buyer", "action": "accept", "price": 630,
      "terms": { "access_scope": "full dataset", "duration_days": 30 },
      "reasoning": "630 is a fair landing point. It's below our prior TinyCloud deal at 675, appropriately reflecting the documented quality issues — the null rates in pressure_hpa and vibration_ms2, and the class imbalance. The seller has made genuine concessions from 720 down to 630, the quality issues are disclosed and bounded, and the dataset has real structural value for my anomaly detection training needs. Well within budget. Accepting here."
    }
  ]
}
```

**What to observe:** both agents referenced the TEE-verified quality credential directly in
their `reasoning` — the seller disclosed issues proactively in round 1 and the buyer cited
them to anchor at $560. The final price ($630) is $45 below the prior TinyCloud deal ($675),
attributable to the quality discount. This is the quality-credential signal working as intended.

**What to observe in the negotiation transcript:** the buyer references the null rates
based on the `additional_notes` context. Neither agent is making up quality facts — both are
working from the same TEE-attested assessment.

---

### IoT dataset — no quality metrics (baseline comparison)

Same dataset, same `seller_proof`, but no `quality_metrics`. The agents negotiate purely on
`data_description` free text. Compare the transcript reasoning to the quality-aware run above
to see how much the structured quality credential changes negotiation behaviour.

```json
{
  "buyer_budget": 800.0,
  "buyer_requirements": "500-row industrial IoT sensor dataset for anomaly detection model training",
  "data_description": "500-row industrial IoT sensor dataset, 7 columns, 5-minute intervals, 20 devices",
  "data_hash": "65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
  "floor_price": 500.0,
  "seller_proof": {
    "root_hash": "65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
    "chunk_hashes": [
      "77089eda09c00d5fccabc1690e1a9e295c9ca71c2b7a205c6416bad89c1f005a",
      "8ea0fedbb4445f3915faa8f210995cb8ca0fc60a5d0793a4c32ab29009ded72d",
      "80c47114a42474f2ca72c11e1132cacc12ac8ae1ce4586c8198f634f488f05b2",
      "b1b3bec0955ffd86c3ead621abd8338dd455711dcc8698312de64cf44b014077",
      "d744683c6a0d8910e809bda6c01734f0c4e32947bc1c5a9e133fbd04cba19340"
    ],
    "chunk_count": 5,
    "algorithm": "sha256"
  }
}
```

---

## Full kitchen-sink payload

Every optional field active. Substitute the three placeholders marked `<...>` — everything
else is copy-paste ready.

| Field | Placeholder | What it unlocks in `DealResult` |
|-------|-------------|--------------------------------|
| `buyer_address` | your buyer wallet address | `buyer_ens` (if address has ENS reverse record) |
| `seller_address` | your seller wallet address | `seller_ens` + `escrow_tx` + `completion_tx` (needs `CONTRACT_ADDRESS` in `.env`) |
| `seller_email_eml` | base64-encoded `.eml` file | `dkim_verification.verified`, `dkim_verification.domain` |

Get the base64 value: `python3 -c "import base64; print(base64.b64encode(open('your.eml','rb').read()).decode())"`

```json
{
  "buyer_budget": 800.0,
  "buyer_requirements": "500-row industrial IoT sensor dataset for anomaly detection model training — need labelled records with temperature, humidity, pressure and vibration readings",
  "data_description": "500-row industrial IoT sensor dataset, 7 columns, 5-minute intervals, 20 devices, SHA-256 chunked. Note: 12.4% null rate in pressure_hpa column and 6.2% in vibration_ms2 due to sensor dropouts during collection.",
  "data_hash": "65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
  "floor_price": 500.0,
  "seller_proof": {
    "root_hash": "65327bf4fcee0f337115c7ab12c4fc54977893386e38b6099ccbd915542effca",
    "chunk_hashes": [
      "77089eda09c00d5fccabc1690e1a9e295c9ca71c2b7a205c6416bad89c1f005a",
      "8ea0fedbb4445f3915faa8f210995cb8ca0fc60a5d0793a4c32ab29009ded72d",
      "80c47114a42474f2ca72c11e1132cacc12ac8ae1ce4586c8198f634f488f05b2",
      "b1b3bec0955ffd86c3ead621abd8338dd455711dcc8698312de64cf44b014077",
      "d744683c6a0d8910e809bda6c01734f0c4e32947bc1c5a9e133fbd04cba19340"
    ],
    "chunk_count": 5,
    "algorithm": "sha256"
  },
  "quality_metrics": {
    "row_count": 500,
    "column_names": ["timestamp", "device_id", "temperature_c", "humidity_pct", "pressure_hpa", "vibration_ms2", "label"],
    "null_rates": {
      "pressure_hpa": 0.124,
      "vibration_ms2": 0.062
    },
    "label_column": "label",
    "label_distribution": {
      "normal": 0.842,
      "anomaly": 0.158
    },
    "schema_valid": true,
    "additional_notes": "Null values in sensor columns are due to connectivity dropouts, not data corruption. Remaining rows are complete."
  },
  "buyer_address": "<YOUR_BUYER_ETH_ADDRESS>",
  "seller_address": "<YOUR_SELLER_ETH_ADDRESS>",
  "escrow_amount_eth": 0.001,
  "seller_email_eml": "<BASE64_ENCODED_EML>"
}
```

**Full populated `DealResult` — every field non-null on success:**

```json
{
  "deal_id": "<uuid>",
  "agreed": true,
  "final_price": "<float>",
  "terms": { "access_scope": "full dataset", "duration_days": 30 },
  "attestation": "<hex>",
  "data_verification_attestation": "<hex>",
  "escrow_tx": "<0x tx hash>",
  "completion_tx": "<0x tx hash>",
  "dkim_verification": {
    "domain": "<seller email domain>",
    "verified": true,
    "dns_unavailable": false,
    "error": null
  },
  "memory_hash": "<buyer_hash>:<seller_hash>",
  "memory_hash_post": "<buyer_hash_post>:<seller_hash_post>",
  "memory_attested": true,
  "picreds": ["<3 DealProofCredential objects>"],
  "picreds_hash": "<hex>",
  "picreds_attested": true,
  "audit_report": {
    "genuine_negotiation": true,
    "round_count": "<int>",
    "final_price": "<float>",
    "summary": "<string>",
    "credential_hash": "<hex>"
  },
  "audit_error": null,
  "arbitrated": false,
  "memory_context_hash": "<hex>",
  "memory_write_hash": "<hex>",
  "hedera_transaction_id": "<topic@timestamp>",
  "data_quality_report": {
    "completeness_score": 0.974,
    "schema_consistent": true,
    "label_distribution": { "normal": 0.842, "anomaly": 0.158 },
    "quality_issues": ["<list>"],
    "overall_quality": "medium",
    "summary": "<string>",
    "quality_hash": "<hex>"
  },
  "quality_attested": true,
  "buyer_ens": "<name.eth or null>",
  "seller_ens": "<name.eth or null>",
  "transcript": ["<NegotiationRound objects>"]
}
```
