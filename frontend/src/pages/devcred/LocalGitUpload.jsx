import React, { useState } from 'react'

/**
 * Route C (revoked-access fallback) — see app/devcred/routes.py's module docstring
 * for the full three-route design and app/devcred/local_signature.py for the signing
 * contract this component implements the client side of.
 *
 * Division of responsibility (deliberate, not an oversight — see local_signature.py):
 *   - THIS COMPONENT reads the local .git folder and does a structural pre-check only
 *     (does the pasted signature look like a well-formed armor block, does the public
 *     key look like a valid ssh-ed25519 line). That's a fast-fail UX convenience.
 *   - The SERVER performs the actual cryptographic verification. Never trust an
 *     unverified client claim of "I checked this myself" for something called a
 *     verified credential — that would collapse this into Route D in all but name.
 *   - This component never asks for a private key. The user runs `ssh-keygen -Y sign`
 *     themselves, outside the browser, and pastes the already-produced signature.
 *
 * Only aggregate commit metadata (sha, author name, timestamp, message) ever leaves
 * this component — no file paths, no diffs. Diff stats are NOT computed here (no
 * in-browser tree-diffing in this pass — flagged, not silently narrowed, see the
 * "not attempted" note in the UI copy below).
 *
 * Git object support: loose objects only. A repo that has been `git gc`'d into
 * packfiles will only yield the commits still reachable as loose objects — this
 * shows up as a partial-coverage note, not a silent undercount.
 *
 * NOT verified in a live browser in this environment (no local signed git repo
 * available to click-through test here) — same disclosed limitation this codebase
 * already applies elsewhere to frontend-only passes (see CLAUDE.md's Offer Check
 * Session UX section). Review carefully, and test against a real .git folder with
 * SSH-signed commits, before relying on this in production.
 */

const MAX_LOCAL_COMMITS = 300
const SIGNING_NAMESPACE = 'devcred-route-c'

function bytesToHex(bytes) {
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('')
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return bytesToHex(new Uint8Array(digest))
}

async function inflateZlib(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

async function readLooseObject(gitDirHandle, sha) {
  const objectsHandle = await gitDirHandle.getDirectoryHandle('objects')
  const subDirHandle = await objectsHandle.getDirectoryHandle(sha.slice(0, 2))
  const fileHandle = await subDirHandle.getFileHandle(sha.slice(2))
  const file = await fileHandle.getFile()
  const compressed = new Uint8Array(await file.arrayBuffer())
  const raw = await inflateZlib(compressed)
  const nullIdx = raw.indexOf(0)
  const header = new TextDecoder().decode(raw.slice(0, nullIdx))
  const [type] = header.split(' ')
  return { type, content: raw.slice(nullIdx + 1) }
}

function parseCommitObject(contentBytes) {
  const text = new TextDecoder().decode(contentBytes)
  const lines = text.split('\n')
  let i = 0
  const parents = []
  let authorLine = null
  let hasSignature = false

  while (i < lines.length && lines[i] !== '') {
    const line = lines[i]
    if (line.startsWith('parent ')) {
      parents.push(line.slice(7).trim())
      i++
    } else if (line.startsWith('author ')) {
      authorLine = line.slice(7)
      i++
    } else if (line.startsWith('gpgsig ')) {
      hasSignature = true
      i++
      while (i < lines.length && lines[i].startsWith(' ')) i++
    } else {
      i++
    }
  }
  const message = lines.slice(i + 1).join('\n').trim()

  let author = null
  let timestamp = null
  if (authorLine) {
    const m = authorLine.match(/^(.*) <[^>]*> (\d+) ([+-]\d{4})$/)
    if (m) {
      author = m[1]
      timestamp = new Date(parseInt(m[2], 10) * 1000).toISOString()
    }
  }

  return { parents, author, timestamp, message, hasSignature }
}

async function resolveHeadSha(gitDirHandle) {
  const headFile = await (await gitDirHandle.getFileHandle('HEAD')).getFile()
  const headText = (await headFile.text()).trim()
  if (!headText.startsWith('ref: ')) return headText

  const refPath = headText.slice(5)
  const parts = refPath.split('/')
  try {
    let handle = gitDirHandle
    for (const p of parts.slice(0, -1)) handle = await handle.getDirectoryHandle(p)
    const refFile = await (await handle.getFileHandle(parts[parts.length - 1])).getFile()
    return (await refFile.text()).trim()
  } catch {
    // Ref not loose — fall back to packed-refs (common after `git gc`).
    const packedFile = await (await gitDirHandle.getFileHandle('packed-refs')).getFile()
    const text = await packedFile.text()
    for (const line of text.split('\n')) {
      if (line.endsWith(' ' + refPath)) return line.split(' ')[0]
    }
    throw new Error(`Could not resolve ${refPath} (not a loose ref, not in packed-refs)`)
  }
}

async function walkLocalRepo(gitDirHandle) {
  const headSha = await resolveHeadSha(gitDirHandle)
  const seen = new Set()
  const queue = [headSha]
  const commits = []
  let hitUnreadableObject = false
  let signedCount = 0

  while (queue.length > 0 && commits.length < MAX_LOCAL_COMMITS) {
    const sha = queue.shift()
    if (seen.has(sha)) continue
    seen.add(sha)

    let obj
    try {
      obj = await readLooseObject(gitDirHandle, sha)
    } catch {
      hitUnreadableObject = true // likely packed into a packfile — not read in this pass
      continue
    }
    if (obj.type !== 'commit') continue

    const parsed = parseCommitObject(obj.content)
    if (parsed.hasSignature) signedCount += 1
    commits.push({
      sha,
      author: parsed.author,
      timestamp: parsed.timestamp,
      message: parsed.message,
      diff_stat: null, // no in-browser tree-diffing in this pass — see module docstring
    })
    for (const p of parsed.parents) queue.push(p)
  }

  return { commits, hitUnreadableObject, signedCount }
}

async function computeCorpusRootClientSide(commits) {
  // Mirrors app/devcred/git_hasher.hash_commit() + compute_repo_corpus_root() exactly:
  // per-commit SHA-256 of {author, diff_stat, message, sha, timestamp} (Python's default
  // json.dumps(sort_keys=True) separators/escaping), then a length-prefixed Merkle root.
  // This value is for the user's own visibility and for constructing the signing
  // payload — the SERVER independently recomputes it from the submitted commits and
  // never trusts this one, so a mismatch here fails a signature check, not a security
  // check (see LocalGitUpload.jsx's module docstring).
  function pyJsonDumps(value) {
    if (value === null || value === undefined) return 'null'
    if (typeof value === 'number') return String(value)
    if (typeof value === 'string') {
      let out = '"'
      for (const ch of value) {
        const code = ch.codePointAt(0)
        if (ch === '"') out += '\\"'
        else if (ch === '\\') out += '\\\\'
        else if (ch === '\n') out += '\\n'
        else if (ch === '\r') out += '\\r'
        else if (ch === '\t') out += '\\t'
        else if (code < 0x20) out += '\\u' + code.toString(16).padStart(4, '0')
        else if (code > 0x7e) out += '\\u' + code.toString(16).padStart(4, '0')
        else out += ch
      }
      return out + '"'
    }
    if (Array.isArray(value)) return '[' + value.map(pyJsonDumps).join(', ') + ']'
    const keys = Object.keys(value).sort()
    return '{' + keys.map((k) => pyJsonDumps(k) + ': ' + pyJsonDumps(value[k])).join(', ') + '}'
  }

  async function hashCommit(c) {
    const canonical = {
      author: c.author ?? null,
      diff_stat: c.diff_stat ?? null,
      message: c.message ?? '',
      sha: c.sha,
      timestamp: c.timestamp ?? null,
    }
    const bytes = new TextEncoder().encode(pyJsonDumps(canonical))
    return sha256Hex(bytes)
  }

  const hashes = await Promise.all(commits.map(hashCommit))
  const lengthPrefix = new Uint8Array(4)
  new DataView(lengthPrefix.buffer).setUint32(0, hashes.length, false)
  const hashBytes = hashes.map((h) => {
    const arr = new Uint8Array(32)
    for (let i = 0; i < 32; i++) arr[i] = parseInt(h.slice(i * 2, i * 2 + 2), 16)
    return arr
  })
  const total = new Uint8Array(4 + hashes.length * 32)
  total.set(lengthPrefix, 0)
  hashBytes.forEach((arr, idx) => total.set(arr, 4 + idx * 32))
  return sha256Hex(total)
}

function canonicalSigningPayload(credentialId, developerHandle, corpusRoot) {
  // Must match app/devcred/local_signature.canonical_payload() exactly: sorted keys,
  // no extra whitespace. All three values are plain ASCII (UUID / GitHub handle / hex
  // hash), so native JSON.stringify's escaping is safe here without a custom serializer.
  const obj = { credential_id: credentialId, developer_handle: developerHandle, corpus_root: corpusRoot }
  const keys = Object.keys(obj).sort()
  return '{' + keys.map((k) => JSON.stringify(k) + ':' + JSON.stringify(obj[k])).join(',') + '}'
}

function looksLikeSshSignatureArmor(text) {
  const t = text.trim()
  return t.startsWith('-----BEGIN SSH SIGNATURE-----') && t.endsWith('-----END SSH SIGNATURE-----')
}

function looksLikeSshPublicKeyLine(text) {
  return /^ssh-ed25519\s+[A-Za-z0-9+/=]+/.test(text.trim())
}

export default function LocalGitUpload({ credentialId, developerHandle, onComplete, onError }) {
  const [phase, setPhase] = useState('idle') // idle | scanning | scanned | submitting
  const [scanResult, setScanResult] = useState(null)
  const [corpusRoot, setCorpusRoot] = useState('')
  const [signature, setSignature] = useState('')
  const [publicKey, setPublicKey] = useState('')
  const [formError, setFormError] = useState('')

  const fsApiSupported = typeof window !== 'undefined' && !!window.showDirectoryPicker

  const handlePickFolder = async () => {
    setFormError('')
    setPhase('scanning')
    try {
      const rootHandle = await window.showDirectoryPicker()
      // Accept either the repo root (containing .git) or the .git folder itself.
      let gitDirHandle = rootHandle
      try {
        gitDirHandle = await rootHandle.getDirectoryHandle('.git')
      } catch {
        // assume the user selected the .git folder directly
      }

      const { commits, hitUnreadableObject, signedCount } = await walkLocalRepo(gitDirHandle)
      if (commits.length === 0) {
        throw new Error('No commits could be read from this folder — is it a git repository?')
      }
      const root = await computeCorpusRootClientSide(commits)
      setScanResult({ commits, hitUnreadableObject, signedCount })
      setCorpusRoot(root)
      setPhase('scanned')
    } catch (err) {
      setFormError(err.message || 'Could not read the selected folder')
      setPhase('idle')
    }
  }

  const payloadToSign = corpusRoot ? canonicalSigningPayload(credentialId, developerHandle, corpusRoot) : ''

  const structuralCheckPassed =
    signature.trim() && publicKey.trim()
      ? looksLikeSshSignatureArmor(signature) && looksLikeSshPublicKeyLine(publicKey)
      : false

  const handleSubmit = async () => {
    setFormError('')
    if (!structuralCheckPassed) {
      setFormError('Signature or public key does not look well-formed — see the format hints above.')
      return
    }
    setPhase('submitting')
    try {
      const { ingestLocalGit, evaluateDevCredential } = await import('../../api.js')
      const commitsForUpload = scanResult.commits.map(({ sha, author, timestamp, message, diff_stat }) => ({
        sha, author, timestamp, message, diff_stat,
      }))
      await ingestLocalGit({
        credential_id: credentialId,
        developer_handle: developerHandle,
        commits: commitsForUpload,
        signature: signature.trim(),
        signature_format: 'ssh',
        public_key: publicKey.trim(),
      })
      await evaluateDevCredential(credentialId)
      onComplete?.()
    } catch (err) {
      setFormError(err.message || 'Submission failed')
      setPhase('scanned')
      onError?.(err)
    }
  }

  if (!fsApiSupported) {
    return (
      <div className="rounded-lg bg-yellow-950/30 border border-yellow-800/50 px-4 py-3 text-sm text-yellow-300">
        Local folder upload needs the File System Access API, which this browser doesn't support.
        Try a recent Chrome or Edge, or use the unverified self-report option instead.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-indigo-800/40 bg-indigo-950/10 p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-indigo-300">Upload from a local repository</h3>
        <p className="mt-1 text-xs text-gray-500 leading-relaxed">
          For repos you left more than GitHub's ~30-day activity window ago, where the account
          itself no longer has enough recent history to fall back on. If you still have a local
          clone, we can verify your authorship from it instead — commit messages and metadata
          only, never file contents, diffs, or file paths.
        </p>
      </div>

      {phase === 'idle' && (
        <button
          type="button"
          onClick={handlePickFolder}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all"
        >
          Select local repository folder…
        </button>
      )}

      {phase === 'scanning' && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          Reading commit history…
        </div>
      )}

      {(phase === 'scanned' || phase === 'submitting') && scanResult && (
        <div className="space-y-4">
          <div className="text-sm text-gray-300">
            Found <span className="font-semibold text-white">{scanResult.commits.length}</span> commit(s)
            {scanResult.signedCount > 0 && (
              <span className="text-emerald-400"> · {scanResult.signedCount} appear signed locally</span>
            )}
            {scanResult.hitUnreadableObject && (
              <p className="mt-1 text-xs text-yellow-500/80">
                Some history couldn't be read (likely packed by `git gc` — only loose objects are
                supported in this version). Showing partial history.
              </p>
            )}
          </div>

          <div className="rounded-lg bg-gray-950/60 border border-gray-800/60 p-3 space-y-2">
            <p className="text-xs text-gray-500">
              Sign the following exact text with an SSH key GitHub has ever associated with your
              account, then paste the result below. This does not require your local git history to
              be signed — it's a fresh, one-time attestation over what you're submitting right now.
            </p>
            <code className="block text-xs font-mono text-gray-300 bg-gray-900/60 rounded px-2 py-1.5 overflow-x-auto whitespace-pre">
              {`printf '%s' '${payloadToSign}' > /tmp/devcred-payload
ssh-keygen -Y sign -n ${SIGNING_NAMESPACE} -f ~/.ssh/id_ed25519 /tmp/devcred-payload
# paste the contents of /tmp/devcred-payload.sig below, and your ~/.ssh/id_ed25519.pub`}
            </code>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
              Signature (.sig file contents)
            </label>
            <textarea
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
              rows={4}
              placeholder="-----BEGIN SSH SIGNATURE-----&#10;...&#10;-----END SSH SIGNATURE-----"
              className="w-full px-3 py-2 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            {signature.trim() && !looksLikeSshSignatureArmor(signature) && (
              <p className="mt-1 text-xs text-red-400">
                Doesn't look like an SSH signature block — check you pasted the full .sig file.
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
              Public key (id_ed25519.pub contents)
            </label>
            <input
              type="text"
              value={publicKey}
              onChange={(e) => setPublicKey(e.target.value)}
              placeholder="ssh-ed25519 AAAA..."
              className="w-full px-3 py-2 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            />
            {publicKey.trim() && !looksLikeSshPublicKeyLine(publicKey) && (
              <p className="mt-1 text-xs text-red-400">
                Only ssh-ed25519 keys are supported in this version — RSA/ECDSA keys are rejected.
              </p>
            )}
          </div>

          {formError && <p className="text-xs text-red-400">{formError}</p>}

          <button
            type="button"
            onClick={handleSubmit}
            disabled={!structuralCheckPassed || phase === 'submitting'}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {phase === 'submitting' ? 'Verifying…' : 'Submit signed metrics'}
          </button>
          <p className="text-[11px] text-gray-600">
            The signature is cryptographically verified server-side, inside the enclave — pasting a
            well-formed-looking block here doesn't verify it, it only formats it correctly.
          </p>
        </div>
      )}

      {formError && phase === 'idle' && <p className="text-xs text-red-400">{formError}</p>}
    </div>
  )
}
