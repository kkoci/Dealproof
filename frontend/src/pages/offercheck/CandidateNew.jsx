import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { offercheckSubmit } from '../../api.js'

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all'
const labelClass = 'block text-xs font-medium text-gray-400 mb-1.5'

export default function CandidateNew() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    company: '',
    role: '',
    base_salary: '',
    equity_value: '',
    bonus: '',
    start_date: '',
    candidate_ask: '',
  })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const body = {
        competing_offer: {
          company: form.company.trim(),
          role: form.role.trim(),
          base_salary: Number(form.base_salary),
          equity_value: Number(form.equity_value || 0),
          bonus: Number(form.bonus || 0),
          start_date: form.start_date,
        },
        candidate_ask: Number(form.candidate_ask),
      }
      const result = await offercheckSubmit(body)
      navigate(`/offercheck/candidate/${result.session_id}?token=${result.candidate_token}`, {
        state: { justCreated: true, employerLink: result.employer_link, consistency: result.consistency },
      })
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-lg mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Your competing offer</h1>
        <p className="text-sm text-gray-500 mb-8">
          These details stay private. The employer only ever sees a gap percentage.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Company</label>
              <input className={inputClass} value={form.company} onChange={update('company')} placeholder="Stripe" required />
            </div>
            <div>
              <label className={labelClass}>Role</label>
              <input className={inputClass} value={form.role} onChange={update('role')} placeholder="Senior Engineer" required />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className={labelClass}>Base salary</label>
              <input className={inputClass} type="number" min="0" value={form.base_salary} onChange={update('base_salary')} placeholder="180000" required />
            </div>
            <div>
              <label className={labelClass}>Equity / yr</label>
              <input className={inputClass} type="number" min="0" value={form.equity_value} onChange={update('equity_value')} placeholder="40000" />
            </div>
            <div>
              <label className={labelClass}>Bonus</label>
              <input className={inputClass} type="number" min="0" value={form.bonus} onChange={update('bonus')} placeholder="15000" />
            </div>
          </div>

          <div>
            <label className={labelClass}>Start date</label>
            <input className={inputClass} type="date" value={form.start_date} onChange={update('start_date')} required />
          </div>

          <div className="pt-2 border-t border-gray-800/60">
            <label className={labelClass}>Your ask at this employer</label>
            <input className={inputClass} type="number" min="0" value={form.candidate_ask} onChange={update('candidate_ask')} placeholder="185000" required />
          </div>

          {error && (
            <div className="px-3 py-2 rounded-lg bg-red-950/40 border border-red-800/50 text-red-400 text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all shadow-lg shadow-emerald-900/40 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting…' : 'Get my verification link'}
          </button>
        </form>
      </div>
    </div>
  )
}
