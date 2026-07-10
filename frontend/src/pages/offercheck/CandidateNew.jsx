import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { offercheckParseOfferLetter, offercheckSubmit } from '../../api.js'

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12] transition-all'
const labelClass = 'block text-xs font-medium text-ink-secondary mb-1.5'

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
  const [parsing, setParsing] = useState(false)
  const [parseNotice, setParseNotice] = useState(null)
  const [isDemo, setIsDemo] = useState(false)
  const fileInputRef = useRef(null)

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const loadDemoData = () => {
    setIsDemo(true)
    const startDate = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    setForm({
      company: 'Stripe',
      role: 'Senior Software Engineer',
      base_salary: '180000',
      equity_value: '40000',
      bonus: '15000',
      start_date: startDate,
      candidate_ask: '190000',
    })
    setParseNotice(null)
    setError('')
  }

  const handlePdfUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setParsing(true)
    setError('')
    setParseNotice(null)
    try {
      const result = await offercheckParseOfferLetter(file)
      const co = result.competing_offer
      setForm((f) => ({
        ...f,
        company: co.company || f.company,
        role: co.role || f.role,
        base_salary: co.base_salary ? String(co.base_salary) : f.base_salary,
        equity_value: co.equity_value ? String(co.equity_value) : f.equity_value,
        bonus: co.bonus ? String(co.bonus) : f.bonus,
        start_date: co.start_date || f.start_date,
      }))
      setParseNotice({ confidence: result.confidence, notes: result.notes })
    } catch (err) {
      setError(err.message || 'Could not read that PDF — enter the details manually below')
    } finally {
      setParsing(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

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
      const employerLink = isDemo ? `${result.employer_link}&demo=1` : result.employer_link
      navigate(`/offercheck/candidate/${result.session_id}?token=${result.candidate_token}`, {
        state: { justCreated: true, employerLink, consistency: result.consistency },
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
        <div className="flex items-start justify-between gap-3 mb-2">
          <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary">Your competing offer</h1>
          <button
            type="button"
            onClick={loadDemoData}
            className="shrink-0 mt-1 px-2.5 py-1 rounded-md bg-bg-elevated hover:bg-border text-ink-secondary hover:text-ink-primary text-xs font-medium transition-all"
          >
            Load demo data
          </button>
        </div>
        <p className="text-sm text-ink-muted mb-6">
          These details stay private. The employer only ever sees a gap percentage.
        </p>

        <div className="mb-6 p-4 rounded-xl bg-bg-surface border border-dashed border-border-strong">
          <label className="flex items-center justify-between gap-3 cursor-pointer">
            <div>
              <p className="text-sm font-medium text-ink-primary">Upload your offer letter (PDF)</p>
              <p className="text-xs text-ink-muted mt-0.5">Optional — we'll prefill the fields below for you to review</p>
            </div>
            <span className="shrink-0 px-3 py-2 rounded-lg bg-teal-subtle border-[1.5px] border-teal text-teal text-xs font-medium transition-all hover:bg-teal-subtle/70">
              {parsing ? 'Reading…' : 'Choose file'}
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              onChange={handlePdfUpload}
              disabled={parsing}
              className="hidden"
            />
          </label>
          {parseNotice && (
            <div className="mt-3 pt-3 border-t border-border text-xs">
              <span className={`font-medium ${parseNotice.confidence === 'high' ? 'text-success' : parseNotice.confidence === 'medium' ? 'text-sealed' : 'text-danger'}`}>
                {parseNotice.confidence} confidence extraction
              </span>
              <span className="text-ink-muted"> — double-check the fields below</span>
              {parseNotice.notes?.length > 0 && (
                <ul className="mt-1 list-disc list-inside text-ink-muted space-y-0.5">
                  {parseNotice.notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>

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

          <div className="pt-2 border-t border-border">
            <label className={labelClass}>Your ask at this employer</label>
            <input className={inputClass} type="number" min="0" value={form.candidate_ask} onChange={update('candidate_ask')} placeholder="185000" required />
          </div>

          <p className="text-xs text-ink-muted pt-2 border-t border-border">
            You can enable AI negotiation from your session page after submitting.
          </p>

          {error && (
            <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full px-6 py-3 rounded-xl bg-teal hover:bg-teal-hover text-white font-semibold text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting…' : 'Get my verification link'}
          </button>
        </form>
      </div>
    </div>
  )
}
