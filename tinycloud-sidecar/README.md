# TinyCloud Sidecar

Permanent Node/Bun service that gives DealProof authenticated read access to
TinyCloud Listen transcripts inside a Phala TEE — no manual CLI sessions, no
dev-only bridge, works identically in local dev and production.

---

## Why this exists

DealProof's negotiation agents need real meeting transcripts as their data corpus.
Those transcripts live in TinyCloud Listen — a TEE-native transcript store run by
the TinyCloud team on Phala Cloud. The data is access-controlled: you can only
read it if the Listen data owner has delegated access to your identity.

The previous approach (`TinyCloud/feed/bridge.ts`) was a dev-only shim that
wrapped the `tc` CLI using a pre-authenticated local session. It worked on a
laptop but had no path to production:
- It depended on a live `tc` CLI session tied to a specific user's machine
- It couldn't run inside a Phala CVM without manual setup each time
- It had no delegation auth — it borrowed an existing session rather than
  holding its own credentials

The sidecar replaces it with a production-grade pattern lifted from
[git-haiku](https://github.com/TinyCloudLabs/git-haiku), which runs the same
pattern deployed on Phala today.

---

## How it works

### Identity

The sidecar has a stable Ethereum private key (`TC_SIDECAR_PRIVATE_KEY`). From
that key it derives a `did:pkh:eip155:1:0x...` address — its permanent identity
on TinyCloud. This is what the Listen data owner delegates to.

In local dev the key comes from `.env`. On Phala it is set as a secure CVM
environment variable on the dashboard — never in the image.

### Delegation (one-time setup per CVM)

The Listen data owner (Sam) grants the sidecar's DID read access to the
transcript KV path and conversation SQL. This produces a delegation artifact
(a JSON blob) that is POSTed to the sidecar once:

```
POST /internal/delegations
{ "serialized": "<delegation JSON>", "ownerDid": "did:pkh:eip155:1:0x<Sam>" }
```

The sidecar stores it on a Docker volume (`tc-sidecar-data`). It survives
container restarts and image updates. It is lost if the CVM volume is wiped
(new CVM from scratch) — in that case Sam needs to re-send the delegation JSON.
Same key → same DID → Sam can re-send the original JSON without creating a new
delegation.

### Transcript fetching

On each ingest request, the sidecar:
1. Loads the stored delegation from disk
2. Writes it to a temporary 0700 directory
3. Invokes `tc kv get <key> --delegation <tempfile> --host <node>` as a
   subprocess, passing `TC_PRIVATE_KEY` via env (never argv — argv is
   world-readable via `ps`)
4. Deletes the temp directory in `finally`
5. Returns the parsed sentence array

For conversation metadata it does the same with `tc sql query`.

### What Python sees

`POST /api/transcripts/ingest` with `mode: "tinycloud"` calls the sidecar over
localhost HTTP. The sidecar URL defaults to `http://localhost:4099` in local dev
and `http://tc-sidecar:4099` in Docker Compose (set via `TC_SIDECAR_URL`).

---

## Endpoints

| Method | Path | What |
|--------|------|------|
| `GET` | `/health` | `{ok, hasDelegation}` — liveness + delegation status |
| `GET` | `/internal/policy` | Permission list to send to the Listen owner |
| `POST` | `/internal/delegations` | Store delegation (one-time setup) |
| `GET` | `/internal/conversations?limit=300` | Conversation metadata rows via SQL |
| `GET` | `/internal/transcript/:id` | Sentence array for one conversation via KV |

---

## File structure

```
tinycloud-sidecar/
  Dockerfile
  package.json          # @tinycloud/cli, viem
  tsconfig.json
  .env.example          # committed, placeholder values
  .env                  # gitignored, real values
  .sidecar-data/        # gitignored, delegation store in local dev
  src/
    index.ts            # Bun.serve entry + route dispatch
    config.ts           # env var resolution
    identity.ts         # did:pkh from TC_SIDECAR_PRIVATE_KEY
    delegation-store.ts # single-owner file store
    policy.ts           # permission advertisement
    transcript.ts       # tc subprocess wrappers (kv get + sql query)
```

---

## Environment variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `TC_SIDECAR_PRIVATE_KEY` | Yes | — | Stable secp256k1 key (0x-prefixed). Generate once with `node -e "..."` (see below). |
| `TC_SIDECAR_PORT` | No | `4099` | |
| `TC_SIDECAR_NODE_HOST` | No | `https://node.tinycloud.xyz` | |
| `TC_SIDECAR_DATA_DIR` | No | `.sidecar-data` | Set to `/data` in Docker (volume mount) |
| `TC_NODE_BIN` | No | `node` | Node binary used to invoke the tc CLI subprocess |

---

## Local dev setup

**1. Generate a key (once)**

```powershell
cd tinycloud-sidecar
bun install
node -e "const {generatePrivateKey,privateKeyToAddress} = require('viem/accounts'); const k = generatePrivateKey(); console.log('key:', k); console.log('address:', privateKeyToAddress(k));"
```

Save the key in `.env` as `TC_SIDECAR_PRIVATE_KEY=0x...`.
The address is your sidecar's DID — share it with the Listen owner when requesting delegation.

**2. Start the sidecar**

```powershell
bun run src/index.ts
```

**3. Verify**

```powershell
Invoke-RestMethod http://localhost:4099/health
# ok: True, hasDelegation: False
```

**4. Get the policy to send to the Listen owner**

```powershell
Invoke-RestMethod http://localhost:4099/internal/policy
```

**5. Store the delegation (after Listen owner sends the JSON)**

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:4099/internal/delegations `
  -ContentType "application/json" `
  -Body '{"serialized":"<JSON from owner>","ownerDid":"did:pkh:eip155:1:0x<owner address>"}'
```

`/health` will now return `hasDelegation: True`.

**6. Test a real ingest**

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/transcripts/ingest `
  -ContentType "application/json" `
  -Body '{"corpus_id":"test-01","mode":"tinycloud"}'
```

---

## Docker Compose

**Local dev** (`docker-compose.yml`): builds from source, runs on the default
Compose network. The `app` service reaches the sidecar at `http://tc-sidecar:4099`
via `TC_SIDECAR_URL`.

```powershell
docker compose up tc-sidecar          # sidecar only
docker compose up                     # everything
```

**Build and push to Docker Hub:**

```powershell
docker compose build tc-sidecar
docker compose push tc-sidecar
```

**Phala deployment** (`docker-compose.phala.yml`): pulls `kkoci/dealproof-tc-sidecar:latest`,
mounts `tc-sidecar-data` volume for delegation persistence. Upload this file to the
Phala dashboard. Add `TC_SIDECAR_PRIVATE_KEY` as a secure env var on the dashboard
— do not put it in the file.

---

## Delegation lifecycle

| Event | Delegation survives? |
|-------|---------------------|
| Container restart | Yes |
| Image update + redeploy | Yes |
| CVM stop + start | Yes (volume persists) |
| New CVM from scratch | No — re-POST delegation |
| Volume explicitly deleted | No — re-POST delegation |
| Delegation expires (if owner set expiry) | No — owner re-issues |

If the same `TC_SIDECAR_PRIVATE_KEY` is used on the new CVM, the Listen owner
does not need to create a new delegation — just re-send the original JSON.

---

## What changed in DealProof

| File | Change |
|------|--------|
| `app/config.py` | Added `tc_sidecar_url` setting |
| `app/api/schemas.py` | Removed `tinycloud_session_token` (no longer needed); `tinycloud_host` now defaults to `settings.tc_sidecar_url` |
| `app/api/routes.py` | `tinycloud` ingest mode calls sidecar instead of bridge; added missing `settings` import |
| `docker-compose.yml` | Added `tc-sidecar` service + `tc-sidecar-data` volume |
| `docker-compose.phala.yml` | Added `tc-sidecar` service + `tc-sidecar-data` volume + `TC_SIDECAR_URL` for `app` |

---

## Reference

- git-haiku backend pattern: `TcCliSecretsProvider` in
  `packages/backend/src/secrets.ts` — the subprocess + temp delegation file
  pattern this sidecar is modelled on
- TinyCloud Listen backend: `TinyCloud/listen/backend/src/` — reference for
  KV/SQL data shapes and delegation patterns
- Ingest route: `app/api/routes.py` → `POST /api/transcripts/ingest`
- Transcript hasher: `app/props/transcript_hasher.py`
