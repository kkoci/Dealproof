import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { offercheckRegisterCompany } from '../../api.js'

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12] transition-all'
const labelClass = 'block text-xs font-medium text-ink-secondary mb-1.5'

export default function CompanyRegister() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [hiresPerYear, setHiresPerYear] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [copied, setCopied] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const data = await offercheckRegisterCompany({
        name: name.trim(),
        hires_per_year: Number(hiresPerYear || 0),
      })
      setResult(data)
    } catch (err) {
      setError(err.message || 'Could not register')
    } finally {
      setSubmitting(false)
    }
  }

  const goToDashboard = () => {
    if (result) localStorage.setItem('offercheck_api_key', result.api_key)
    navigate('/offercheck/dashboard')
  }

  if (result) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-3xl mx-auto">
          <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary mb-2">You're registered</h1>
          <p className="text-sm text-sealed-text mb-6">
            🔒 Save this API key now — it's shown exactly once and cannot be recovered.
          </p>

          <div className="p-4 rounded-xl bg-sealed-subtle border border-dashed border-sealed-border mb-4">
            <p className="text-xs text-sealed-text mb-2">Your API key</p>
            <div className="flex gap-2">
              <input
                readOnly
                value={result.api_key}
                className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-white border border-sealed-border text-sealed-text text-xs font-mono"
                onFocus={(e) => e.target.select()}
              />
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(result.api_key)
                  setCopied(true)
                }}
                className="px-3 py-2 rounded-lg bg-teal-subtle border-[1.5px] border-teal hover:bg-teal-subtle/70 text-teal text-xs font-medium transition-all"
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-bg-surface border border-border mb-6 text-sm text-ink-secondary" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            Recommended plan: <span className="text-ink-primary font-medium">{result.recommended_plan}</span>
            {' — '}
            {result.pricing.price_usd != null
              ? `$${result.pricing.price_usd} ${result.pricing.billing_period === 'monthly' ? '/month' : 'per verification'}`
              : 'custom pricing — contact sales'}
          </div>

          <button
            onClick={goToDashboard}
            className="w-full px-6 py-3 rounded-xl bg-teal hover:bg-teal-hover text-white font-semibold text-sm transition-all"
          >
            Go to dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-3xl mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary mb-2">Register your company</h1>
        <p className="text-sm text-ink-muted mb-8">
          Get an API key for bulk verification and the TA dashboard.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelClass}>Company name</label>
            <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Corp" required />
          </div>
          <div>
            <label className={labelClass}>Hires per year (for a plan recommendation)</label>
            <input
              className={inputClass}
              type="number"
              min="0"
              value={hiresPerYear}
              onChange={(e) => setHiresPerYear(e.target.value)}
              placeholder="50"
            />
          </div>

          {error && (
            <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full px-6 py-3 rounded-xl bg-teal hover:bg-teal-hover text-white font-semibold text-sm transition-all disabled:opacity-50"
          >
            {submitting ? 'Registering…' : 'Register'}
          </button>
        </form>
      </div>
    </div>
  )
}
