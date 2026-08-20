import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { offercheckStartAgentic, offercheckVerifyDemoToken } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'
import Badge from '../../components/offercheck/Badge.jsx'

export default function Demo() {
  const [searchParams] = useSearchParams()
  // Read once from the URL and keep in component memory only — never localStorage,
  // per the magic-link design: these links are short-lived and single-use.
  const [token] = useState(() => searchParams.get('token') || '')
  const [sessionId] = useState(() => searchParams.get('session') || '')

  const [checking, setChecking] = useState(true)
  const [valid, setValid] = useState(false)
  const [checkError, setCheckError] = useState('')

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [runError, setRunError] = useState('')

  useEffect(() => {
    if (!token || !sessionId) {
      setChecking(false)
      setCheckError('This link is missing its token or session — ask for a new one.')
      return
    }
    let cancelled = false
    offercheckVerifyDemoToken(token, sessionId)
      .then((data) => { if (!cancelled) setValid(Boolean(data.valid)) })
      .catch((e) => { if (!cancelled) setCheckError(e.message || 'Demo link expired — request a new one') })
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [token, sessionId])

  const run = async () => {
    setRunning(true)
    setRunError('')
    try {
      const data = await offercheckStartAgentic(sessionId, { demoToken: token })
      setResult(data)
    } catch (e) {
      setRunError(e.message || 'Agentic negotiation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <PageShell>
      <h1 className="font-display text-hero-sm text-ink-primary mb-2">Offer Check — live demo</h1>
      <p className="text-sm text-ink-muted mb-8">
        Two Claude agents negotiate a salary inside a TEE-attested revision loop. No login, no account.
      </p>

      {checking && <p className="text-sm text-ink-muted italic">Checking your link…</p>}

      {!checking && !valid && (
        <Card padding="lg" className="!bg-danger-subtle !border-danger/30">
          <p className="text-sm font-semibold text-danger mb-1">Demo link expired — request a new one</p>
          <p className="text-xs text-danger/80">{checkError}</p>
        </Card>
      )}

      {!checking && valid && !result && (
        <Card padding="lg" className="!bg-teal-subtle !border-teal-border">
          <p className="text-sm font-medium text-ink-primary mb-1">Ready to negotiate</p>
          <p className="text-xs text-ink-secondary mb-4">
            This link is valid and single-use. Clicking below runs the full negotiation —
            sealed floor and band never cross between agents, only offer amounts and moves do.
          </p>
          <Button variant="success" size="lg" fullWidth loading={running} onClick={run}>
            {running ? 'Agents negotiating…' : 'Let agents negotiate'}
          </Button>
          {runError && <p className="text-xs text-danger mt-2">{runError}</p>}
        </Card>
      )}

      {result && (
        <Card padding="lg" className="!bg-teal-subtle !border-teal-border">
          <Badge tone="teal" className="mb-2">Negotiated by AI agents</Badge>
          <p className="text-sm font-semibold text-ink-primary mb-3">
            {result.state === 'AGREED'
              ? `Agreed at $${result.agreed_price?.toLocaleString()}`
              : result.state === 'WALKAWAY'
                ? 'Agents walked away'
                : 'Agents ran out of rounds'}
          </p>
          <div className="space-y-1.5 mb-4">
            {result.transcript.map((r) => (
              <div key={r.round} className="flex items-center justify-between text-xs text-ink-secondary">
                <span>Round {r.round} — {r.actor === 'employer' ? 'Employer' : 'Candidate'}</span>
                <span className="font-mono tnum font-semibold text-ink-primary">
                  {r.move.toUpperCase()}{r.value != null ? ` $${r.value.toLocaleString()}` : ''}
                </span>
              </div>
            ))}
          </div>
          {result.credential && (
            <div className="pt-3 border-t border-teal-border mb-3">
              <span className={`text-xs font-semibold ${result.credential.genuine_negotiation ? 'text-success' : 'text-sealed'}`}>
                {result.credential.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
              </span>
              <p className="text-xs text-ink-muted mt-1">{result.credential.summary}</p>
            </div>
          )}
          <p className="text-[11px] font-mono tnum text-ink-muted break-all">{result.attestation}</p>
        </Card>
      )}
    </PageShell>
  )
}
