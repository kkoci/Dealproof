import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offercheckCheckCompanyKey, offercheckListCompanySessions } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'
import Badge from '../../components/offercheck/Badge.jsx'
import { Input } from '../../components/offercheck/Input.jsx'

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Awaiting band',
  EMPLOYER_RESPONDED: 'In progress',
  CANDIDATE_COUNTERED: 'In progress',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired',
}

const STATE_TONE = {
  PENDING_EMPLOYER: 'sealed',
  EMPLOYER_RESPONDED: 'teal',
  CANDIDATE_COUNTERED: 'teal',
  AGREED: 'success',
  WALKAWAY: 'danger',
  EXPIRED: 'neutral',
}

export default function Dashboard() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('offercheck_api_key') || '')
  const [keyInput, setKeyInput] = useState('')
  // Verified *before* the authenticated view renders — see offercheckCheckCompanyKey. Starts
  // 'empty' rather than null so a key-less first render goes straight to the key-entry screen
  // instead of flashing a "checking" state for nothing.
  const [keyStatus, setKeyStatus] = useState('empty')
  const [sessions, setSessions] = useState(null)
  const [error, setError] = useState('')

  const refresh = async (key) => {
    try {
      const data = await offercheckListCompanySessions(key)
      setSessions(data.sessions)
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load sessions')
      setSessions(null)
    }
  }

  useEffect(() => {
    if (!apiKey) {
      setKeyStatus('empty')
      return
    }
    let cancelled = false
    setKeyStatus('checking')
    offercheckCheckCompanyKey(apiKey).then((status) => {
      if (cancelled) return
      setKeyStatus(status)
      if (status === 'valid') refresh(apiKey)
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
    setSessions(null)
    setKeyStatus('empty')
  }

  if (keyStatus === 'empty' || keyStatus === 'malformed') {
    return (
      <PageShell>
        <h1 className="font-display text-hero-sm text-ink-primary mb-2">Company dashboard</h1>
        <p className="text-sm text-ink-muted mb-6">Paste your API key to view your verifications.</p>
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

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-hero-sm text-ink-primary">Company dashboard</h1>
        <div className="flex items-center gap-4">
          <Link to="/offercheck/company/new" className="focus-ring rounded text-xs text-teal hover:text-teal-hover font-medium">
            + Start a negotiation
          </Link>
          <button onClick={useDifferentKey} className="focus-ring rounded text-xs text-ink-muted hover:text-ink-secondary">
            Use a different key
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
      )}

      <Card padding="none" className="overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <span className="text-sm font-medium text-ink-primary">Verifications ({sessions?.length ?? 0})</span>
          <button onClick={() => refresh(apiKey)} className="focus-ring rounded text-xs text-teal hover:text-teal-hover">Refresh</button>
        </div>
        {sessions && sessions.length === 0 && (
          <p className="px-4 py-6 text-sm text-ink-muted italic">No verifications yet.</p>
        )}
        {sessions?.map((s) => (
          <div key={s.session_id} className="px-4 py-3 border-b border-border last:border-b-0 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <Badge tone={STATE_TONE[s.state] || 'neutral'} className="mb-1">
                {STATE_LABEL[s.state] || s.state}
              </Badge>
              <p className="text-xs text-ink-muted font-mono tnum truncate">{s.session_id}</p>
            </div>
            <div className="flex items-center gap-4 shrink-0">
              {s.gap_pct != null && (
                <span className="text-xs font-mono tnum text-ink-secondary">{s.gap_pct > 0 ? '+' : ''}{s.gap_pct.toFixed(1)}%</span>
              )}
              <span className="text-xs text-ink-muted">round {s.round_number}</span>
              <a href={s.employer_link} className="focus-ring rounded text-xs text-teal hover:text-teal-hover underline">
                Open
              </a>
            </div>
          </div>
        ))}
      </Card>
    </PageShell>
  )
}
