import React, { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { offercheckJoinInvite, offercheckParseOfferLetter } from '../../api.js'

// luxe SKILL.md "Controls, Dials & Selectors" control anatomy: named transition properties
// (never `transition: all`) at the spec's 120ms smooth-out easing for hover/focus.
const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12] transition-[background-color,border-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]'
const labelClass = 'block text-xs font-medium text-ink-secondary mb-1.5'
// Primary action button: named-property transition + luxe Press Feedback (scale(0.96) on :active,
// a separate 100ms duration so the press reads snappier than the 150ms hover crossfade).
const primaryButtonClass =
  'transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] active:scale-[0.96] active:duration-100 disabled:active:scale-100'
// The "Choose file" pill acts as a button (wraps the hidden file input) — same press feedback.
const filePillClass =
  'transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] active:scale-[0.96] active:duration-100'

export default function CandidateJoin() {
  const navigate = useNavigate()
  const { inviteId } = useParams()
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
  const fileInputRef = useRef(null)

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

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
      const result = await offercheckJoinInvite(inviteId, body)
      navigate(`/offercheck/candidate/${result.session_id}?token=${result.candidate_token}`, {
        state: { justCreated: true, consistency: result.consistency },
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
        <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary mb-2">You've been invited to negotiate</h1>
        <p className="text-sm text-ink-muted mb-6">
          Enter your competing offer and your ask. These details stay private — the employer only ever sees a gap percentage.
        </p>

        <div className="mb-6 p-4 rounded-xl bg-bg-surface border border-dashed border-border-strong">
          <label className="flex items-center justify-between gap-3 cursor-pointer">
            <div>
              <p className="text-sm font-medium text-ink-primary">Upload your offer letter (PDF)</p>
              <p className="text-xs text-ink-muted mt-0.5">Optional — we'll prefill the fields below for you to review</p>
            </div>
            <span className={`shrink-0 w-24 text-center px-3 py-2 rounded-lg bg-teal-subtle border-[1.5px] border-teal text-teal text-xs font-medium hover:bg-teal-subtle/70 ${filePillClass}`}>
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
            <div className="mt-3 pt-3 border-t border-border text-xs animate-rise-in">
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

          {error && (
            <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm animate-rise-in">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className={`w-full px-6 py-3 rounded-xl bg-teal hover:bg-teal-hover text-white font-semibold text-sm disabled:opacity-50 disabled:cursor-not-allowed ${primaryButtonClass}`}
          >
            {submitting ? 'Submitting…' : 'Join negotiation'}
          </button>
        </form>
      </div>
    </div>
  )
}
