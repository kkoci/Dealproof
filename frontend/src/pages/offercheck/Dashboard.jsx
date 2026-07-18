import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offercheckCheckCompanyKey, offercheckConnectAts, offercheckListCompanySessions } from '../../api.js'

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Awaiting band',
  EMPLOYER_RESPONDED: 'In progress',
  CANDIDATE_COUNTERED: 'In progress',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired',
}

const STATE_COLOR = {
  AGREED: 'text-success',
  WALKAWAY: 'text-danger',
  EXPIRED: 'text-ink-muted',
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
  const [atsProvider, setAtsProvider] = useState('greenhouse')
  const [atsKey, setAtsKey] = useState('')
  const [atsStatus, setAtsStatus] = useState('')

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

  const handleConnectAts = async (e) => {
    e.preventDefault()
    setAtsStatus('')
    try {
      await offercheckConnectAts(apiKey, { provider: atsProvider, api_key: atsKey })
      setAtsStatus(`Connected to ${atsProvider}.`)
      setAtsKey('')
    } catch (err) {
      setAtsStatus(err.message || 'Could not connect')
    }
  }

  if (keyStatus === 'empty' || keyStatus === 'malformed') {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-md mx-auto">
          <h1 className="text-2xl font-bold text-ink-primary mb-2">Company dashboard</h1>
          <p className="text-sm text-ink-muted mb-6">Paste your API key to view your verifications.</p>
          <form onSubmit={handleUseKey} className="flex gap-2 mb-4">
            <input
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="oc_..."
              className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm font-mono focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12]"
            />
            <button type="submit" className="px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-medium transition-colors">
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

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-ink-primary">Company dashboard</h1>
          <div className="flex items-center gap-4">
            <Link to="/offercheck/company/new" className="text-xs text-teal hover:text-teal-hover font-medium">
              + Start a negotiation
            </Link>
            <button onClick={useDifferentKey} className="text-xs text-ink-muted hover:text-ink-secondary">
              Use a different key
            </button>
          </div>
        </div>

        <div className="mb-6 p-4 rounded-xl bg-bg-surface border border-border" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <p className="text-sm font-medium text-ink-primary mb-3">Connect an ATS</p>
          <form onSubmit={handleConnectAts} className="flex flex-col sm:flex-row gap-2">
            <select
              value={atsProvider}
              onChange={(e) => setAtsProvider(e.target.value)}
              className="px-3 py-2 rounded-lg bg-bg-input border border-border text-ink-primary text-sm focus:outline-none focus:border-teal"
            >
              <option value="greenhouse">Greenhouse</option>
              <option value="lever">Lever</option>
              <option value="workday">Workday</option>
            </select>
            <input
              value={atsKey}
              onChange={(e) => setAtsKey(e.target.value)}
              placeholder="ATS API key"
              className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12]"
            />
            <button type="submit" className="px-4 py-2 rounded-lg bg-transparent border-[1.5px] border-border-strong text-ink-secondary hover:bg-bg-elevated text-sm font-medium transition-colors">
              Connect
            </button>
          </form>
          {atsStatus && <p className="text-xs text-ink-muted mt-2">{atsStatus}</p>}
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
        )}

        <div className="rounded-xl bg-bg-surface border border-border overflow-hidden" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
          <div className="px-4 py-3 border-b border-border flex items-center justify-between">
            <span className="text-sm font-medium text-ink-primary">Verifications ({sessions?.length ?? 0})</span>
            <button onClick={() => refresh(apiKey)} className="text-xs text-teal hover:text-teal-hover">Refresh</button>
          </div>
          {sessions && sessions.length === 0 && (
            <p className="px-4 py-6 text-sm text-ink-muted italic">No verifications yet.</p>
          )}
          {sessions?.map((s) => (
            <div key={s.session_id} className="px-4 py-3 border-b border-border last:border-b-0 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className={`text-sm font-medium ${STATE_COLOR[s.state] || 'text-ink-secondary'}`}>
                  {STATE_LABEL[s.state] || s.state}
                </p>
                <p className="text-xs text-ink-muted font-mono truncate">{s.session_id}</p>
              </div>
              <div className="flex items-center gap-4 shrink-0">
                {s.gap_pct != null && (
                  <span className="text-xs font-mono text-ink-secondary">{s.gap_pct > 0 ? '+' : ''}{s.gap_pct.toFixed(1)}%</span>
                )}
                <span className="text-xs text-ink-muted">round {s.round_number}</span>
                <a
                  href={s.employer_link}
                  className="text-xs text-teal hover:text-teal-hover underline"
                >
                  Open
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
