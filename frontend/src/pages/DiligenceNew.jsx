import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestDiligence, evaluateDiligence } from '../api.js'

const EXAMPLE_METRICS = [
  {
    source: "monthly_revenue",
    format: "revenue_timeseries_json",
    content: {
      months: [
        { month: "2025-10", revenue: 78000, cogs: 19000 },
        { month: "2025-11", revenue: 84000, cogs: 20500 },
        { month: "2025-12", revenue: 92000, cogs: 22000 }
      ]
    }
  },
  {
    source: "customer_revenue_breakdown",
    format: "customer_breakdown_json",
    content: {
      customers: [
        { customer_id: "cust_001", revenue: 11000 },
        { customer_id: "cust_002", revenue: 9500 },
        { customer_id: "cust_003", revenue: 8000 },
        { customer_id: "cust_004", revenue: 7000 }
      ]
    }
  },
  {
    source: "expenses_and_cash",
    format: "expense_cash_json",
    content: { monthly_burn: 85000, cash_balance: 1200000 }
  },
  {
    source: "cohort_retention",
    format: "cohort_json",
    content: {
      cohorts: [{ cohort_month: "2025-09", starting_customers: 40, active_after_3mo: 37 }]
    }
  },
  {
    source: "reported_arr",
    format: "arr_claim_json",
    content: { reported_arr: 1100000 }
  }
]

const inputClass = `
  w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200
  placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50
  focus:border-indigo-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed
`.trim()

const inputErrorClass = inputClass.replace('border-gray-700/60', 'border-red-700/60')
  .replace('focus:ring-indigo-500/50', 'focus:ring-red-500/50')
  .replace('focus:border-indigo-500/50', 'focus:border-red-500/50')

function FormField({ label, hint, error, children, required }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-gray-300 flex items-center gap-1.5">
        {label}
        {required && <span className="text-indigo-400 text-xs">*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-gray-600">{hint}</p>}
      {error && (
        <p className="text-xs text-red-400 flex items-center gap-1">
          <svg className="w-3 h-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          {error}
        </p>
      )}
    </div>
  )
}

export default function DiligenceNew() {
  const navigate = useNavigate()

  const [companyName, setCompanyName] = useState('')
  const [roundLabel, setRoundLabel] = useState('')
  const [metricsJson, setMetricsJson] = useState('')
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [phase, setPhase] = useState(null) // 'ingesting' | 'evaluating'
  const [submitError, setSubmitError] = useState(null)

  function loadExample() {
    setCompanyName('Acme Software Inc')
    setRoundLabel('Series A')
    setMetricsJson(JSON.stringify(EXAMPLE_METRICS, null, 2))
    setErrors({})
  }

  function validate() {
    const errs = {}
    if (!companyName.trim()) errs.company_name = 'Company name is required'

    let parsed
    try {
      parsed = JSON.parse(metricsJson)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        errs.metrics = 'Must be a non-empty JSON array of metrics records'
      }
    } catch {
      errs.metrics = 'Invalid JSON — paste a valid metrics_records array'
    }
    return { errs, parsed }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitError(null)

    const { errs, parsed } = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }

    setSubmitting(true)
    setPhase('ingesting')

    try {
      const ingestResult = await ingestDiligence({
        company_name: companyName.trim(),
        round_label: roundLabel.trim() || null,
        metrics_records: parsed,
      })

      setPhase('evaluating')

      const evalResult = await evaluateDiligence(ingestResult.diligence_id, {})

      navigate(`/fundraising/diligence/${ingestResult.diligence_id}`, {
        state: { result: evalResult },
      })
    } catch (err) {
      setSubmitError(err.message || 'Something went wrong. Is the backend running?')
      setSubmitting(false)
      setPhase(null)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span>dealproof</span>
            <span>/</span>
            <span className="text-indigo-400">fundraising</span>
            <span>/</span>
            <span className="text-gray-400">new-diligence</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            Fundraising Diligence
          </h1>
          <p className="text-sm text-gray-500">
            Upload a company's financial metrics. The TEE computes and verifies six key
            metrics — without the investor ever seeing the raw numbers.
          </p>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-6">

          {/* Company info */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-800/40 bg-gray-900/40">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                Company
              </h2>
            </div>
            <div className="px-5 py-5 space-y-5">
              <FormField label="Company Name" error={errors.company_name} required>
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => { setCompanyName(e.target.value); setErrors((p) => ({ ...p, company_name: null })) }}
                  disabled={submitting}
                  placeholder="Acme Software Inc"
                  className={errors.company_name ? inputErrorClass : inputClass}
                />
              </FormField>
              <FormField label="Round Label" hint="Optional — e.g. Seed, Series A">
                <input
                  type="text"
                  value={roundLabel}
                  onChange={(e) => setRoundLabel(e.target.value)}
                  disabled={submitting}
                  placeholder="Series A"
                  className={inputClass}
                />
              </FormField>
            </div>
          </div>

          {/* Metrics */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                Metrics Package
              </h2>
              <button
                type="button"
                onClick={loadExample}
                disabled={submitting}
                className="text-xs px-3 py-1.5 rounded-md bg-indigo-900/30 text-indigo-400 hover:bg-indigo-900/50 hover:text-indigo-300 border border-indigo-800/40 transition-all disabled:opacity-40"
              >
                Load example
              </button>
            </div>
            <div className="px-5 py-5">
              <FormField
                label="metrics_records JSON"
                hint='Paste a JSON array of metric sources: monthly_revenue, customer_revenue_breakdown, expenses_and_cash, cohort_retention, reported_arr'
                error={errors.metrics}
                required
              >
                <textarea
                  rows={12}
                  value={metricsJson}
                  onChange={(e) => { setMetricsJson(e.target.value); setErrors((p) => ({ ...p, metrics: null })) }}
                  disabled={submitting}
                  placeholder='[{"source": "monthly_revenue", ...}]'
                  className={`${errors.metrics ? inputErrorClass : inputClass} font-mono text-xs resize-y min-h-[200px]`}
                />
              </FormField>

              {/* Source legend */}
              <div className="mt-4 grid grid-cols-2 gap-1.5">
                {['monthly_revenue', 'customer_revenue_breakdown', 'expenses_and_cash', 'cohort_retention', 'reported_arr'].map((s) => {
                  const present = (() => {
                    try {
                      const arr = JSON.parse(metricsJson)
                      return Array.isArray(arr) && arr.some((r) => r.source === s)
                    } catch { return false }
                  })()
                  return (
                    <div key={s} className={`flex items-center gap-1.5 text-xs rounded px-2 py-1 border ${present ? 'border-emerald-800/40 bg-emerald-950/20 text-emerald-400' : 'border-gray-800/40 text-gray-600'}`}>
                      <svg className={`w-3 h-3 ${present ? 'text-emerald-400' : 'text-gray-700'}`} fill="currentColor" viewBox="0 0 20 20">
                        {present
                          ? <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                          : <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clipRule="evenodd" />
                        }
                      </svg>
                      <span className="font-mono truncate">{s}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Error */}
          {submitError && (
            <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="font-medium text-red-300">Diligence failed</p>
                <p className="text-red-400/80 text-xs mt-0.5">{submitError}</p>
              </div>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:-translate-y-0.5 active:translate-y-0 disabled:translate-y-0 disabled:shadow-none"
          >
            {submitting ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>
                  {phase === 'ingesting' ? 'Hashing metrics into TEE…' : 'Evaluating inside enclave…'}
                </span>
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Run Diligence
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
