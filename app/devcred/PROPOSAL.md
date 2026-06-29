# devcred Integration Proposal
## Branch: feat/tinycloud-integration

---

## What we're porting

`Dealproof-devcred` has a clean three-layer pipeline:

| Layer | File | Role |
|-------|------|------|
| Corpus hashing | `git_hasher.py` | Deterministic Merkle root of commit corpus (same length-prefixed SHA-256 algorithm as `transcript_hasher.py`) |
| Hard findings | `agents/git_inspector.py` | Deterministic seniority floor — no LLM, no network, pure metrics |
| Semantic layer | `agents/git_evaluator.py` | Claude Sonnet 4.6 qualitative assessment; seniority clamped ≥ hard signal in code |
| API schemas | `schemas.py` | `SeniorDevCredential` + request/response models |
| API routes | `routes.py` | Ingest → Evaluate → Status; currently uses SQLite |

git-haiku contributes two additional patterns that need Python adaptation:
- **Locked-egress guard**: TEE output constrained to a sanitized, schema-validated snapshot before serialization
- **Commit data boundary discipline**: GitHub fetch strictly bounded (no diffs, no file paths, no patches in egress)

---

## What changes from the devcred source

| Component | devcred source | This branch |
|-----------|---------------|-------------|
| `git_hasher.py` | Uses SQLite for status | **Port as-is** — no persistence here |
| `agents/git_inspector.py` | Standalone | **Port as-is** — pure computation |
| `agents/git_evaluator.py` | Standalone | **Port as-is** — uses `anthropic.AsyncAnthropic` |
| `schemas.py` | Standalone | **Port as-is** — Pydantic models unchanged |
| `routes.py` | SQLite persistence | **Adapted**: TinyCloud KV via bridge (port 4098) |
| `routes.py` | No egress guard | **Adapted**: Python locked-egress guard added at evaluation endpoint |
| `routes.py` | Local attestation wrapper | **Adapted**: reuse existing `app/tee/attestation.py` (`sign_result()`) |
| _(new)_ `egress.py` | _(from git-haiku)_ | Python adaptation of the output-guard pattern |

---

## New file: `app/devcred/egress.py` — Python locked-egress guard

git-haiku's egress pipeline is: **Sanitize → Validate → Serialize**, with a guarded denial fallback.

In Python, Pydantic with `model_config = ConfigDict(extra='forbid')` collapses sanitize + validate into one step. The guard becomes:

```python
from pydantic import ValidationError
from app.devcred.schemas import SeniorDevCredential

def guard_credential_output(raw: dict) -> SeniorDevCredential | None:
    """
    TEE output gate. Validates raw dict against SeniorDevCredential schema
    (extra fields rejected). Returns None on any validation failure — caller
    must not emit a partial credential.
    """
    try:
        return SeniorDevCredential.model_validate(raw)
    except ValidationError:
        return None
```

`SeniorDevCredential.model_dump()` then serializes only declared fields — nothing can ride out on prototype or extra keys.

The "guarded denial" in git-haiku becomes `credential: null, tee_attested: false` in our response — same non-fatal resilience pattern used by the Auditor and πCreds.

**Why this matters in a TEE:** the guard ensures that if the LLM evaluator returns unexpected fields (prompt injection, schema drift), nothing extraneous leaves the enclave in the credential. The enclave's output contract is the schema.

---

## Storage: TinyCloud KV via existing bridge (port 4098)

Instead of SQLite, ingest state and evaluated credentials are stored via the bridge already used by `transcript_hasher.py` and `DataCredentialAgent`:

```
# Ingest phase
PUT KV:  devcred/{credential_id}/state
         → {"status": "ingested", "corpus_root": "...", "commit_count": N, "metrics": {...}}

# Evaluate phase (after guard passes)
PUT KV:  devcred/{credential_id}/credential
         → SeniorDevCredential JSON (guarded output)

# Status endpoint
GET KV:  devcred/{credential_id}/state
GET KV:  devcred/{credential_id}/credential
```

The bridge exposes `GET /v1/kv/:key` and `POST /v1/sql` — we only need the KV endpoints. The Python client is a thin `httpx.AsyncClient` wrapper (same pattern as `app/memory/client.py` for the Contexto sidecar).

**Why TinyCloud KV instead of SQLite:** the existing SQLite in this repo is for deal results. Credentials are a separate concern and belong in TinyCloud where they can be fetched by the TC node with delegation. This also means a delegated frontend can read credentials without touching the FastAPI service.

---

## Attestation: reuse `app/tee/attestation.py`

The evaluate endpoint re-attests after the guard passes, embedding:

```
SHA-256(credential_hash || repo_corpus_root)
```

in `report_data` via the existing `sign_result()`. This mirrors how `DataQualityAgent` embeds `quality_hash` in Step Q of `_negotiate_deal()`.

`credential_hash` is already computed by `_hash_credential()` (same pattern as `hash_credentials()` in `app/picreds/credential.py`).

---

## Commit data boundary (from git-haiku)

git-haiku fetches ONLY: commit message first line (200-char cap), repo name, timestamp.

The devcred source fetches slightly more — diff stat (insertions, deletions, files changed) and test file ratio from the file path list. These are **aggregate metadata**, not file contents or patches. The `SeniorDevCredential` egress already enforces the boundary: it contains no raw commit data, no file paths, no diffs. The guard is the final enforcement layer.

One addition from git-haiku worth adopting: a hard cap of **300 commits per repo** already in the devcred source (matches git-haiku's `maxCommits=30` spirit, just more generous for seniority signal). No change needed.

---

## Endpoint mapping

| Route | What it does |
|-------|-------------|
| `POST /api/devcred/ingest` | Fetch GitHub commits, extract metrics, compute Merkle root, store state in TinyCloud KV. Returns `corpus_root`. |
| `POST /api/devcred/{id}/evaluate` | Inspector (hard findings) → Evaluator (LLM) → egress guard → TDX attest → store guarded credential in TinyCloud KV. |
| `GET /api/devcred/{id}` | Read status + credential from TinyCloud KV. |

No route changes from the devcred source — only the internals (storage + guard + attestation).

---

## Files to create

```
app/devcred/__init__.py
app/devcred/agents/__init__.py
app/devcred/agents/git_inspector.py   ← port from devcred source (unchanged)
app/devcred/agents/git_evaluator.py   ← port from devcred source (unchanged)
app/devcred/git_hasher.py             ← port from devcred source (unchanged)
app/devcred/schemas.py                ← port from devcred source (unchanged)
app/devcred/egress.py                 ← new: Python locked-egress guard
app/devcred/tinycloud_client.py       ← new: thin httpx wrapper for bridge KV reads/writes
app/devcred/routes.py                 ← adapted: TinyCloud KV + egress guard + existing attestation
```

No changes to `TinyCloud/listen/backend/src/` — that's a reference, not a dependency of the Python layer.

No changes to `app/api/routes.py` at this stage — devcred routes mount separately under `/api/devcred`.

---

## Tests to add

Mirror the devcred test suite structure (`tests/test_data_credential.py` as precedent):

```
tests/test_devcred.py        ← port from devcred test suite
tests/test_devcred_egress.py ← new: guard accepts valid, rejects extra fields, returns None on failure
```

Key new test cases not in the devcred source:
- `test_guard_rejects_extra_fields`: inject `{"malicious_key": "..."}` into raw dict, verify `None` returned
- `test_guard_fallback_on_invalid_schema`: wrong type for `seniority_level`, verify `None` returned
- `test_tinycloud_client_kv_roundtrip`: mock bridge at port 4098, verify PUT → GET contract
- `test_evaluate_stores_guarded_credential`: full evaluate path, verify only guarded fields in KV

---

## What stays the same (no changes)

- Seniority floor: hard signal cannot be downgraded by LLM — enforced in `git_evaluator.py` via `_clamp_seniority()`
- Non-fatal LLM: evaluator failure falls back to hard findings only
- Privacy: no employer names, file paths, or raw commit content in `SeniorDevCredential`
- Resilience pattern: evaluate failure → `credential: null`, `tee_attested: false`, deal/service continues

---

## Open questions for review

1. **Bridge availability**: the KV bridge (port 4098) is currently started manually from `TinyCloud/feed/`. Should devcred routes fail fast with HTTP 503 if the bridge is unreachable, or fall back to in-memory state (matching the Contexto sidecar pattern)?

2. **GitHub token handling**: the devcred source accepts `github_token` in the ingest request body and uses it in-memory only (never stored). This is consistent with the listen backend's `TcCliSecretsProvider` pattern. Should we also support reading the token from the TinyCloud bridge secrets endpoint (`/v1/secrets/GITHUB_TOKEN`) to avoid token-in-body?

3. **Route mounting**: mount under `/api/devcred` (new prefix) or integrate into existing `/api/deals` namespace? I'd suggest the former — devcred credentials are standalone, not deal-scoped.
