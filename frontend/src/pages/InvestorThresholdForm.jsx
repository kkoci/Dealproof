import React, { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { submitInvestorThresholds, runMatch } from '../api.js'

// ---------------------------------------------------------------------------
// Threshold field definitions
// ---------------------------------------------------------------------------

const THRESHOLD_FIELDS = [
  {
    key: 'min_mom_growth',
    label: 'Min MoM Growth',
    unit: '%',
    direction: 'min',
    hint: 'e.g. 5 means ≥5% monthly revenue growth',
    placeholder: '5',
    scale: 0.01,
  },
  {
    key: 'max_customer_concentration_pct',
    label: 'Max Customer Concentration',
    unit: '%',
    direction: 'max',
    hint: 'e.g. 30 means no single customer > 30% of revenue',
    placeholder: '30',
    scale: 0.01,
  },
  {
    key: 'min_gross_margin',
    label: 'Min Gross Margin',
    unit: '%',
    direction: 'min',
    hint: 'e.g. 60 means ≥60% gross margin required',
    placeholder: '60',
    scale: 0.01,
  },
  {
    key: 'min_runway_months',
    label: 'Min Runway',
    unit: 'months',
    direction: 'min',
    hint: 'e.g. 12 means at least 12 months of runway',
    placeholder: '12',
    scale: 1,
  },
  {
    key: 'max_monthly_churn_pct',
    label: 'Max Monthly Churn',
    unit: '%',
    direction: 'max',
    hint: 'e.g. 5 means ≤5% monthly customer churn',
    placeholder: '5',
    scale: 0.01,
  },
  {
    key: 'max_arr_delta_pct',
    label: 'Max ARR Inconsistency',
    unit: '%',
    direction: 'max',
    hint: 'e.g. 10 means ≤10% gap between reported and computed ARR',
    placeholder: '10',
    scale: 0.01,
  },
]

const DISCLOSURE_OPTIONS = [
  {
    value: 'none',
    label: 'Silent',
    description: 'Founder only learns pass/fail — no metric detail',
  },
  {
    value: 'category_only',
    label: 'Category only',
    description: 'Founder learns which metric categories failed, not threshold values',
  },
  {
    value: 'full_threshold',
    label: 'Full threshold',
    description: 'Founder sees your threshold value per failed metric',
  },
]

// ---------------------------------------------------------------------------
// Form component
// ---------------------------------------------------------------------------

export default function InvestorThresholdForm() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const diligenceIdFromQuery = searchParams.get('diligence_id') || ''

  const [diligenceId, setDiligenceId] = useState(diligenceIdFromQuery)
  const [investorId, setInvestorId] = useState('')
  const [thresholds, setThresholds] = useState({})
  const [disclosure, setDisclosure] = useState('category_only')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 80)
    return () => clearTimeout(t)
  }, [])

  function setThreshold(key, rawValue) {
    if (rawValue === '' || rawValue == null) {
      setThresholds(prev => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    } else {
      setThresholds(prev => ({ ...prev, [key]: rawValue }))
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)

    if (!diligenceId.trim()) {
      setError('Diligence ID is required.')
      return
    }
    if (!investorId.trim()) {
      setError('Investor ID is required.')
      return
    }

    // Build thresholds payload — convert display values to decimal where needed
    const thresholdPayload = { investor_id: investorId.trim(), disclosure_on_mismatch: disclosure }
    let anyThreshold = false
    for (const field of THRESHOLD_FIELDS) {
      const raw = thresholds[field.key]
      if (raw !== undefined && raw !== '') {
        thresholdPayload[field.key] = Number(raw) * field.scale
        anyThreshold = true
      }
    }

    if (!anyThreshold) {
      setError('Set at least one threshold, otherwise matching is trivially pass.')
      return
    }

    setSubmitting(true)
    try {
      const { threshold_id } = await submitInvestorThresholds(diligenceId.trim(), thresholdPayload)
      const matchResult = await runMatch(diligenceId.trim(), threshold_id)
      navigate(`/fundraising/match/${matchResult.match_id}`, { state: { matchResult } })
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  const activeCount = Object.keys(thresholds).filter(k => thresholds[k] !== '').length

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div
        className={`max-w-2xl mx-auto transition-all duration-500 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
      >
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span
              className="text-indigo-400 hover:text-indigo-300 cursor-pointer"
              onClick={() => navigate('/fundraising')}
            >
              Fundraising Credential
            </span>
            <span>/</span>
            <span className="text-gray-400">Investor Match</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            Set Your Thresholds
          </h1>
          <p className="text-gray-400 text-sm leading-relaxed">
            The founder never sees your raw thresholds. The TEE runs the comparison
            and returns only a pass/fail result — with the disclosure level you choose.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Diligence + Investor IDs */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Pairing
              </h2>
            </div>
            <div className="px-4 py-4 space-y-4">
              <div>
                <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1.5">
                  Diligence ID
                </label>
                <input
                  type="text"
                  value={diligenceId}
                  onChange={e => setDiligenceId(e.target.value)}
                  placeholder="paste the diligence_id from the credential"
                  className="w-full px-3 py-2.5 rounded-lg bg-gray-800/50 border border-gray-700/60 text-gray-200 text-sm font-mono placeholder-gray-600 focus:outline-none focus:border-indigo-500/60 focus:bg-gray-800/80 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 uppercase tracking-wider mb-1.5">
                  Your Investor ID
                </label>
                <input
                  type="text"
                  value={investorId}
                  onChange={e => setInvestorId(e.target.value)}
                  placeholder="e.g. acme-ventures-fund-ii"
                  className="w-full px-3 py-2.5 rounded-lg bg-gray-800/50 border border-gray-700/60 text-gray-200 text-sm placeholder-gray-600 focus:outline-none focus:border-indigo-500/60 focus:bg-gray-800/80 transition-colors"
                />
                <p className="text-xs text-gray-600 mt-1">Used to identify you in the match credential. Not shared with the founder.</p>
              </div>
            </div>
          </div>

          {/* Threshold fields */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Thresholds
                <span className="ml-2 text-gray-600 normal-case font-normal">— leave blank to skip</span>
              </h2>
              {activeCount > 0 && (
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-950/60 text-indigo-300 border border-indigo-800/50">
                  {activeCount} set
                </span>
              )}
            </div>
            <div className="divide-y divide-gray-800/30">
              {THRESHOLD_FIELDS.map((field) => (
                <div key={field.key} className="px-4 py-3 flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm text-gray-300 font-medium">{field.label}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${field.direction === 'min' ? 'text-emerald-400 border-emerald-800/50 bg-emerald-950/30' : 'text-amber-400 border-amber-800/50 bg-amber-950/30'}`}>
                        {field.direction === 'min' ? 'MIN' : 'MAX'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-600">{field.hint}</p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0 w-32">
                    <input
                      type="number"
                      step="any"
                      min="0"
                      value={thresholds[field.key] ?? ''}
                      onChange={e => setThreshold(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      className="w-20 px-2.5 py-2 rounded-lg bg-gray-800/50 border border-gray-700/60 text-gray-200 text-sm text-right font-mono placeholder-gray-700 focus:outline-none focus:border-indigo-500/60 transition-colors"
                    />
                    <span className="text-xs text-gray-500 w-10">{field.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Disclosure level */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
              <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Disclosure on Mismatch
              </h2>
            </div>
            <div className="px-4 py-3 space-y-2">
              {DISCLOSURE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${disclosure === opt.value ? 'border-indigo-600/60 bg-indigo-950/20' : 'border-gray-800/50 hover:border-gray-700/60 hover:bg-gray-800/20'}`}
                >
                  <input
                    type="radio"
                    name="disclosure"
                    value={opt.value}
                    checked={disclosure === opt.value}
                    onChange={() => setDisclosure(opt.value)}
                    className="mt-0.5 accent-indigo-500"
                  />
                  <div>
                    <span className="text-sm text-gray-200 font-medium">{opt.label}</span>
                    <p className="text-xs text-gray-500 mt-0.5">{opt.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Privacy notice */}
          <div className="px-3 py-2.5 rounded-lg bg-indigo-950/20 border border-indigo-800/30 text-xs text-indigo-300 flex items-start gap-2">
            <svg className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span>
              Your threshold values are stored in the TEE. The founder only receives a pass/fail outcome per your disclosure setting — never the raw numbers you entered.
            </span>
          </div>

          {error && (
            <div className="px-3 py-2.5 rounded-lg bg-red-950/30 border border-red-800/40 text-xs text-red-400">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900/50 disabled:text-indigo-500 text-white font-semibold text-sm transition-colors flex items-center justify-center gap-2"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-indigo-300/30 border-t-indigo-300 rounded-full animate-spin" />
                Running match in TEE…
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Run Attested Match
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
