import React, { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { offercheckJoinInvite, offercheckParseOfferLetter } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Button from '../../components/offercheck/Button.jsx'
import { FieldLabel, Input, Select } from '../../components/offercheck/Input.jsx'

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
    location: '',
    currency: 'USD',
  })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [parseNotice, setParseNotice] = useState(null)
  const fileInputRef = useRef(null)

  // Same numbers CandidateNew.jsx's own "Load demo data" uses for the candidate-initiated
  // flow — kept identical so either entry point demos consistently.
  const loadDemoData = () => {
    const startDate = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    setForm({
      company: 'Stripe',
      role: 'Senior Software Engineer',
      base_salary: '180000',
      equity_value: '40000',
      bonus: '15000',
      start_date: startDate,
      candidate_ask: '190000',
      location: 'Seattle, WA',
      currency: 'USD',
    })
    setParseNotice(null)
    setError('')
  }

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
          location: form.location.trim() || undefined,
          currency: form.currency,
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
    <PageShell>
      <div className="flex items-start justify-between gap-3 mb-2">
        <h1 className="font-display text-hero-sm text-ink-primary">You've been invited to negotiate</h1>
        <Button type="button" variant="secondary" size="sm" onClick={loadDemoData} className="shrink-0 mt-1">
          Load demo data
        </Button>
      </div>
      <p className="text-sm text-ink-muted mb-6">
        Enter your competing offer and your ask. These details stay private — the employer only ever sees a gap percentage.
      </p>

      <div className="mb-6 p-4 rounded-xl bg-bg-surface border border-dashed border-border-strong">
        <label className="flex items-center justify-between gap-3 cursor-pointer">
          <div>
            <p className="text-sm font-medium text-ink-primary">Upload your offer letter (PDF)</p>
            <p className="text-xs text-ink-muted mt-0.5">Optional — we'll prefill the fields below for you to review</p>
          </div>
          <span className="shrink-0 w-24 text-center inline-flex items-center justify-center h-9 px-3 rounded-lg bg-teal-subtle border-[1.5px] border-teal text-teal text-xs font-medium transition-colors duration-150 hover:bg-teal-subtle/70">
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
            <FieldLabel>Company</FieldLabel>
            <Input value={form.company} onChange={update('company')} placeholder="Stripe" required />
          </div>
          <div>
            <FieldLabel>Role</FieldLabel>
            <Input value={form.role} onChange={update('role')} placeholder="Senior Engineer" required />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <FieldLabel>Base salary</FieldLabel>
            <Input mono type="number" min="0" value={form.base_salary} onChange={update('base_salary')} placeholder="180000" required />
          </div>
          <div>
            <FieldLabel>Equity / yr</FieldLabel>
            <Input mono type="number" min="0" value={form.equity_value} onChange={update('equity_value')} placeholder="40000" />
          </div>
          <div>
            <FieldLabel>Bonus</FieldLabel>
            <Input mono type="number" min="0" value={form.bonus} onChange={update('bonus')} placeholder="15000" />
          </div>
        </div>

        <div>
          <FieldLabel>Start date</FieldLabel>
          <Input type="date" value={form.start_date} onChange={update('start_date')} required />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-border">
          <div className="sm:col-span-2">
            <FieldLabel>Location (optional)</FieldLabel>
            <Input value={form.location} onChange={update('location')} placeholder="Seattle, WA or London" />
          </div>
          <div>
            <FieldLabel>Currency</FieldLabel>
            <Select value={form.currency} onChange={update('currency')}>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
            </Select>
          </div>
          <p className="sm:col-span-3 text-xs text-ink-muted -mt-1.5">
            Helps us compare your offer against real market data for your area. Skip it and we'll use national
            averages instead.
          </p>
        </div>

        <div className="pt-2 border-t border-border">
          <FieldLabel>Your ask at this employer</FieldLabel>
          <Input mono type="number" min="0" value={form.candidate_ask} onChange={update('candidate_ask')} placeholder="185000" required />
        </div>

        {error && (
          <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm animate-rise-in">
            {error}
          </div>
        )}

        <Button type="submit" variant="primary" size="lg" fullWidth loading={submitting}>
          {submitting ? 'Submitting…' : 'Join negotiation'}
        </Button>
      </form>
    </PageShell>
  )
}
