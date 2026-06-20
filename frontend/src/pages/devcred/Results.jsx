import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getDevCredential } from '../../api.js'
import TrustStackBar from '../../components/TrustStackBar.jsx'

const SENIORITY_COLOR = {
  staff:  'text-purple-300 border-purple-700/60 bg-purple-950/40',
  senior: 'text-emerald-300 border-emerald-700/60 bg-emerald-950/40',
  mid:    'text-indigo-300 border-indigo-700/60 bg-indigo-950/40',
  junior: 'text-yellow-300 border-yellow-700/60 bg-yellow-950/40',
}

function CredentialField({ label, children }) {
  return (
    <div>
      <dt className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function HashChip({ hash }) {
  const [copied, setCopied] = useState(false)
  const display = hash ? `${hash.slice(0, 8)}...${hash.slice(-6)}` : '—'

  const copy = () => {
    if (!hash) return
    navigator.clipboard.writeText(hash).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={hash}
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-gray-800/60 border border-gray-700/40 text-xs font-mono text-gray-400 hover:text-gray-200 hover:border-gray-600/60 transition-all"
    >
      {display}
      {copied ? (
        <svg className="w-3 h-3 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
        </svg>
      ) : (
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      )}
    </button>
  )
}

function LanguageTag({ lang }) {
  return (
    <span className="inline-block px-2 py-0.5 rounded-md bg-indigo-950/50 border border-indigo-800/40 text-indigo-300 text-xs font-mono">
      {lang}
    </span>
  )
}

function CredentialCard({ cred }) {
  if (!cred) return null

  const seniorityClass = SENIORITY_COLOR[cred.seniority_level] || SENIORITY_COLOR.junior

  return (
    <div className="rounded-2xl border border-gray-800/60 bg-gray-900/40 overflow-hidden">
      {/* header strip */}
      <div className="px-5 py-4 border-b border-gray-800/40 bg-gray-900/60 flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 mb-1">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
            SeniorDevCredential
          </div>
          <h2 className="text-xl font-bold text-white">@{cred.developer_handle}</h2>
        </div>
        <span className={`px-3 py-1.5 rounded-full border text-sm font-bold uppercase tracking-wide ${seniorityClass}`}>
          {cred.seniority_level}
        </span>
      </div>

      {/* body */}
      <div className="px-5 py-5 space-y-4">
        <dl className="space-y-4">

          <CredentialField label="Languages">
            <div className="flex flex-wrap gap-1.5">
              {cred.primary_languages.map((l) => <LanguageTag key={l} lang={l} />)}
            </div>
          </CredentialField>

          {cred.specializations?.length > 0 && (
            <CredentialField label="Specialisms">
              <div className="flex flex-wrap gap-1.5">
                {cred.specializations.map((s) => (
                  <span key={s} className="inline-block px-2 py-0.5 rounded-md bg-gray-800/50 border border-gray-700/40 text-gray-300 text-xs">
                    {s}
                  </span>
                ))}
              </div>
            </CredentialField>
          )}

          <div className="grid grid-cols-2 gap-4">
            <CredentialField label="Years Active">
              <span className="text-sm font-semibold text-gray-200">{cred.years_active?.toFixed(1)}</span>
            </CredentialField>

            <CredentialField label="Commits">
              <span className="text-sm font-semibold text-gray-200">{cred.commit_count?.toLocaleString()}</span>
            </CredentialField>
          </div>

          <CredentialField label="Test Culture">
            <span className={`text-sm font-semibold ${cred.has_test_culture ? 'text-emerald-400' : 'text-gray-500'}`}>
              {cred.has_test_culture ? '✓ Present' : 'Not detected'}
            </span>
          </CredentialField>

          <CredentialField label="Confidence">
            <span className={`text-sm font-semibold capitalize ${
              cred.confidence === 'high' ? 'text-emerald-400' :
              cred.confidence === 'medium' ? 'text-indigo-400' : 'text-yellow-400'
            }`}>
              {cred.confidence}
            </span>
          </CredentialField>

          <CredentialField label="Assessment">
            <p className="text-sm text-gray-300 leading-relaxed">{cred.qualitative_assessment}</p>
          </CredentialField>

          {cred.caveats?.length > 0 && (
            <CredentialField label="Caveats">
              <ul className="space-y-1">
                {cred.caveats.map((c, i) => (
                  <li key={i} className="text-xs text-gray-500 flex items-start gap-1.5">
                    <span className="text-gray-600 mt-0.5">—</span>
                    <span>{c}</span>
                  </li>
                ))}
              </ul>
            </CredentialField>
          )}

          <div className="pt-2 border-t border-gray-800/40 space-y-2">
            <CredentialField label="Corpus Root">
              <HashChip hash={cred.repo_corpus_root} />
            </CredentialField>
            <CredentialField label="Credential Hash">
              <HashChip hash={cred.credential_hash} />
            </CredentialField>
            <CredentialField label="Issued">
              <span className="text-xs font-mono text-gray-500">
                {cred.issued_at ? new Date(cred.issued_at).toLocaleString() : '—'}
              </span>
            </CredentialField>
          </div>
        </dl>
      </div>
    </div>
  )
}

function ActionBar({ credentialId, credential }) {
  const [copied, setCopied] = useState(false)

  const shareUrl = `${window.location.origin}/devcred/${credentialId}`

  const copyLink = () => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(credential, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `devcred-${credentialId.slice(0, 8)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        onClick={copyLink}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-700/40 hover:border-indigo-600/60 text-indigo-300 text-sm font-medium transition-all"
      >
        {copied ? (
          <svg className="w-4 h-4 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
          </svg>
        )}
        {copied ? 'Copied!' : 'Share'}
      </button>

      {credential && (
        <button
          type="button"
          onClick={downloadJson}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800/60 hover:bg-gray-700/60 border border-gray-700/40 hover:border-gray-600/60 text-gray-300 text-sm font-medium transition-all"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download JSON
        </button>
      )}
    </div>
  )
}

export default function DevCredResults() {
  const { credentialId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!credentialId) return
    getDevCredential(credentialId)
      .then(setData)
      .catch((err) => setError(err.message || 'Failed to load credential'))
      .finally(() => setLoading(false))
  }, [credentialId])

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500 font-mono">Loading credential...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
        <div className="max-w-md w-full text-center">
          <div className="w-12 h-12 rounded-full bg-red-950/40 border border-red-800/40 flex items-center justify-center mx-auto mb-4">
            <svg className="w-6 h-6 text-red-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-white mb-2">Credential not found</h2>
          <p className="text-sm text-gray-500 mb-6">{error}</p>
          <Link
            to="/devcred/new"
            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all"
          >
            Generate a new credential
          </Link>
        </div>
      </div>
    )
  }

  const cred = data?.credential
  const teeAttested = data?.tee_quote && data.tee_quote !== 'mock_tee_quote_simulation'

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10">
      <div className="max-w-4xl mx-auto">

        {/* breadcrumb */}
        <div className="flex items-center gap-2 text-xs font-mono text-gray-600 mb-6">
          <Link to="/devcred/" className="hover:text-gray-400 transition-colors">Dev Credential</Link>
          <span>/</span>
          <span className="text-gray-500">{credentialId?.slice(0, 8)}...</span>
        </div>

        {/* status pill */}
        <div className="flex items-center gap-3 mb-8">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-semibold uppercase tracking-wide ${
              data?.status === 'complete'
                ? 'text-emerald-400 border-emerald-800/60 bg-emerald-950/40'
                : 'text-yellow-400 border-yellow-800/60 bg-yellow-950/40'
            }`}
          >
            <div className={`w-1.5 h-1.5 rounded-full ${data?.status === 'complete' ? 'bg-emerald-400' : 'bg-yellow-400 animate-pulse'}`} />
            {data?.status === 'complete' ? 'Credential Ready' : 'Processing'}
          </span>
          {teeAttested && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-indigo-800/50 bg-indigo-950/40 text-indigo-400 text-xs font-mono">
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              TDX-Attested
            </span>
          )}
        </div>

        {/* two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* credential card — wider column */}
          <div className="lg:col-span-3 space-y-4">
            <CredentialCard cred={cred} />
            {cred && <ActionBar credentialId={credentialId} credential={cred} />}
          </div>

          {/* trust stack — narrower column */}
          <div className="lg:col-span-2 space-y-4">
            <TrustStackBar
              corpusRoot={cred?.repo_corpus_root}
              credentialHash={cred?.credential_hash}
              teeAttested={cred?.tee_attested}
            />

            {/* raw JSON toggle */}
            {data && (
              <details className="group rounded-xl border border-gray-800/40 bg-gray-900/30 overflow-hidden">
                <summary className="flex items-center justify-between px-4 py-3 cursor-pointer select-none text-xs font-mono text-gray-500 hover:text-gray-300 transition-colors">
                  <span>Raw JSON</span>
                  <svg className="w-3.5 h-3.5 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <pre className="px-4 py-3 overflow-x-auto text-[10px] leading-relaxed text-gray-500 border-t border-gray-800/40">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </details>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
