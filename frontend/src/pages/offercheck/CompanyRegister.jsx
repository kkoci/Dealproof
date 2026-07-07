import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { offercheckRegisterCompany } from '../../api.js'

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all'
const labelClass = 'block text-xs font-medium text-gray-400 mb-1.5'

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
        <div className="w-full max-w-lg mx-auto">
          <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">You're registered</h1>
          <p className="text-sm text-amber-400 mb-6">
            Save this API key now — it's shown exactly once and cannot be recovered.
          </p>

          <div className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40 mb-4">
            <p className="text-xs text-gray-500 mb-2">Your API key</p>
            <div className="flex gap-2">
              <input
                readOnly
                value={result.api_key}
                className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-300 text-xs font-mono"
                onFocus={(e) => e.target.select()}
              />
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(result.api_key)
                  setCopied(true)
                }}
                className="px-3 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-xs font-medium transition-all"
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40 mb-6 text-sm text-gray-400">
            Recommended plan: <span className="text-gray-200 font-medium">{result.recommended_plan}</span>
            {' — '}
            {result.pricing.price_usd != null
              ? `$${result.pricing.price_usd} ${result.pricing.billing_period === 'monthly' ? '/month' : 'per verification'}`
              : 'custom pricing — contact sales'}
          </div>

          <button
            onClick={goToDashboard}
            className="w-full px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all"
          >
            Go to dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-lg mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Register your company</h1>
        <p className="text-sm text-gray-500 mb-8">
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
            <div className="px-3 py-2 rounded-lg bg-red-950/40 border border-red-800/50 text-red-400 text-sm">{error}</div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all disabled:opacity-50"
          >
            {submitting ? 'Registering…' : 'Register'}
          </button>
        </form>
      </div>
    </div>
  )
}
