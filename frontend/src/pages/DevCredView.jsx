import React, { useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import TrustStackBar from '../components/TrustStackBar.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function short(h) {
  if (!h) return '—'
  return `${h.slice(0, 16)}…`
}

const SENIORITY_COLOR = {
  junior: 'text-yellow-400 border-yellow-800/50 bg-yellow-950/30',
  mid:    'text-blue-400  border-blue-800/50  bg-blue-950/30',
  senior: 'text-emerald-400 border-emerald-800/50 bg-emerald-950/30',
  staff:  'text-teal-400 border-teal-800/50 bg-teal-950/30',
}

// ---------------------------------------------------------------------------
// Credential card
// ---------------------------------------------------------------------------

function CredentialCard({ cred }) {
  const [copied, setCopied] = useState(false)

  function download() {
    const blob = new Blob([JSON.stringify(cred, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `dev-credential-${cred.credential_id?.slice(0, 8)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function copyCredential() {
    navigator.clipboard?.writeText(JSON.stringify(cred, null, 2)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const seniorityClass = SENIORITY_COLOR[cred.seniority_level] || SENIORITY_COLOR.junior

  return (
    <div className="rounded-2xl border border-gray-700/60 bg-gray-900/30 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-teal-400 animate-pulse" />
          <h2 className="text-xs font-semibold text-teal-400 uppercase tracking-widest">
            Dev Credential · Attested
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={copyCredential}
            className="p-1.5 rounded-md border border-gray-700/40 text-gray-500 hover:text-gray-200 hover:border-gray-600 transition-colors"
            title="Copy JSON"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
          </button>
          <button
            onClick={download}
            className="p-1.5 rounded-md border border-gray-700/40 text-gray-500 hover:text-gray-200 hover:border-gray-600 transition-colors"
            title="Download JSON"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="px-5 py-5 space-y-4">
        {/* Seniority */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">SENIORITY</p>
            <div className="flex items-center gap-2">
              <span className={`text-lg font-bold font-mono capitalize ${seniorityClass.split(' ')[0]}`}>
                {cred.seniority_level}
              </span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${seniorityClass}`}>
                hard floor: {cred.hard_seniority_signal}
              </span>
            </div>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">YEARS ACTIVE</p>
            <p className="text-xl font-bold font-mono text-gray-200">{cred.years_active}</p>
          </div>
        </div>

        {/* Languages */}
        {cred.primary_languages?.length > 0 && (
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5">LANGUAGES</p>
            <div className="flex flex-wrap gap-1.5">
              {cred.primary_languages.map((lang) => (
                <span key={lang} className="text-xs px-2.5 py-0.5 rounded-md bg-indigo-950/50 border border-indigo-800/40 text-indigo-300 font-mono">
                  {lang}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Specializations */}
        {cred.specializations?.length > 0 && (
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5">SPECIALISMS</p>
            <div className="flex flex-wrap gap-1.5">
              {cred.specializations.map((s) => (
                <span key={s} className="text-xs px-2.5 py-0.5 rounded-md bg-gray-800/60 border border-gray-700/40 text-gray-300">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Attributes */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">TEST CULTURE</p>
            <p className={`text-xs font-semibold ${cred.has_test_culture ? 'text-emerald-400' : 'text-gray-500'}`}>
              {cred.has_test_culture ? '✓ yes' : '✗ not detected'}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">CONFIDENCE</p>
            <p className={`text-xs font-semibold capitalize ${cred.confidence === 'high' ? 'text-emerald-400' : cred.confidence === 'medium' ? 'text-yellow-400' : 'text-gray-500'}`}>
              {cred.confidence}
            </p>
          </div>
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">COMMITS</p>
            <p className="text-xs text-gray-300 font-mono">{cred.commit_count?.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">DEVELOPER</p>
            <p className="text-xs text-gray-300 font-mono truncate">{cred.developer_handle || '—'}</p>
          </div>
        </div>

        {/* Assessment */}
        {cred.qualitative_assessment && (
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">ASSESSMENT</p>
            <p className="text-xs text-gray-400 italic leading-relaxed">&ldquo;{cred.qualitative_assessment}&rdquo;</p>
          </div>
        )}

        {/* Caveats */}
        {cred.caveats?.length > 0 && (
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">CAVEATS</p>
            <ul className="space-y-0.5">
              {cred.caveats.map((c, i) => (
                <li key={i} className="text-xs text-amber-400 flex items-start gap-1.5">
                  <span className="mt-0.5 flex-shrink-0">·</span>
                  {c}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Hashes */}
        <div className="border-t border-gray-800/40 pt-3 space-y-2">
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">CORPUS ROOT</p>
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-mono text-gray-500 truncate">{short(cred.repo_corpus_root)}</p>
            </div>
          </div>
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">CREDENTIAL HASH</p>
            <p className="text-xs font-mono text-teal-400 break-all">{cred.credential_hash}</p>
          </div>
        </div>

        {/* Privacy note */}
        <div className="rounded-lg bg-gray-900/40 border border-gray-800/30 px-3 py-2.5">
          <p className="text-[10px] text-gray-600 leading-relaxed">
            Repo names, employer names, and file paths were never exposed to this credential or to DealProof.
            Only computed ratios and aggregate metrics appear above.
          </p>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DevCredView() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const cred = location.state?.cred

  if (!cred) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
        <div className="max-w-md text-center space-y-4">
          <p className="text-gray-300">Dev credential not found in session.</p>
          <p className="text-sm text-gray-600">Credential ID: <span className="font-mono">{id}</span></p>
          <button
            onClick={() => navigate('/devcred')}
            className="px-4 py-2 bg-teal-700 hover:bg-teal-600 text-white rounded-lg text-sm transition-colors"
          >
            Back to Dev Credentials
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-5xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span className="text-teal-400">Dev Credential</span>
            <span>/</span>
            <span className="text-gray-400 truncate max-w-[180px]">{id}</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-1">
            Senior Dev Credential
          </h1>
          <p className="text-sm text-gray-500">
            Issued from authenticated commit history inside Intel TDX.
          </p>
        </div>

        {/* Two-panel layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left — credential card */}
          <CredentialCard cred={cred} />

          {/* Right — trust stack */}
          <TrustStackBar
            corpusRoot={cred.repo_corpus_root}
            credentialHash={cred.credential_hash}
            teeQuote={cred.tee_quote}
          />
        </div>

      </div>
    </div>
  )
}
