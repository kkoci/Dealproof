import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offercheckCheckCompanyKey, offercheckCreateInvite, offercheckGetInvite } from '../../api.js'

// luxe SKILL.md "Controls, Dials & Selectors" control anatomy: named transition properties
// (never `transition: all`) at the spec's 120ms smooth-out easing for hover/focus.
const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12] transition-[background-color,border-color,box-shadow] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]'
const labelClass = 'block text-xs font-medium text-ink-secondary mb-1.5'
// Primary action button: named-property transition + luxe Press Feedback (scale(0.96) on :active,
// a separate 100ms duration so the press reads snappier than the 150ms hover crossfade).
const primaryButtonClass =
  'transition-[background-color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] active:scale-[0.96] active:duration-100 disabled:active:scale-100'
// Small icon/text buttons (Copy, Check status): same press feedback, lighter transition.
const smallButtonClass =
  'transition-[background-color,color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] active:scale-[0.96] active:duration-100 disabled:active:scale-100'

export default function CompanyNew() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('offercheck_api_key') || '')
  const [keyInput, setKeyInput] = useState('')
  // Verified *before* the form renders — see offercheckCheckCompanyKey. Starts 'empty' rather
  // than null so a key-less first render goes straight to the key-entry screen.
  const [keyStatus, setKeyStatus] = useState('empty')
  const [form, setForm] = useState({
    band_min: '', band_mid: '', band_max: '',
    requirements: '', employer_authority_limit: '', employer_priorities: '',
  })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [invite, setInvite] = useState(null)
  const [copied, setCopied] = useState(false)
  const [status, setStatus] = useState(null)
  const [checking, setChecking] = useState(false)

  const update = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  // Same band numbers EmployerSession.jsx's own "Load demo data" uses for the human flow —
  // keeping them identical means a solo demo run (this form -> candidate join -> employer
  // session) lines up without the demo-er having to remember or re-type anything.
  const loadDemoData = () => {
    setForm((f) => ({
      ...f,
      band_min: '155000',
      band_mid: '175000',
      band_max: '195000',
      requirements: 'Senior Software Engineer, backend team',
    }))
  }

  useEffect(() => {
    if (!apiKey) {
      setKeyStatus('empty')
      return
    }
    let cancelled = false
    setKeyStatus('checking')
    offercheckCheckCompanyKey(apiKey).then((result) => {
      if (!cancelled) setKeyStatus(result)
    })
    return () => { cancelled = true }
  }, [apiKey])

  const handleUseKey = (e) => {
    e.preventDefault()
    if (!keyInput.trim()) return
    localStorage.setItem('offercheck_api_key', keyInput.trim())
    setApiKey(keyInput.trim())
  }

  const useDifferentKey = () => {
    localStorage.removeItem('offercheck_api_key')
    setApiKey('')
    setKeyStatus('empty')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const body = {
        band_min: Number(form.band_min),
        band_mid: Number(form.band_mid),
        band_max: Number(form.band_max),
        requirements: form.requirements.trim() || null,
      }
      if (form.employer_authority_limit) body.employer_authority_limit = Number(form.employer_authority_limit)
      if (form.employer_priorities.trim()) body.employer_priorities = form.employer_priorities.trim()

      const result = await offercheckCreateInvite(apiKey, body)
      setInvite(result)
      setStatus(null)
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  const checkStatus = async () => {
    setChecking(true)
    try {
      const data = await offercheckGetInvite(apiKey, invite.invite_id)
      setStatus(data)
    } catch (err) {
      setError(err.message || 'Could not check status')
    } finally {
      setChecking(false)
    }
  }

  if (keyStatus === 'empty' || keyStatus === 'malformed') {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-md mx-auto">
          <h1 className="text-2xl font-bold text-ink-primary mb-2">Start a negotiation</h1>
          <p className="text-sm text-ink-muted mb-6">Paste your company API key to open an invite.</p>
          <form onSubmit={handleUseKey} className="flex gap-2 mb-4">
            <input
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="oc_..."
              className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm font-mono focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12]"
            />
            <button type="submit" className={`px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-medium ${primaryButtonClass}`}>
              Go
            </button>
          </form>
          {keyStatus === 'malformed' && (
            <p className="text-xs text-danger mb-4">That doesn't look like a valid API key — check for typos.</p>
          )}
          <Link to="/offercheck/company/register" className="text-sm text-teal hover:text-teal-hover underline">
            Don't have a key? Register your company
          </Link>
        </div>
      </div>
    )
  }

  if (keyStatus === 'checking') {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-md mx-auto">
          <p className="text-sm text-ink-muted">Checking your key…</p>
        </div>
      </div>
    )
  }

  if (keyStatus === 'unregistered') {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-md mx-auto">
          <h1 className="text-2xl font-bold text-ink-primary mb-2">No company registered yet</h1>
          <p className="text-sm text-ink-muted mb-6">
            This server instance has no record of that key — register to get started.
          </p>
          <div className="flex items-center gap-4">
            <Link
              to="/offercheck/company/register"
              className="px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-medium transition-colors"
            >
              Register your company
            </Link>
            <button onClick={useDifferentKey} className="text-xs text-ink-muted hover:text-ink-secondary">
              Use a different key
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (invite) {
    const joinUrl = `${window.location.origin}${invite.candidate_join_link}`
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-lg mx-auto animate-rise-in">
          <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary mb-2">Invite created</h1>
          <p className="text-sm text-ink-muted mb-6">
            Send this link to the candidate. Their raw numbers stay private — you'll only ever see a gap percentage.
          </p>

          <div className="p-4 rounded-xl bg-bg-surface border border-border mb-4" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <p className="text-xs text-ink-muted mb-2">Candidate join link</p>
            <div className="flex gap-2">
              <input
                readOnly
                value={joinUrl}
                className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-bg-input border border-border text-ink-primary text-xs font-mono"
                onFocus={(e) => e.target.select()}
              />
              <button
                onClick={() => { navigator.clipboard?.writeText(joinUrl); setCopied(true) }}
                className={`w-16 shrink-0 px-3 py-2 rounded-lg bg-teal-subtle border-[1.5px] border-teal hover:bg-teal-subtle/70 text-teal text-xs font-medium ${smallButtonClass}`}
              >
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-bg-surface border border-border mb-6" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-ink-primary">Status</p>
              <button
                onClick={checkStatus}
                disabled={checking}
                className={`w-24 text-right text-xs text-teal hover:text-teal-hover disabled:opacity-50 ${smallButtonClass}`}
              >
                {checking ? 'Checking…' : 'Check status'}
              </button>
            </div>
            {status ? (
              status.status === 'CLAIMED' ? (
                <div className="animate-rise-in">
                  <p className="text-sm text-success font-medium mb-2">Claimed — negotiation is live.</p>
                  <a
                    href={`/offercheck/employer/${status.session_id}?token=${status.employer_token}`}
                    className={`inline-block px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-medium ${primaryButtonClass}`}
                  >
                    Open negotiation
                  </a>
                </div>
              ) : (
                <p className="text-sm text-ink-muted animate-rise-in">Not claimed yet.</p>
              )
            ) : (
              <p className="text-sm text-ink-muted">Not checked yet.</p>
            )}
          </div>

          <button
            onClick={() => { setInvite(null); setForm({ band_min: '', band_mid: '', band_max: '', requirements: '', employer_authority_limit: '', employer_priorities: '' }) }}
            className={`text-sm text-teal hover:text-teal-hover underline inline-block ${smallButtonClass}`}
          >
            Create another invite
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-lg mx-auto">
        <div className="flex items-start justify-between gap-3 mb-2">
          <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary">Start a negotiation</h1>
          <button
            type="button"
            onClick={loadDemoData}
            className="shrink-0 mt-1 px-2.5 py-1 rounded-md bg-bg-elevated hover:bg-border text-ink-secondary hover:text-ink-primary text-xs font-medium transition-all"
          >
            Load demo data
          </button>
        </div>
        <p className="text-sm text-ink-muted mb-6">
          Your salary band stays private. The candidate only ever sees a gap percentage.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelClass}>Role / context (shown only on your own dashboard)</label>
            <input className={inputClass} value={form.requirements} onChange={update('requirements')} placeholder="Senior Engineer, backend team" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-border">
            <div>
              <label className={labelClass}>Band min</label>
              <input className={inputClass} type="number" min="0" value={form.band_min} onChange={update('band_min')} placeholder="155000" required />
            </div>
            <div>
              <label className={labelClass}>Band mid</label>
              <input className={inputClass} type="number" min="0" value={form.band_mid} onChange={update('band_mid')} placeholder="175000" required />
            </div>
            <div>
              <label className={labelClass}>Band max</label>
              <input className={inputClass} type="number" min="0" value={form.band_max} onChange={update('band_max')} placeholder="195000" required />
            </div>
          </div>

          <p className="text-xs text-ink-muted pt-2 border-t border-border">
            You can enable AI negotiation from the session page after the candidate joins.
          </p>

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
            {submitting ? 'Creating…' : 'Get shareable candidate link'}
          </button>
        </form>
      </div>
    </div>
  )
}
