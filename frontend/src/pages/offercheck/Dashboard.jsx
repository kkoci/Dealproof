import React, { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { offercheckCheckCompanyKey, offercheckListCompanySessions, offercheckPurchaseCredits } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'
import Badge from '../../components/offercheck/Badge.jsx'
import { FieldLabel, Input } from '../../components/offercheck/Input.jsx'

// $25/credit — same figure already shown publicly on the Plans page
// (billing.PRICING["individual"]["price_usd"]); not fetched live since
// there's no GET endpoint exposing pricing outside of registration-time.
const PRICE_PER_CREDIT_USD = 25
const CREDIT_PRESETS = [5, 20, 50]

function BuyCreditsPanel({ apiKey, onPurchaseStarted }) {
  const [count, setCount] = useState(5)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setError('')
    setSubmitting(true)
    try {
      const origin = window.location.origin
      const { checkout_url } = await offercheckPurchaseCredits(apiKey, {
        credit_count: count,
        success_url: `${origin}/offercheck/dashboard?checkout=success`,
        cancel_url: `${origin}/offercheck/dashboard?checkout=cancelled`,
      })
      onPurchaseStarted?.()
      window.location.href = checkout_url
    } catch (e) {
      setError(e.message || 'Could not start checkout')
      setSubmitting(false)
    }
  }

  return (
    <Card padding="lg" className="mb-6">
      <p className="text-sm font-semibold text-ink-primary mb-1">Buy verification credits</p>
      <p className="text-xs text-ink-muted leading-relaxed mb-4">
        Each credit unlocks one attested verification (TDX proof + conduct credential + market comparator) at
        ${PRICE_PER_CREDIT_USD} per credit.
      </p>

      <div className="flex flex-wrap items-center gap-2 mb-3">
        {CREDIT_PRESETS.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => setCount(n)}
            className={`focus-ring px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors duration-150 ${
              count === n
                ? 'bg-teal-subtle border-teal text-teal'
                : 'bg-bg-elevated border-border text-ink-secondary hover:border-teal'
            }`}
          >
            {n} credits
          </button>
        ))}
      </div>

      <div className="flex items-end gap-3">
        <div className="w-32">
          <FieldLabel>Or a custom amount</FieldLabel>
          <Input
            mono
            type="number"
            min="1"
            max="1000"
            value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(1000, Number(e.target.value) || 1)))}
          />
        </div>
        <Button variant="primary" onClick={submit} loading={submitting} disabled={submitting}>
          {submitting ? 'Starting checkout…' : `Buy ${count} for $${count * PRICE_PER_CREDIT_USD}`}
        </Button>
      </div>

      {error && (
        <div className="mt-3 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
      )}
    </Card>
  )
}

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
  const [searchParams, setSearchParams] = useSearchParams()
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('offercheck_api_key') || '')
  const [keyInput, setKeyInput] = useState('')
  // Verified *before* the authenticated view renders — see offercheckCheckCompanyKey. Starts
  // 'empty' rather than null so a key-less first render goes straight to the key-entry screen
  // instead of flashing a "checking" state for nothing.
  const [keyStatus, setKeyStatus] = useState('empty')
  const [sessions, setSessions] = useState(null)
  const [billing, setBilling] = useState(null) // { credit_balance, plan, is_unlimited }
  const [error, setError] = useState('')
  // Set once, from the ?checkout= param Stripe redirects back with — cleared from the URL
  // immediately so a page refresh doesn't re-show a stale banner.
  const [checkoutOutcome] = useState(() => searchParams.get('checkout'))

  const refresh = async (key) => {
    try {
      const data = await offercheckListCompanySessions(key)
      setSessions(data.sessions)
      setBilling({ credit_balance: data.credit_balance, plan: data.plan, is_unlimited: data.is_unlimited })
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load sessions')
      setSessions(null)
    }
  }

  useEffect(() => {
    if (checkoutOutcome) {
      searchParams.delete('checkout')
      setSearchParams(searchParams, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

      {checkoutOutcome === 'success' && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-success-subtle border border-success/30 text-success text-sm">
          Payment received — your credit balance updates once Stripe's confirmation reaches us, usually within a
          few seconds. Hit Refresh below if it hasn't shown up yet.
        </div>
      )}
      {checkoutOutcome === 'cancelled' && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-sealed-subtle border border-sealed-border text-sealed-text text-sm">
          Checkout cancelled — no charge was made.
        </div>
      )}

      {error && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
      )}

      {billing && !billing.is_unlimited && billing.plan === 'individual' && (
        <>
          <Card padding="lg" className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-xs text-ink-muted mb-0.5">Verification credits</p>
              <p className="font-mono tnum text-2xl font-semibold text-ink-primary">{billing.credit_balance}</p>
            </div>
            <button onClick={() => refresh(apiKey)} className="focus-ring rounded text-xs text-teal hover:text-teal-hover">
              Refresh
            </button>
          </Card>
          <BuyCreditsPanel apiKey={apiKey} onPurchaseStarted={() => {}} />
        </>
      )}
      {billing?.is_unlimited && (
        <Card padding="lg" className="mb-6">
          <p className="text-xs text-ink-muted">Unlimited verification credit — no purchase needed.</p>
        </Card>
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
