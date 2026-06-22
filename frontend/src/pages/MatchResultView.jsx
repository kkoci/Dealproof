import React, { useState, useEffect } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { getMatch } from '../api.js'
import TrustStackBar from '../components/TrustStackBar.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function fmtThreshold(metric, val) {
  if (val == null) return '—'
  if (metric === 'runway') return `${val} months`
  return pct(val)
}

// ---------------------------------------------------------------------------
// Overall match banner
// ---------------------------------------------------------------------------

function MatchBanner({ overall_match }) {
  return (
    <div
      className={`rounded-xl border px-5 py-4 flex items-center gap-4 ${
        overall_match
          ? 'bg-emerald-950/20 border-emerald-800/40'
          : 'bg-red-950/20 border-red-800/40'
      }`}
    >
      <div
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
          overall_match ? 'bg-emerald-950/50 border border-emerald-700/60' : 'bg-red-950/50 border border-red-700/60'
        }`}
      >
        {overall_match ? (
          <svg className="w-5 h-5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        )}
      </div>
      <div>
        <p className={`text-base font-bold ${overall_match ? 'text-emerald-300' : 'text-red-300'}`}>
          {overall_match ? 'All thresholds met — MATCH' : 'One or more thresholds not met — NO MATCH'}
        </p>
        <p className="text-xs text-gray-500 mt-0.5">
          Computed inside the TEE. Neither party saw the other's raw data.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Investor view — full per-metric table
// ---------------------------------------------------------------------------

function InvestorMetricTable({ metricResults }) {
  if (!metricResults?.length) return null

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          Your Threshold Results
        </h3>
      </div>
      <div className="divide-y divide-gray-800/30">
        {metricResults.map((m) => {
          const hasThreshold = m.investor_threshold != null
          if (!hasThreshold) return null
          return (
            <div
              key={m.metric}
              className={`px-4 py-3 flex items-center gap-3 ${!m.passed ? 'bg-red-950/10' : ''}`}
            >
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
                  m.passed
                    ? 'bg-emerald-950/50 border border-emerald-700/60'
                    : 'bg-red-950/50 border border-red-700/60'
                }`}
              >
                {m.passed ? (
                  <svg className="w-2.5 h-2.5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-2.5 h-2.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
              <span className="text-sm text-gray-300 flex-1">{m.label}</span>
              <span className="text-xs font-mono text-gray-500">
                threshold: {fmtThreshold(m.metric, m.investor_threshold)}
              </span>
              <span
                className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border flex-shrink-0 ${
                  m.passed
                    ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50'
                    : 'bg-red-950/50 text-red-300 border-red-800/50'
                }`}
              >
                {m.passed ? 'PASS' : 'FAIL'}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Founder view — disclosure-aware panel
// ---------------------------------------------------------------------------

function FounderDisclosurePanel({ view }) {
  const { disclosure_level, failed_metrics, checked_metric_count, metric_results } = view

  if (disclosure_level === 'none') {
    return (
      <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 px-5 py-5">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Disclosure</p>
        <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-gray-800/30 border border-gray-700/40">
          <svg className="w-4 h-4 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
          </svg>
          <span className="text-sm text-gray-400">Investor chose silent disclosure — no metric detail shared.</span>
        </div>
      </div>
    )
  }

  if (disclosure_level === 'category_only') {
    return (
      <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Failed Metric Categories
          </h3>
          {checked_metric_count != null && (
            <span className="text-xs text-gray-600">{checked_metric_count} metric{checked_metric_count !== 1 ? 's' : ''} checked</span>
          )}
        </div>
        <div className="px-4 py-4">
          {failed_metrics?.length > 0 ? (
            <div className="space-y-2">
              {failed_metrics.map((name) => (
                <div key={name} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-950/15 border border-red-800/30">
                  <svg className="w-3.5 h-3.5 text-red-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                  <span className="text-sm text-red-300">{name}</span>
                </div>
              ))}
              <p className="text-xs text-gray-600 pt-1">
                Investor threshold values are not disclosed. Contact the investor for details.
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-emerald-950/15 border border-emerald-800/30">
              <svg className="w-3.5 h-3.5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              <span className="text-sm text-emerald-300">All checked metrics passed.</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  // full_threshold
  if (metric_results?.length > 0) {
    return (
      <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Metric Results with Investor Thresholds
          </h3>
        </div>
        <div className="divide-y divide-gray-800/30">
          {metric_results.map((m) => (
            <div
              key={m.metric}
              className={`px-4 py-3 flex items-center gap-3 ${!m.passed ? 'bg-red-950/10' : ''}`}
            >
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
                  m.passed
                    ? 'bg-emerald-950/50 border border-emerald-700/60'
                    : 'bg-red-950/50 border border-red-700/60'
                }`}
              >
                {m.passed ? (
                  <svg className="w-2.5 h-2.5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-2.5 h-2.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                )}
              </div>
              <span className="text-sm text-gray-300 flex-1">{m.label}</span>
              {m.investor_threshold != null && (
                <span className="text-xs font-mono text-gray-500">
                  threshold: {fmtThreshold(m.metric, m.investor_threshold)}
                </span>
              )}
              <span
                className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border flex-shrink-0 ${
                  m.passed
                    ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50'
                    : 'bg-red-950/50 text-red-300 border-red-800/50'
                }`}
              >
                {m.passed ? 'PASS' : 'FAIL'}
              </span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return null
}

// ---------------------------------------------------------------------------
// Credential card
// ---------------------------------------------------------------------------

function MatchCredentialCard({ data }) {
  const short = (h) => h ? `${h.slice(0, 16)}…` : '—'

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Match Credential
        </h3>
        {data.tee_attested !== false && (
          <span className="text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded-full bg-indigo-950/50 text-indigo-300 border border-indigo-800/50">
            TDX ATTESTED
          </span>
        )}
      </div>
      <div className="px-4 py-4 space-y-3">
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Match ID</p>
          <p className="text-xs font-mono text-gray-500 break-all">{data.match_id}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Credential Hash</p>
          <p className="text-xs font-mono text-indigo-400 break-all">{data.credential_hash}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Source Diligence Hash</p>
          <p className="text-xs font-mono text-gray-500 break-all">{data.source_diligence_credential_hash}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Issued At</p>
          <p className="text-xs text-gray-500">{data.issued_at}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">TDX Quote</p>
          <p className="text-xs font-mono text-gray-600 truncate">{short(data.tee_quote)}</p>
        </div>
        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `match-${data.match_id?.slice(0, 8)}.json`
            a.click()
            URL.revokeObjectURL(url)
          }}
          className="w-full mt-2 px-3 py-2 rounded-lg border border-gray-700/60 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 hover:bg-gray-800/30 transition-all flex items-center justify-center gap-2"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download credential JSON
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function MatchResultView() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  // location.state carries the full MatchRunResponse from the form submit
  const stateResult = location.state?.matchResult

  const [activeViewer, setActiveViewer] = useState('investor')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(!stateResult)
  const [error, setError] = useState(null)
  const [mounted, setMounted] = useState(false)

  // Initialise from state (no extra fetch needed)
  useEffect(() => {
    if (stateResult) {
      setData(stateResult)
    }
    const t = setTimeout(() => setMounted(true), 80)
    return () => clearTimeout(t)
  }, [])

  // Fetch when navigating directly to the URL
  useEffect(() => {
    if (stateResult) return
    setLoading(true)
    // Fetch investor view first; both views are pre-loaded from state when available
    getMatch(id, 'investor')
      .then((res) => setData({ ...res, investor_view: res, founder_view: null }))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-gray-500">
          <div className="w-6 h-6 border-2 border-gray-700 border-t-indigo-500 rounded-full animate-spin" />
          <span className="text-sm">Loading match result…</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
        <div className="max-w-md text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-red-950/40 border border-red-800/50 flex items-center justify-center mx-auto">
            <svg className="w-6 h-6 text-red-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </div>
          <p className="text-gray-300 font-medium">{error}</p>
          <button onClick={() => navigate('/fundraising')} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm transition-colors">
            Back to Fundraising
          </button>
        </div>
      </div>
    )
  }

  if (!data) return null

  // Resolve the view to display based on activeViewer
  // From POST state: data.founder_view / data.investor_view
  // From GET: data contains the view fields spread directly
  const currentView = stateResult
    ? (activeViewer === 'investor' ? data.investor_view : data.founder_view)
    : data

  const overall_match = data.overall_match ?? currentView?.overall_match ?? false

  return (
    <div
      className={`min-h-[calc(100vh-3.5rem)] py-10 px-4 transition-all duration-500 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
    >
      <div className="max-w-6xl mx-auto">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
          <span
            className="text-indigo-400 hover:text-indigo-300 cursor-pointer"
            onClick={() => navigate('/fundraising')}
          >
            Fundraising Credential
          </span>
          <span>/</span>
          <span className="text-gray-400 truncate max-w-[200px]">{id}</span>
        </div>

        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-1">
            Match Result
          </h1>
          {data.diligence_id && (
            <button
              onClick={() => navigate(`/fundraising/diligence/${data.diligence_id}`)}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              View source diligence
            </button>
          )}
        </div>

        {/* Overall result banner */}
        <div className="mb-6">
          <MatchBanner overall_match={overall_match} />
        </div>

        {/* Viewer tabs (only when both views available from POST state) */}
        {stateResult && (
          <div className="flex gap-1 mb-6 bg-gray-900/40 rounded-xl p-1 border border-gray-800/40 w-fit">
            {[
              { key: 'investor', label: 'Investor View' },
              { key: 'founder', label: 'Founder View' },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActiveViewer(key)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  activeViewer === key
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {/* Three-panel layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Left — metric disclosure panel */}
          <div className="lg:col-span-1">
            {activeViewer === 'investor' && stateResult ? (
              <InvestorMetricTable metricResults={currentView?.metric_results} />
            ) : activeViewer === 'founder' && stateResult ? (
              <FounderDisclosurePanel view={currentView || {}} />
            ) : (
              // Direct GET: show investor view only
              <InvestorMetricTable metricResults={data.metric_results} />
            )}
          </div>

          {/* Center — trust stack with both hashes */}
          <div className="lg:col-span-1">
            <TrustStackBar
              corpusRoot={data.corpus_root}
              credentialHash={data.source_diligence_credential_hash}
              teeQuote={data.tee_quote}
              matchCredentialHash={data.credential_hash}
            />
          </div>

          {/* Right — match credential card */}
          <div className="lg:col-span-1">
            <MatchCredentialCard data={data} />
          </div>

        </div>

        {/* Run another match CTA */}
        <div className="mt-8 flex items-center justify-center gap-4">
          <button
            onClick={() => navigate(`/fundraising/match/new?diligence_id=${data.diligence_id || ''}`)}
            className="px-4 py-2.5 rounded-xl border border-gray-700/60 text-sm text-gray-400 hover:text-gray-200 hover:border-gray-600 hover:bg-gray-800/30 transition-all"
          >
            Run another match against this diligence
          </button>
        </div>

      </div>
    </div>
  )
}
