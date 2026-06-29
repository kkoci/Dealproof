# TinyCloud Sidecar — Design Proposal

## 0. DealProof's existing dstack identity pattern

**Answer: DealProof does NOT have one.**

`app/tee/attestation.py` talks to tappd (`/var/run/tappd.sock`) only to generate
TDX quotes — it never derives a stable private key. There is no `getKey()` call
anywhere in the Python codebase.

The sidecar therefore needs to add its own identity derivation, identical to
git-haiku's `identity.ts`:
- **In TEE**: `dstack.getKey('dealproof/keys/tc-sidecar', 'tc-sidecar')` →
  keccak256 → 32-byte secp256k1 key. Deterministic per app measurement, survives
  reboots of the same image.
- **In local dev**: `TC_SIDECAR_PRIVATE_KEY` env var (gitignored).

This is the DID that the Listen data owner delegates KV-get to. It must be stable —
dstack derives it from the enclave measurement, so the same image always produces
the same DID.

---

## 1. Location

```
tinycloud-sidecar/
  package.json          # declares @tinycloud/cli, @tinycloud/node-sdk, bun runtime
  tsconfig.json
  src/
    index.ts            # Bun.serve entry + route dispatch
    config.ts           # env var resolution (port, node host, key, secrets provider)
    identity.ts         # dstack key derivation + TinyCloudNode init (from git-haiku)
    delegation-store.ts # fileStore (dev) / TinyCloud KV (TEE) (from git-haiku)
    policy.ts           # permission advertisement (KV-get on transcript path)
    transcript.ts       # tc subprocess wrapper: kv-get + sql-query
```

This is a permanent, production service — NOT a dev tool. It lives at project root,
separate from `TinyCloud/feed/` (bulk-download tooling) and
`TinyCloud/listen/backend/` (TinyCloud's own Listen server).

Default port: **4099** (bridge.ts used 4098; keeping them distinct avoids confusion
if both are present during transition).

---

## 2. Endpoints

### POST /internal/delegations

Stores the Listen owner's delegation so the sidecar can make authenticated tc calls.
Called once during setup, not per-request.

```
Request body:
{
  "serialized": "<delegation candidate JSON — the output of the TC wallet sign flow>",
  "ownerDid":   "did:pkh:eip155:1:0x...",
  "expiresAt":  "2027-01-01T00:00:00Z"   // or null
}

Response 200:
{
  "ok":  true,
  "did": "did:pkh:eip155:1:0x..."   // sidecar's backend DID (Listen owner verifies this
                                    //  is the audience they delegated to)
}

Response 400: { "error": "missing serialized / ownerDid" }
Response 500: { "error": "failed to store delegation: ..." }
```

### GET /internal/conversations?limit=300

Fetches conversation metadata rows via `tc sql query` under the stored delegation.
Replaces the bridge's `POST /v1/sql`.

```
Response 200:
{
  "rows": [
    { "id": "rec-...", "title": "...", "source": "fireflies",
      "started_at": "2024-01-15T10:00:00Z", "summary": "..." },
    ...
  ]
}

Response 503: { "error": "no delegation stored — POST /internal/delegations first" }
Response 502: { "error": "tc sql query failed: ..." }
```

SQL issued internally:
```sql
SELECT id, title, source, started_at, summary FROM conversation LIMIT $limit
```
Database: `xyz.tinycloud.listen/conversations` (same as the current bridge constant).

### GET /internal/transcript/:conversationId

Fetches one transcript KV blob via `tc kv get` under the stored delegation.
Replaces the bridge's `GET /v1/kv/{key}`.

```
Response 200: [ { "index": 0, "speaker_id": "...", "speaker_name": "...",
                  "text": "...", "start_time": 1.2, "end_time": 3.4,
                  "language": "en" }, ... ]
  // Raw sentence array — same shape transcript_hasher.py already consumes.

Response 404: { "error": "NOT_FOUND", "id": "rec-..." }
Response 503: { "error": "no delegation stored — POST /internal/delegations first" }
Response 502: { "error": "tc kv get failed: ..." }
```

KV key passed to tc: `xyz.tinycloud.listen/transcript/{conversationId}`

---

## 3. tc subprocess pattern (from git-haiku, adapted for KV)

git-haiku calls `tc secrets get <NAME> --scope <scope> --delegation <file>`.
For KV reads the equivalent is `tc kv get <key> --delegation <file> --host <node>`.
For SQL: `tc sql query <sql> --db <db> --delegation <file> --host <node> --json`.

Each call:
1. Load stored delegation from store (file or TinyCloud KV).
2. Write `stored.serialized` to a temp file under a `0700` dir.
3. Resolve the tc entrypoint via `require.resolve('@tinycloud/cli/package.json')`.
4. `execFile(process.execPath, [tcEntry, 'kv', 'get', key, '--delegation', tempFile,
   '--host', nodeHost, '--json'], { env: { ...process.env, TC_PRIVATE_KEY: privateKey } })`
5. `finally { rmSync(dir, { recursive: true, force: true }) }`

`TC_PRIVATE_KEY` goes in env, never argv — argv is world-readable via `ps`.

### Policy declared by the sidecar (GET /internal/policy)

Optional informational endpoint, mirrors git-haiku's `/api/server-info`. Lets the
Listen owner see exactly what they're delegating to:

```json
[
  {
    "service": "tinycloud.kv",
    "space":   "applications",
    "path":    "xyz.tinycloud.listen/transcript/",
    "actions": ["get"],
    "skipPrefix": true,
    "description": "Read transcript KV blobs from TinyCloud Listen."
  },
  {
    "service": "tinycloud.kv",
    "space":   "applications",
    "path":    "xyz.tinycloud.listen/conversations",
    "actions": ["get"],
    "skipPrefix": true,
    "description": "Read conversation metadata via SQL."
  }
]
```

---

## 4. Delegation flow — who signs and how it gets here

There is ONE delegator: the Listen data owner (Sam, or whoever holds the wallet
that owns the TinyCloud Listen instance). This is not per-user — it is a one-time
admin setup step.

**Flow:**

1. Sidecar starts. `GET /internal/policy` (or just README) tells the operator the
   sidecar's backend DID and the permissions it needs.

2. The Listen owner opens the TinyCloud Listen frontend (already has wallet-sign
   delegation UI), grants DealProof's backend DID KV-get on the transcript path,
   and downloads the delegation candidate JSON.

   Alternative if no UI yet: the Listen owner uses the tc CLI directly:
   ```sh
   tc delegation grant \
     --audience did:pkh:eip155:1:0x<sidecar-DID> \
     --permissions '...' \
     --host node.tinycloud.xyz \
     --json > delegation.json
   ```

3. The delegation JSON is POSTed to `POST /internal/delegations` once:
   ```sh
   curl -X POST http://localhost:4099/internal/delegations \
     -H 'Content-Type: application/json' \
     -d @delegation.json
   ```

4. The sidecar stores it (file in dev, its own TinyCloud KV space in TEE).
   All subsequent transcript fetches use it without any further operator action.

**The delegation survives TEE reboots** because in production it is stored in the
sidecar's own TinyCloud KV space (keyed by `delegations/listen-owner`), which is
bound to the sidecar's stable DID — same pattern as git-haiku.

---

## 5. Process management

### Local dev

Add to a top-level `Procfile` (create if absent) or document in README:

```
# Procfile
api:      uvicorn app.main:app --reload --port 8000
sidecar:  bun run tinycloud-sidecar/src/index.ts
```

Run both with `foreman start` or `overmind start`. The sidecar is optional in local
dev if using `local` or `direct` ingest mode — only required for `tinycloud` mode.

Env in `.env` (gitignored, already used by Python side):
```
TC_SIDECAR_PRIVATE_KEY=0x...   # dev-only stable key; dstack-derived in TEE
TC_SIDECAR_PORT=4099
TC_SIDECAR_NODE_HOST=https://node.tinycloud.xyz
```

### Phala docker-compose (docker-compose.phala.yml)

Add a `tc-sidecar` service alongside the existing `app` service:

```yaml
tc-sidecar:
  image: kkoci/dealproof-tc-sidecar:latest
  restart: unless-stopped
  environment:
    - TC_SIDECAR_PORT=4099
    - TC_SIDECAR_NODE_HOST=https://node.tinycloud.xyz
    # TC_SIDECAR_PRIVATE_KEY is absent here — dstack derives it inside the TEE
    # via the tappd socket (same socket app uses for TDX quotes).
  volumes:
    - /var/run/tappd.sock:/var/run/tappd.sock  # same mount app already uses
  network_mode: "host"  # or share the compose internal network with app
```

The sidecar image is built from `tinycloud-sidecar/Dockerfile` (Bun base image).
It is pushed and rebuilt independently of `app` — only when `tinycloud-sidecar/`
changes.

---

## 6. Changes to routes.py `tinycloud` mode

Currently the `tinycloud` branch in `ingest_corpus()` calls:
- `POST http://localhost:4098/v1/sql` (bridge)
- `GET  http://localhost:4098/v1/kv/{key}` (bridge)

After: replace with two calls to the sidecar. The sidecar URL is read from config
(`settings.tc_sidecar_url`, default `http://localhost:4099`):

```
POST http://localhost:4098/v1/sql
  → GET  http://localhost:4099/internal/conversations?limit=300

GET  http://localhost:4098/v1/kv/xyz.tinycloud.listen/transcript/{id}
  → GET  http://localhost:4099/internal/transcript/{id}
```

Response shapes the Python side sees are identical to what it expects today:
- Conversations: `{ "rows": [...] }` — same key name, same fields.
- Transcript: raw JSON array of sentence objects — same shape `transcript_hasher.py`
  already receives and passes to `hash_transcript()`.

The `tinycloud_host` field on `CorpusIngest` changes meaning slightly: it now
points at the sidecar URL, not at the bridge or the TinyCloud node directly. The
default changes from `http://localhost:4098` to `http://localhost:4099`. Existing
`tinycloud_session_token` field on the schema can be removed (the sidecar handles
auth internally; Python never touches a delegation token).

---

## 7. What is NOT in scope for this sidecar

- Secrets reads (GitHub tokens, etc.) — not needed; the sidecar only reads KV/SQL.
- Per-user delegation flows — only one Listen-owner delegation, not per end-user.
- Encryption/decrypt permissions — transcript blobs in TinyCloud KV are not
  encrypted at the application layer (they are stored as plain JSON by the Listen
  backend). Only the `--delegation` is needed for access control.
- Any changes to `app/devcred/` — unrelated, not touched.
