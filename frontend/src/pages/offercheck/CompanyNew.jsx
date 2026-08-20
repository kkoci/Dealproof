import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offercheckCheckCompanyKey, offercheckCreateInvite, offercheckGetInvite } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'
import Checkbox from '../../components/offercheck/Checkbox.jsx'
import { FieldLabel, Input } from '../../components/offercheck/Input.jsx'
import { CopyIcon, CheckIcon } from '../../components/offercheck/icons.jsx'

export default function CompanyNew() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('offercheck_api_key') || '')
  const [keyInput, setKeyInput] = useState('')
  // Verified *before* the form renders — see offercheckCheckCompanyKey. Starts 'empty' rather
  // than null so a key-less first render goes straight to the key-entry screen.
  const [keyStatus, setKeyStatus] = useState('empty')
  const [form, setForm] = useState({
    band_min: '', band_mid: '', band_max: '',
    requirements: '', employer_authority_limit: '', employer_priorities: '',
    require_provenance_credential: false,
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
        require_provenance_credential: form.require_provenance_credential,
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
      <PageShell>
        <h1 className="font-display text-hero-sm text-ink-primary mb-2">Start a negotiation</h1>
        <p className="text-sm text-ink-muted mb-6">Paste your company API key to open an invite.</p>
        <form onSubmit={handleUseKey} className="flex gap-2 mb-4">
          <Input mono value={keyInput} onChange={(e) => setKeyInput(e.target.value)} placeholder="oc_..." className="flex-1 min-w-0" />
          <Button type="submit">Go</Button>
        </form>
        {keyStatus === 'malformed' && (
          <p className="text-xs text-danger mb-4">That doesn't look like a valid API key — check for typos.</p>
        )}
        <Link to="/offercheck/company/register" className="focus-ring rounded text-sm text-teal hover:text-teal-hover underline">
          Don't have a key? Register your company
        </Link>
      </PageShell>
    )
  }

  if (keyStatus === 'checking') {
    return (
      <PageShell>
        <p className="text-sm text-ink-muted">Checking your key…</p>
      </PageShell>
    )
  }

  if (keyStatus === 'unregistered') {
    return (
      <PageShell>
        <h1 className="font-display text-hero-sm text-ink-primary mb-2">No company registered yet</h1>
        <p className="text-sm text-ink-muted mb-6">
          This server instance has no record of that key — register to get started.
        </p>
        <div className="flex items-center gap-4">
          <Button as={Link} to="/offercheck/company/register">Register your company</Button>
          <button onClick={useDifferentKey} className="focus-ring rounded text-xs text-ink-muted hover:text-ink-secondary">
            Use a different key
          </button>
        </div>
      </PageShell>
    )
  }

  if (invite) {
    const joinUrl = `${window.location.origin}${invite.candidate_join_link}`
    return (
      <PageShell>
        <div className="animate-rise-in">
          <h1 className="font-display text-hero-sm text-ink-primary mb-2">Invite created</h1>
          <p className="text-sm text-ink-muted mb-2">
            Send this link to the candidate. Their raw numbers stay private — you'll only ever see a gap percentage.
          </p>
          <p className="text-xs mb-6">
            Verified credential required:{' '}
            <span className={invite.require_provenance_credential ? 'text-teal font-semibold' : 'text-ink-muted'}>
              {invite.require_provenance_credential ? 'Yes' : 'No'}
            </span>
          </p>

          <Card padding="sm" className="mb-4">
            <p className="text-xs text-ink-muted mb-2">Candidate join link</p>
            <div className="flex gap-2">
              <Input readOnly mono value={joinUrl} className="flex-1 min-w-0 !text-xs" onFocus={(e) => e.target.select()} />
              <Button
                variant="subtle"
                size="sm"
                className="w-16 shrink-0"
                onClick={() => { navigator.clipboard?.writeText(joinUrl); setCopied(true) }}
              >
                {copied ? <CheckIcon size={12} /> : <CopyIcon size={12} />}
                {copied ? 'Copied' : 'Copy'}
              </Button>
            </div>
          </Card>

          <Card padding="sm" className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-ink-primary">Status</p>
              <button
                onClick={checkStatus}
                disabled={checking}
                className="focus-ring rounded w-24 text-right text-xs text-teal hover:text-teal-hover disabled:opacity-50 transition-colors"
              >
                {checking ? 'Checking…' : 'Check status'}
              </button>
            </div>
            {status ? (
              status.status === 'CLAIMED' ? (
                <div className="animate-rise-in">
                  <p className="text-sm text-success font-medium mb-2">Claimed — negotiation is live.</p>
                  <Button as="a" size="sm" href={`/offercheck/employer/${status.session_id}?token=${status.employer_token}`}>
                    Open negotiation
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-ink-muted animate-rise-in">Not claimed yet.</p>
              )
            ) : (
              <p className="text-sm text-ink-muted">Not checked yet.</p>
            )}
          </Card>

          <button
            onClick={() => { setInvite(null); setForm({ band_min: '', band_mid: '', band_max: '', requirements: '', employer_authority_limit: '', employer_priorities: '', require_provenance_credential: false }) }}
            className="focus-ring rounded text-sm text-teal hover:text-teal-hover underline"
          >
            Create another invite
          </button>
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <div className="flex items-start justify-between gap-3 mb-2">
        <h1 className="font-display text-hero-sm text-ink-primary">Start a negotiation</h1>
        <Button type="button" variant="secondary" size="sm" onClick={loadDemoData} className="shrink-0 mt-1">
          Load demo data
        </Button>
      </div>
      <p className="text-sm text-ink-muted mb-6">
        Your salary band stays private. The candidate only ever sees a gap percentage.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <FieldLabel>Role / context (shown only on your own dashboard)</FieldLabel>
          <Input value={form.requirements} onChange={update('requirements')} placeholder="Senior Engineer, backend team" />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-border">
          <div>
            <FieldLabel>Band min</FieldLabel>
            <Input mono type="number" min="0" value={form.band_min} onChange={update('band_min')} placeholder="155000" required />
          </div>
          <div>
            <FieldLabel>Band mid</FieldLabel>
            <Input mono type="number" min="0" value={form.band_mid} onChange={update('band_mid')} placeholder="175000" required />
          </div>
          <div>
            <FieldLabel>Band max</FieldLabel>
            <Input mono type="number" min="0" value={form.band_max} onChange={update('band_max')} placeholder="195000" required />
          </div>
        </div>

        <div className="pt-2 border-t border-border">
          <Checkbox
            checked={form.require_provenance_credential}
            onChange={(e) => setForm((f) => ({ ...f, require_provenance_credential: e.target.checked }))}
          >
            Require a verified git-provenance credential before the candidate can respond.
            They'll prove real engineering experience straight from their commit history —
            no résumé needed, and we never store their GitHub token or repo names.
          </Checkbox>
        </div>

        <p className="text-xs text-ink-muted pt-2 border-t border-border">
          You can enable AI negotiation from the session page after the candidate joins.
        </p>

        {error && (
          <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm animate-rise-in">
            {error}
          </div>
        )}

        <Button type="submit" variant="primary" size="lg" fullWidth loading={submitting}>
          {submitting ? 'Creating…' : 'Get shareable candidate link'}
        </Button>
      </form>
    </PageShell>
  )
}
