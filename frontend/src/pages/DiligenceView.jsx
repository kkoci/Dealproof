import React, { useState, useEffect } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { getDiligence } from '../api.js'
import TrustStackBar from '../components/TrustStackBar.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function money(v) {
  if (v == null) return '—'
  return `$${Number(v).toLocaleString()}`
}

function short(h) {
  if (!h) return '—'
  return `${h.slice(0, 16)}…`
}

// ---------------------------------------------------------------------------
// Metric row
// ---------------------------------------------------------------------------

const METRICS = [
  {
    key: 'mom_growth',
    label: 'MoM Revenue Growth',
    flag: (f) => !f.mom_growth_verified,
    valueStr: (f) => f.mom_growth_computed != null ? pct(f.mom_growth_computed) : '—',
    detail: (f) => f.mom_growth_verified ? 'Verified vs claim' : 'Computed rate differs from claim',
  },
  {
    key: 'customer_concentration',
    label: 'Customer Concentration',
    flag: (f) => f.customer_concentration_flag,
    valueStr: (f) => f.top_customer_pct != null ? `top customer: ${pct(f.top_customer_pct)}` : '—',
    detail: (f) => f.customer_concentration_flag ? 'Single customer ≥ 30% of revenue' : 'No single customer ≥ 30%',
  },
  {
    key: 'gross_margin',
    label: 'Gross Margin',
    flag: (f) => !f.gross_margin_verified,
    valueStr: (f) => f.gross_margin_computed != null ? pct(f.gross_margin_computed) : '—',
    detail: (f) => f.gross_margin_verified ? 'Verified vs claim' : 'Computed margin differs from claim',
  },
  {
    key: 'runway',
    label: 'Runway',
    flag: (f) => f.runway_flag,
    valueStr: (f) => f.runway_months_computed != null ? `${f.runway_months_computed.toFixed(1)} months` : '—',
    detail: (f) => f.runway_flag ? 'Runway < 6 months' : 'Healthy runway',
  },
  {
    key: 'churn',
    label: 'Monthly Churn Rate',
    flag: (f) => f.churn_flag,
    valueStr: (f) => f.churn_rate_computed != null ? `${pct(f.churn_rate_computed)} / month` : '—',
    detail: (f) => f.churn_flag ? 'Monthly churn > 5%' : 'Churn within healthy range',
  },
  {
    key: 'arr',
    label: 'ARR Consistency',
    flag: (f) => !f.arr_consistency_verified,
    valueStr: (f) => f.arr_delta_pct != null ? `delta ${f.arr_delta_pct >= 0 ? '+' : ''}${pct(f.arr_delta_pct)}` : '—',
    detail: (f) => f.arr_consistency_verified ? 'Computed ARR matches reported' : 'Reported ARR diverges from subscription data',
  },
]

function MetricStatusGrid({ findings }) {
  if (!findings) return null

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          Metric Findings
        </h3>
      </div>
      <div className="divide-y divide-gray-800/30">
        {METRICS.map(({ key, label, flag, valueStr, detail }) => {
          const isFlagged = flag(findings)
          return (
            <div key={key} className={`px-4 py-3 ${isFlagged ? 'bg-red-950/10' : ''}`}>
              <div className="flex items-start gap-3">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${isFlagged ? 'bg-red-950/50 border border-red-700/60' : 'bg-emerald-950/50 border border-emerald-700/60'}`}>
                  {isFlagged ? (
                    <svg className="w-2.5 h-2.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    <svg className="w-2.5 h-2.5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm text-gray-300 font-medium">{label}</span>
                    <span className={`text-xs font-mono flex-shrink-0 ${isFlagged ? 'text-red-400' : 'text-emerald-400'}`}>
                      {valueStr(findings)}
                    </span>
                  </div>
                  <p className={`text-xs mt-0.5 ${isFlagged ? 'text-red-500' : 'text-gray-600'}`}>
                    {detail(findings)}
                  </p>
                </div>
                <span className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border flex-shrink-0 self-center ${isFlagged ? 'bg-red-950/50 text-red-300 border-red-800/50' : 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50'}`}>
                  {isFlagged ? 'FLAGGED' : 'VERIFIED'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Credential card
// ---------------------------------------------------------------------------

function CredentialCard({ result }) {
  const findings = result.inspector_findings || {}
  const allFavorable = !findings.any_flag_raised
  const evaluation = result.evaluation

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Diligence Credential
        </h3>
        <span className={`text-[10px] font-semibold tracking-wider px-2.5 py-1 rounded-full border ${allFavorable ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50' : 'bg-yellow-950/50 text-yellow-300 border-yellow-800/50'}`}>
          {allFavorable ? 'ALL FAVORABLE' : 'FLAGS RAISED'}
        </span>
      </div>
      <div className="px-4 py-4 space-y-3">
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Company</p>
          <p className="text-sm text-gray-200 font-medium">{result.company_name}</p>
          {result.round_label && <p className="text-xs text-gray-500">{result.round_label}</p>}
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Credential ID</p>
          <p className="text-xs font-mono text-gray-500">{result.diligence_id}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Credential Hash</p>
          <p className="text-xs font-mono text-indigo-400 break-all">{result.credential_hash}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Corpus Root</p>
          <p className="text-xs font-mono text-gray-500 break-all">{result.corpus_root}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">TDX Quote</p>
          <p className="text-xs font-mono text-gray-600 truncate">{short(result.tee_quote)}</p>
        </div>

        {evaluation?.notable_strengths?.length > 0 && (
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5">Strengths</p>
            <ul className="space-y-1">
              {evaluation.notable_strengths.map((s, i) => (
                <li key={i} className="text-xs text-emerald-400 flex items-start gap-1.5">
                  <span className="mt-0.5 flex-shrink-0">✓</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {evaluation?.notable_risks?.length > 0 && (
          <div>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5">Risks</p>
            <ul className="space-y-1">
              {evaluation.notable_risks.map((r, i) => (
                <li key={i} className="text-xs text-red-400 flex items-start gap-1.5">
                  <span className="mt-0.5 flex-shrink-0">⚠</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {evaluation?.overall_assessment && (
          <div className="pt-1 border-t border-gray-800/40">
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Assessment</p>
            <p className="text-xs text-gray-400 leading-relaxed">{evaluation.overall_assessment}</p>
          </div>
        )}

        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `diligence-${result.diligence_id?.slice(0, 8)}.json`
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
// Before / After demo view
// ---------------------------------------------------------------------------

const MOCK_SPREADSHEET_ROWS = [
  ['Revenue (Oct)', '$78,234', '$84,102', '$92,450'],
  ['COGS', '$19,045', '$20,512', '$22,018'],
  ['Customer A (name redacted)', '$11,200', '$10,900', '$11,450'],
  ['Customer B (name redacted)', '$9,500', '$9,200', '$9,800'],
  ['Cash Balance', '—', '—', '$1,204,500'],
  ['Monthly Burn', '—', '—', '$85,000'],
  ['Cohort Sep-25: 40 → ?', '███', '███', '███'],
  ['Reported ARR', '—', '—', '$1,100,000'],
]

function BeforeAfterToggle({ result }) {
  const [view, setView] = useState('after')

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-gray-800/40 bg-gray-900/40">
        <button
          onClick={() => setView('before')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${view === 'before' ? 'text-gray-100 border-b-2 border-indigo-500 bg-gray-900/60' : 'text-gray-500 hover:text-gray-300'}`}
        >
          What the investor would normally see
        </button>
        <button
          onClick={() => setView('after')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${view === 'after' ? 'text-gray-100 border-b-2 border-indigo-500 bg-gray-900/60' : 'text-gray-500 hover:text-gray-300'}`}
        >
          What they actually receive
        </button>
      </div>

      {view === 'before' ? (
        <div className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-3 h-3 rounded-full bg-red-500/70" />
            <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
            <div className="w-3 h-3 rounded-full bg-emerald-500/70" />
            <span className="ml-2 text-xs text-gray-600 font-mono">Q4_2025_Financials_FINAL_v3.xlsx</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-gray-700/60">
                  <th className="text-left py-2 pr-4 text-gray-500 font-normal">Metric</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-normal">Oct</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-normal">Nov</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-normal">Dec</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_SPREADSHEET_ROWS.map(([label, ...vals], i) => (
                  <tr key={i} className="border-b border-gray-800/30">
                    <td className="py-2 pr-4 text-gray-400">{label}</td>
                    {vals.map((v, j) => (
                      <td key={j} className={`py-2 px-3 text-right ${v === '███' ? 'text-gray-700 select-none' : 'text-gray-300'}`}>{v}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 px-3 py-2.5 rounded-lg bg-yellow-950/30 border border-yellow-800/40 text-xs text-yellow-400">
            ⚠ Investor must trust these numbers. No way to verify without seeing the full source data.
          </div>
        </div>
      ) : (
        <div className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-5 h-5 rounded bg-indigo-600/80 flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <span className="text-xs text-gray-400 font-medium">DealProof Diligence Credential</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950/50 text-emerald-300 border border-emerald-800/50 font-semibold tracking-wider">TDX ATTESTED</span>
          </div>

          <div className="space-y-2.5 text-xs">
            {[
              { label: 'MoM Growth', value: result?.inspector_findings?.mom_growth_computed != null ? pct(result.inspector_findings.mom_growth_computed) : '—', ok: result?.inspector_findings?.mom_growth_verified },
              { label: 'Gross Margin', value: result?.inspector_findings?.gross_margin_computed != null ? pct(result.inspector_findings.gross_margin_computed) : '—', ok: result?.inspector_findings?.gross_margin_verified },
              { label: 'Top Customer Concentration', value: result?.inspector_findings?.top_customer_pct != null ? pct(result.inspector_findings.top_customer_pct) : '—', ok: !result?.inspector_findings?.customer_concentration_flag },
              { label: 'Runway', value: result?.inspector_findings?.runway_months_computed != null ? `${result.inspector_findings.runway_months_computed.toFixed(1)} months` : '—', ok: !result?.inspector_findings?.runway_flag },
              { label: 'Monthly Churn', value: result?.inspector_findings?.churn_rate_computed != null ? pct(result.inspector_findings.churn_rate_computed) : '—', ok: !result?.inspector_findings?.churn_flag },
              { label: 'ARR Consistency', value: result?.inspector_findings?.arr_delta_pct != null ? `delta ${result.inspector_findings.arr_delta_pct >= 0 ? '+' : ''}${pct(result.inspector_findings.arr_delta_pct)}` : '—', ok: result?.inspector_findings?.arr_consistency_verified },
            ].map(({ label, value, ok }) => (
              <div key={label} className={`flex items-center justify-between px-3 py-2 rounded-lg border ${ok ? 'border-emerald-800/30 bg-emerald-950/10' : 'border-red-800/30 bg-red-950/10'}`}>
                <span className={ok ? 'text-gray-400' : 'text-gray-400'}>{label}</span>
                <div className="flex items-center gap-2">
                  <span className={`font-mono ${ok ? 'text-emerald-300' : 'text-red-300'}`}>{value}</span>
                  <span className={`text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded border ${ok ? 'text-emerald-400 border-emerald-800/50' : 'text-red-400 border-red-800/50'}`}>
                    {ok ? 'VERIFIED' : 'FLAGGED'}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 px-3 py-2.5 rounded-lg bg-indigo-950/30 border border-indigo-800/40 text-xs text-indigo-300">
            Raw financial figures were never exposed to this credential or to DealProof. The enclave proves the metric. Nobody sees the underlying data — including us.
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DiligenceView() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const [result, setResult] = useState(location.state?.result || null)
  const [loading, setLoading] = useState(!result)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (result) return
    setLoading(true)
    getDiligence(id)
      .then((row) => {
        if (row.credential) {
          setResult({ ...row.credential, tee_quote: row.tee_quote, diligence_id: row.diligence_id, company_name: row.company_name, round_label: row.round_label, corpus_root: row.corpus_root })
        } else {
          setError('Diligence found but not yet evaluated.')
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-gray-500">
          <div className="w-6 h-6 border-2 border-gray-700 border-t-indigo-500 rounded-full animate-spin" />
          <span className="text-sm">Loading credential…</span>
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
          <button onClick={() => navigate('/fundraising/new')} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm transition-colors">
            New Diligence
          </button>
        </div>
      </div>
    )
  }

  const findings = result?.inspector_findings || {}

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span>dealproof</span>
            <span>/</span>
            <span className="text-indigo-400">fundraising</span>
            <span>/</span>
            <span className="text-gray-400 truncate max-w-[200px]">{id}</span>
          </div>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-1">
                {result?.company_name || 'Diligence Report'}
              </h1>
              {result?.round_label && (
                <span className="text-sm text-gray-500">{result.round_label}</span>
              )}
            </div>
            <span className={`text-xs font-semibold tracking-wider px-3 py-1.5 rounded-full border flex-shrink-0 mt-1 ${!findings.any_flag_raised ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50' : 'bg-yellow-950/50 text-yellow-300 border-yellow-800/50'}`}>
              {!findings.any_flag_raised ? '✓ ALL METRICS FAVORABLE' : '⚠ FLAGS RAISED'}
            </span>
          </div>
        </div>

        {/* Before/After demo toggle */}
        <div className="mb-8">
          <BeforeAfterToggle result={result} />
        </div>

        {/* Three-panel layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left — metric status grid */}
          <div className="lg:col-span-1">
            <MetricStatusGrid findings={findings} />
          </div>

          {/* Center — trust stack */}
          <div className="lg:col-span-1">
            <TrustStackBar
              corpusRoot={result?.corpus_root}
              credentialHash={result?.credential_hash}
              teeQuote={result?.tee_quote}
            />
          </div>

          {/* Right — credential card */}
          <div className="lg:col-span-1">
            <CredentialCard result={result} />
          </div>
        </div>
      </div>
    </div>
  )
}
