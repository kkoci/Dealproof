import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestRepos, evaluateDevCredential, getEnclaveAttestation } from '../../api.js'

function RepoTag({ repo, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-indigo-950/60 border border-indigo-800/50 text-indigo-300 text-xs font-mono">
      {repo}
      <button
        type="button"
        onClick={onRemove}
        className="text-indigo-500 hover:text-indigo-200 transition-colors ml-0.5"
        aria-label={`Remove ${repo}`}
      >
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </span>
  )
}

function ProgressStep({ label, status }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
        {status === 'done' && (
          <svg className="w-5 h-5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
        )}
        {status === 'loading' && (
          <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        )}
        {status === 'pending' && (
          <div className="w-3 h-3 rounded-full bg-gray-700 border border-gray-600" />
        )}
      </div>
      <span className={`text-sm ${
        status === 'done' ? 'text-emerald-400' :
        status === 'loading' ? 'text-indigo-300' : 'text-gray-600'
      }`}>
        {label}
      </span>
    </div>
  )
}

// Mirrors devcred/Landing.jsx's TrustPill styling (emerald check + gray pill) —
// kept local since Landing.jsx doesn't export it.
function TrustPill({ children }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-gray-800/60 border border-gray-700/40 text-gray-400 text-xs font-medium">
      <svg className="w-3 h-3 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
      {children}
    </span>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all bg-gray-700/60 hover:bg-gray-600/60 text-gray-300 hover:text-white border border-gray-600/40 hover:border-gray-500/60 flex-shrink-0"
      title="Copy"
    >
      {copied ? (
        <>
          <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-emerald-400">Copied</span>
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          Copy
        </>
      )}
    </button>
  )
}

function EvidenceField({ label, value }) {
  if (!value) return null
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-1">{label}</div>
      <div className="flex items-center gap-2">
        <code className="flex-1 text-xs font-mono text-gray-300 bg-gray-950/60 rounded-lg px-3 py-2 border border-gray-800/60 break-all leading-relaxed">
          {value}
        </code>
        <CopyButton text={value} />
      </div>
    </div>
  )
}

function ClaimRow({ label, children }) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 border-b border-gray-800/30 last:border-0">
      <span className="mt-1.5 w-2 h-2 rounded-full bg-emerald-500 flex-shrink-0" />
      <div className="min-w-0">
        <div className="text-sm font-medium text-gray-200">{label}</div>
        <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{children}</p>
      </div>
    </div>
  )
}

function ChevronIcon({ open }) {
  return (
    <svg
      className={`w-3.5 h-3.5 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
      fill="none" stroke="currentColor" viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  )
}

// "Verification Center" — redpill.ai-style slide-out panel triggered by a
// header pill, ported on top of GET /api/attest (see devcred_attestation_ux_fix.md).
function VerificationCenter({ attestation, attestationLoading, attestationError, onVerifyAgain }) {
  const [expanded, setExpanded] = useState(false)
  const [rawExpanded, setRawExpanded] = useState(false)

  const status = attestationLoading ? 'loading' : attestationError ? 'error' : 'verified'
  const pillStyles = {
    loading: 'bg-gray-800/60 text-gray-400 border-gray-700/40',
    error: 'bg-red-950/40 text-red-300 border-red-800/50',
    verified: 'bg-emerald-950/40 text-emerald-300 border-emerald-700/50',
  }[status]
  const pillLabel = {
    loading: 'Verifying enclave…',
    error: 'Attestation failed',
    verified: '✓ TDX Verified',
  }[status]

  const curlCmd = `curl ${typeof window !== 'undefined' ? window.location.origin : ''}/api/attest`

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        disabled={attestationLoading}
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all disabled:cursor-wait ${pillStyles}`}
      >
        {attestationLoading && (
          <div className="w-3 h-3 border border-gray-400 border-t-transparent rounded-full animate-spin" />
        )}
        {pillLabel}
        <ChevronIcon open={expanded} />
      </button>

      {expanded && (
        <div className="mt-3 rounded-xl border border-gray-800/60 bg-gray-900/40 overflow-hidden">
          {/* Attestor row */}
          <div className="px-4 py-3 border-b border-gray-800/40 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-950/60 border border-indigo-800/50 flex items-center justify-center flex-shrink-0">
              <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-gray-200">
                Attested by <span className="text-indigo-300">Intel</span>
              </div>
              <div className="text-xs text-gray-500">
                via DCAP — Intel TDX hardware-rooted attestation
              </div>
            </div>
          </div>

          {/* Claim rows */}
          <ClaimRow label="Token Never Persisted">
            Your GitHub token is used once inside the TEE and immediately discarded.
            Not even DealProof can retrieve it after the request completes.
          </ClaimRow>
          <ClaimRow label="Verified Software">
            Attestation cryptographically proves the code running inside the TEE
            matches the published source — no backdoors, no undisclosed modifications.
          </ClaimRow>
          <ClaimRow label="Confidential Hardware">
            Runs on Intel TDX-attested hardware with hardware-rooted attestation
            proofs you can independently verify.
          </ClaimRow>

          {attestationError && (
            <div className="mx-4 my-3 flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-red-950/40 border border-red-800/50">
              <svg className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-sm text-red-300">{attestationError}</span>
            </div>
          )}

          {/* Raw evidence */}
          {attestation && (
            <>
              <button
                type="button"
                onClick={() => setRawExpanded((v) => !v)}
                className="w-full flex items-center justify-between px-4 py-3 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-gray-200 transition-colors border-t border-gray-800/40"
              >
                Show raw attestation data
                <ChevronIcon open={rawExpanded} />
              </button>
              {rawExpanded && (
                <div className="px-4 pb-4 space-y-3">
                  <EvidenceField label="Quote" value={attestation.quote} />
                  <EvidenceField label="MRENCLAVE" value={attestation.mrenclave} />
                  <EvidenceField label="Timestamp" value={attestation.timestamp != null ? String(attestation.timestamp) : null} />
                  <EvidenceField label="Verify independently" value={curlCmd} />
                </div>
              )}
            </>
          )}

          {/* Verify again */}
          <div className="px-4 py-3 border-t border-gray-800/40">
            <button
              type="button"
              onClick={onVerifyAgain}
              disabled={attestationLoading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 hover:text-indigo-300 border border-indigo-700/40 hover:border-indigo-600/60 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {attestationLoading ? (
                <>
                  <div className="w-3 h-3 border border-indigo-400 border-t-transparent rounded-full animate-spin" />
                  Verifying...
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  Verify Again
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function DevCredSetup() {
  const navigate = useNavigate()
  const [token, setToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [repoInput, setRepoInput] = useState('')
  const [repos, setRepos] = useState([])
  const [repoError, setRepoError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [steps, setSteps] = useState({ ingest: 'pending', evaluate: 'pending' })
  const [error, setError] = useState('')
  const tokenRef = useRef(null)

  // Verify, then release: fetch the enclave attestation before the form
  // becomes usable (Hang Yin / Phala feedback, July 20 2026).
  const [attestation, setAttestation] = useState(null)
  const [attestationLoading, setAttestationLoading] = useState(true)
  const [attestationError, setAttestationError] = useState('')

  const fetchAttestation = useCallback(async () => {
    setAttestationLoading(true)
    setAttestationError('')
    try {
      const data = await getEnclaveAttestation()
      setAttestation(data)
    } catch (err) {
      setAttestation(null)
      setAttestationError(err.message || 'Enclave attestation could not be verified')
    } finally {
      setAttestationLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAttestation()
  }, [fetchAttestation])

  const attestationVerified = !!attestation && !attestationError

  const addRepo = () => {
    const val = repoInput.trim()
    if (!val) return
    if (!/^[^/\s]+\/[^/\s]+$/.test(val)) {
      setRepoError('Format must be owner/repo')
      return
    }
    if (repos.includes(val)) {
      setRepoError('Repo already added')
      return
    }
    setRepos((prev) => [...prev, val])
    setRepoInput('')
    setRepoError('')
  }

  const handleRepoKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addRepo()
    }
  }

  const removeRepo = (repo) => setRepos((prev) => prev.filter((r) => r !== repo))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!attestationVerified) { setError('Enclave attestation must be verified before submitting'); return }
    if (!token.trim()) { setError('GitHub token is required'); return }
    if (repos.length === 0) { setError('Add at least one repo'); return }

    setError('')
    setSubmitting(true)

    const credentialId = crypto.randomUUID()

    // Clear token from state immediately after capturing it
    const capturedToken = token.trim()
    setToken('')
    setShowToken(false)

    try {
      // Step 1: ingest
      setSteps({ ingest: 'loading', evaluate: 'pending' })
      await ingestRepos({
        github_token: capturedToken,
        repos,
        credential_id: credentialId,
      })
      setSteps({ ingest: 'done', evaluate: 'loading' })

      // Step 2: evaluate
      await evaluateDevCredential(credentialId)
      setSteps({ ingest: 'done', evaluate: 'done' })

      // Navigate to results
      navigate(`/devcred/${credentialId}`)
    } catch (err) {
      setError(err.message || 'Something went wrong')
      setSteps({ ingest: 'pending', evaluate: 'pending' })
      setSubmitting(false)
    }
  }

  const canSubmit = attestationVerified && token.trim() && repos.length > 0 && !submitting
  const inputsDisabled = submitting || !attestationVerified

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">

        {/* header */}
        <div className="mb-6">
          <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 mb-2">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
            Dev Credential
          </div>
          <h1 className="text-2xl font-bold text-white">Generate your credential</h1>
          <p className="mt-1 text-sm text-gray-500 leading-relaxed">
            Your token is used once inside the TEE and immediately discarded.
            Repo names and diffs are never stored — only aggregate metrics.
          </p>
        </div>

        {/* Verify, then release — attestation must resolve before the form unlocks */}
        <div className="mb-6">
          <VerificationCenter
            attestation={attestation}
            attestationLoading={attestationLoading}
            attestationError={attestationError}
            onVerifyAgain={fetchAttestation}
          />
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Inside the TEE — emerald visual boundary around the two fields that send data into the enclave */}
          <div className="border border-emerald-800/50 bg-emerald-950/10 rounded-xl p-4 space-y-5">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
                  Inside the TEE — encrypted in transit, discarded after use
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <TrustPill>Intel TDX</TrustPill>
                <TrustPill>DCAP verified</TrustPill>
                <TrustPill>Token discarded after use</TrustPill>
              </div>
            </div>

            {/* GitHub token */}
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                GitHub Token
                <span className="ml-2 text-gray-600 normal-case font-normal">read-only scope (repo:read)</span>
              </label>
              <div className="relative">
                <input
                  ref={tokenRef}
                  type={showToken ? 'text' : 'password'}
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  autoComplete="off"
                  disabled={inputsDisabled}
                  className="w-full px-3 py-2.5 pr-10 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={() => setShowToken((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition-colors"
                  tabIndex={-1}
                >
                  {showToken ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
              {!attestationVerified ? (
                <p className="mt-1.5 text-xs text-yellow-500/80 flex items-center gap-1.5">
                  {attestationLoading && (
                    <div className="w-3 h-3 border border-yellow-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                  )}
                  {attestationLoading
                    ? 'Verifying enclave attestation before enabling input…'
                    : 'Input disabled — enclave attestation could not be verified.'}
                </p>
              ) : (
                <p className="mt-1.5 text-xs text-gray-600">
                  Token is sent once and never stored. Generate at{' '}
                  <a
                    href="https://github.com/settings/tokens"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2"
                  >
                    github.com/settings/tokens
                  </a>
                </p>
              )}
            </div>

            {/* Repos */}
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
                Repositories
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={repoInput}
                  onChange={(e) => { setRepoInput(e.target.value); setRepoError('') }}
                  onKeyDown={handleRepoKeyDown}
                  placeholder="owner/repo"
                  disabled={inputsDisabled}
                  className="flex-1 min-w-0 px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={addRepo}
                  disabled={!repoInput.trim() || inputsDisabled}
                  className="px-4 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-sm font-medium border border-gray-600/40 hover:border-gray-500/60 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Add
                </button>
              </div>
              {repoError && <p className="mt-1 text-xs text-red-400">{repoError}</p>}

              {repos.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {repos.map((r) => (
                    <RepoTag key={r} repo={r} onRemove={() => removeRepo(r)} />
                  ))}
                </div>
              )}
              {repos.length === 0 && !submitting && (
                <p className="mt-1.5 text-xs text-gray-600">Add one or more repos. Press Enter or click Add.</p>
              )}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg bg-red-950/40 border border-red-800/50">
              <svg className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <span className="text-sm text-red-300">{error}</span>
            </div>
          )}

          {/* Progress */}
          {submitting && (
            <div className="rounded-lg bg-gray-900/60 border border-gray-800/60 px-4 py-4 space-y-3">
              <ProgressStep label="Fetching commits from GitHub..." status={steps.ingest} />
              <ProgressStep label="Analysing with AI inside TEE..." status={steps.evaluate} />
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full flex items-center justify-center gap-2 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-none"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Analysing...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Analyse
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
