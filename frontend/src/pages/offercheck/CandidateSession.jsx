import React, { useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useSearchParams } from 'react-router-dom'
import { offercheckCandidateMove, offercheckEnableCandidateAgentic, offercheckGetAttestation, offercheckGetCredential, offercheckGetSession, offercheckStartAgentic, offercheckStartAgenticPackage } from '../../api.js'

const PACKAGE_TERM_LABELS = {
  base: 'Base', equity_grant: 'Equity', vesting_years: 'Vesting (yrs)', cliff_months: 'Cliff (mo)',
  signing_bonus: 'Signing bonus', annual_bonus_pct: 'Bonus %', remote: 'Remote', start_date_days: 'Start (days)', pto_days: 'PTO days',
}

function formatPackageValue(field, value) {
  if (value == null) return '—'
  if (field === 'remote') return value
  if (['vesting_years', 'cliff_months', 'start_date_days', 'pto_days', 'annual_bonus_pct'].includes(field)) return value
  return `$${Number(value).toLocaleString()}`
}

const POLL_MS = 3000

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all'
const labelClass = 'block text-xs font-medium text-gray-400 mb-1.5'

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Waiting for the employer',
  EMPLOYER_RESPONDED: 'Your turn',
  CANDIDATE_COUNTERED: 'Waiting for the employer',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired — no agreement reached',
}

function GapMeter({ gapPct }) {
  if (gapPct === null || gapPct === undefined) return null
  const clamped = Math.max(-50, Math.min(50, gapPct))
  const pos = ((clamped + 50) / 100) * 100
  return (
    <div className="mb-6">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-xs text-gray-500">Gap to employer's current position</span>
        <span className={`text-lg font-mono font-semibold ${gapPct > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
          {gapPct > 0 ? '+' : ''}{gapPct.toFixed(1)}%
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-gray-800/80">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-600" />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-emerald-400 shadow shadow-emerald-900/60"
          style={{ left: `calc(${pos}% - 6px)` }}
        />
      </div>
    </div>
  )
}

function AttestationPanel({ sessionId, token, visible }) {
  const [receipt, setReceipt] = useState(null)
  const [cred, setCred] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!visible) return
    let cancelled = false
    offercheckGetAttestation(sessionId, token)
      .then((data) => { if (!cancelled) setReceipt(data) })
      .catch((e) => { if (!cancelled) setErr(e.message || 'Attestation not available yet') })
    offercheckGetCredential(sessionId, { token }).then((data) => { if (!cancelled) setCred(data) }).catch(() => {})
    return () => { cancelled = true }
  }, [sessionId, token, visible])

  if (!visible) return null

  return (
    <div className="mt-4 p-4 rounded-xl bg-gray-900/40 border border-gray-800/40">
      {receipt ? (
        <>
          <div className="flex items-center gap-2 mb-2">
            <span className={`relative flex h-2 w-2`}>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${receipt.tee_attested ? 'bg-emerald-400' : 'bg-yellow-400'}`} />
            </span>
            <span className="text-xs font-semibold text-gray-200">
              {receipt.tee_attested
                ? 'Verified by hardware attestation'
                : 'Simulation mode — no real TEE hardware'}
            </span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed mb-2">
            This verification ran inside a TDX enclave. Neither party's raw data was observable by the platform.
          </p>
          <p className="text-[11px] font-mono text-gray-600 break-all mb-3">{receipt.attestation}</p>
          {cred && (
            <div className="pt-3 border-t border-gray-800/60">
              <span className={`text-xs font-semibold ${cred.genuine_negotiation ? 'text-emerald-400' : 'text-amber-400'}`}>
                {cred.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
              </span>
              <p className="text-xs text-gray-500 mt-1">{cred.summary}</p>
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-gray-500 italic">{err || 'Loading attestation receipt…'}</p>
      )}
    </div>
  )
}

function EnableAgenticButton({ sessionId, token, visible, onEnabled }) {
  const [open, setOpen] = useState(false)
  const [floor, setFloor] = useState('')
  const [priorities, setPriorities] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')

  if (!visible) return null

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    setSubmitting(true)
    try {
      await offercheckEnableCandidateAgentic(sessionId, {
        token,
        candidate_floor: Number(floor),
        candidate_priorities: priorities.trim() || undefined,
      })
      setOpen(false)
      onEnabled?.()
    } catch (e) {
      setErr(e.message || 'Could not enable AI negotiation')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="mt-4 w-full px-4 py-2.5 rounded-lg bg-gray-800/60 hover:bg-gray-700/60 border border-gray-700/50 text-gray-200 text-sm font-medium transition-all"
      >
        Enable AI negotiation
      </button>
    )
  }

  return (
    <form onSubmit={submit} className="mt-4 p-4 rounded-xl bg-gray-900/40 border border-gray-800/40 space-y-3">
      <p className="text-sm font-medium text-gray-200">Enable AI negotiation</p>
      <p className="text-xs text-gray-500">
        A Claude agent will negotiate on your behalf once the employer is ready too. Your floor is sealed — never shown to the employer, even to their agent.
      </p>
      <div>
        <label className={labelClass}>Your walk-away floor (never revealed)</label>
        <input className={inputClass} type="number" min="0" value={floor} onChange={(e) => setFloor(e.target.value)} placeholder="175000" required />
      </div>
      <div>
        <label className={labelClass}>Priorities (optional)</label>
        <input className={inputClass} value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="base matters more than equity" />
      </div>
      {err && <p className="text-xs text-red-400">{err}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !floor} className="flex-1 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-50">
          {submitting ? 'Sealing…' : 'Seal & enable'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-lg bg-gray-800/60 hover:bg-gray-700/60 text-gray-300 text-sm">
          Cancel
        </button>
      </div>
    </form>
  )
}

function AgenticPanel({ sessionId, token, visible, onComplete }) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')

  if (!visible && !result) return null

  const run = async () => {
    setRunning(true)
    setErr('')
    try {
      const data = await offercheckStartAgentic(sessionId, { token })
      setResult(data)
      onComplete?.()
    } catch (e) {
      setErr(e.message || 'Agentic negotiation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="mt-4 p-4 rounded-xl bg-gray-900/40 border border-emerald-800/30">
      {!result && (
        <>
          <p className="text-sm font-medium text-gray-200 mb-1">Let AI agents negotiate</p>
          <p className="text-xs text-gray-500 mb-3">
            Both sides have sealed their private numbers. Two Claude agents will negotiate from here —
            your floor never crosses to the employer's agent, only offer amounts and moves do.
          </p>
          <button
            onClick={run}
            disabled={running}
            className="w-full px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-50"
          >
            {running ? 'Agents negotiating…' : 'Let agents negotiate'}
          </button>
          {err && <p className="text-xs text-red-400 mt-2">{err}</p>}
        </>
      )}
      {result && (
        <>
          <p className="text-sm font-semibold text-gray-200 mb-2">
            {result.state === 'AGREED'
              ? `Agents agreed at $${result.agreed_price?.toLocaleString()}`
              : result.state === 'WALKAWAY'
                ? 'Agents walked away'
                : 'Agents ran out of rounds'}
          </p>
          <div className="space-y-1.5">
            {result.transcript.map((r) => (
              <div key={r.round} className="flex items-center justify-between text-xs text-gray-500">
                <span>Round {r.round} — {r.actor}</span>
                <span className="font-mono text-gray-400">
                  {r.move.toUpperCase()}{r.value != null ? ` $${r.value.toLocaleString()}` : ''}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function PackageAgenticPanel({ sessionId, token, visible, onComplete }) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')

  if (!visible && !result) return null

  const run = async () => {
    setRunning(true)
    setErr('')
    try {
      const data = await offercheckStartAgenticPackage(sessionId, { token })
      setResult(data)
      onComplete?.()
    } catch (e) {
      setErr(e.message || 'Package negotiation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="mt-4 p-4 rounded-xl bg-gray-900/40 border border-emerald-800/30">
      {!result && (
        <>
          <p className="text-sm font-medium text-gray-200 mb-1">Let AI agents negotiate the full package</p>
          <p className="text-xs text-gray-500 mb-3">
            Base, equity, signing bonus, annual bonus, remote policy, start date, and PTO — negotiated
            simultaneously. Floors and budgets never cross, only the package on the table each round.
          </p>
          <button
            onClick={run}
            disabled={running}
            className="w-full px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-50"
          >
            {running ? 'Agents negotiating…' : 'Let agents negotiate (full package)'}
          </button>
          {err && <p className="text-xs text-red-400 mt-2">{err}</p>}
        </>
      )}
      {result && (
        <>
          <p className="text-sm font-semibold text-gray-200 mb-3">
            {result.state === 'AGREED'
              ? 'Agreed package'
              : result.state === 'WALKAWAY'
                ? 'Agents walked away'
                : 'Agents ran out of rounds'}
          </p>
          <div className="overflow-x-auto -mx-1 mb-3">
            <table className="w-full text-xs min-w-[420px]">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800/60">
                  <th className="text-left font-medium py-1 px-1">Term</th>
                  {result.transcript.map((r) => (
                    <th key={r.round} className="text-right font-medium py-1 px-1">
                      R{r.round} {r.actor === 'employer' ? '🏢' : '🧑'}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.keys(PACKAGE_TERM_LABELS).map((field, fi) => {
                  const values = result.transcript.map((r) => r.package?.[field])
                  return (
                    <tr key={field} className={fi % 2 === 0 ? '' : 'bg-gray-800/20'}>
                      <td className="py-1 px-1 text-gray-400">{PACKAGE_TERM_LABELS[field]}</td>
                      {values.map((v, i) => {
                        const changed = i > 0 && values[i - 1] != null && v !== values[i - 1]
                        return (
                          <td key={i} className={`text-right py-1 px-1 font-mono ${changed ? 'text-emerald-400' : 'text-gray-300'}`}>
                            {formatPackageValue(field, v)}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
                <tr className="border-t border-gray-800/60">
                  <td className="py-1 px-1 text-gray-400 font-medium">Total comp</td>
                  {result.transcript.map((r) => (
                    <td key={r.round} className="text-right py-1 px-1 font-mono text-gray-200">
                      {r.total_comp != null ? `$${Math.round(r.total_comp).toLocaleString()}` : '—'}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          {result.credential && (
            <div className="pt-3 border-t border-gray-800/60">
              <span className={`text-xs font-semibold ${result.credential.genuine_negotiation ? 'text-emerald-400' : 'text-amber-400'}`}>
                {result.credential.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
              </span>
              <p className="text-xs text-gray-500 mt-1">{result.credential.summary}</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function CandidateSession() {
  const { sessionId } = useParams()
  const [searchParams] = useSearchParams()
  const location = useLocation()
  const token = searchParams.get('token')

  const [view, setView] = useState(null)
  const [error, setError] = useState('')
  const [counterValue, setCounterValue] = useState('')
  const [acting, setActing] = useState(false)
  const employerLink = location.state?.employerLink
  const consistency = location.state?.consistency
  const pollRef = useRef(null)

  const refresh = async () => {
    try {
      const data = await offercheckGetSession(sessionId, token)
      setView(data)
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load session')
    }
  }

  useEffect(() => {
    refresh()
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => clearInterval(pollRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, token])

  // Package mode is a parallel state machine (see app.offercheck.package's module docstring) —
  // its progress lives in package_state/package_turn, never in the scalar state/turn fields.
  // Once it's actually been used (package_round_number > 0) it's the negotiation in progress,
  // so terminal/turn must defer to it — otherwise this side gets stuck showing "waiting" forever
  // after a package AI negotiation agrees, because the scalar state never advances on its own.
  const packageActive = view && view.package_round_number > 0
  const isTerminal = view && (
    packageActive
      ? ['AGREED', 'WALKAWAY', 'EXPIRED'].includes(view.package_state)
      : ['AGREED', 'WALKAWAY', 'EXPIRED'].includes(view.state)
  )
  const myTurn = view && (packageActive ? view.package_turn === 'candidate' : view.turn === 'candidate')

  const act = async (move, value) => {
    setActing(true)
    setError('')
    try {
      const data = await offercheckCandidateMove(sessionId, { token, move, value: value ?? null })
      setView(data)
    } catch (err) {
      setError(err.message || 'Move failed')
    } finally {
      setActing(false)
    }
  }

  const absoluteEmployerLink = employerLink ? `${window.location.origin}${employerLink}` : null

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-lg mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Verification status</h1>

        {consistency && !consistency.verified && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-amber-950/40 border border-amber-800/50 text-amber-300 text-xs">
            Heads up — some details didn't pass the consistency check: {consistency.issues.join('; ')}
          </div>
        )}

        {absoluteEmployerLink && !view?.band_set && (
          <div className="mb-6 p-4 rounded-xl bg-gray-900/40 border border-gray-800/40">
            <p className="text-xs text-gray-500 mb-2">Send this link to the employer:</p>
            <div className="flex gap-2">
              <input
                readOnly
                value={absoluteEmployerLink}
                className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-300 text-xs font-mono"
                onFocus={(e) => e.target.select()}
              />
              <button
                onClick={() => navigator.clipboard?.writeText(absoluteEmployerLink)}
                className="px-3 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-xs font-medium transition-all"
              >
                Copy
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-red-950/40 border border-red-800/50 text-red-400 text-sm">{error}</div>
        )}

        {view && (
          <div className="p-5 rounded-xl bg-gray-900/40 border border-gray-800/40">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-semibold text-gray-200">{STATE_LABEL[view.state] || view.state}</span>
              <span className="text-xs font-mono text-gray-500">round {view.round_number} / {view.max_rounds}</span>
            </div>

            <GapMeter gapPct={view.gap_pct} />

            {view.my_current_value != null && (
              <p className="text-xs text-gray-500 mb-4">
                Your current ask: <span className="font-mono text-gray-300">${view.my_current_value.toLocaleString()}</span>
              </p>
            )}

            {view.state === 'AGREED' && (
              <p className="text-sm text-emerald-400 font-medium mb-4">
                Agreed at ${view.agreed_price?.toLocaleString()}
              </p>
            )}

            {view.history.length > 0 && (
              <div className="mb-4 space-y-1.5">
                {view.history.map((h) => (
                  <div key={h.round_number} className="flex items-center justify-between text-xs text-gray-500">
                    <span>Round {h.round_number} — {h.actor === 'employer' ? 'Employer' : 'Candidate'}</span>
                    <span className="font-mono uppercase text-gray-400">
                      {h.move}{h.value != null ? ` $${h.value.toLocaleString()}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {view.package_history.length > 0 && (
              <div className="mb-4 space-y-1.5 pt-3 border-t border-gray-800/60">
                <p className="text-xs text-gray-500 mb-1">Package negotiation</p>
                {view.package_history.map((h) => (
                  <div key={`pkg-${h.round}`} className="flex items-center justify-between text-xs text-gray-500">
                    <span>Round {h.round} — {h.actor === 'employer' ? 'Employer' : 'Candidate'}</span>
                    <span className="font-mono uppercase text-gray-400">
                      {h.move}{h.total_comp != null ? ` $${Math.round(h.total_comp).toLocaleString()} total comp` : ''}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {!isTerminal && !myTurn && (
              <p className="text-xs text-gray-500 italic">Waiting for the other side to respond…</p>
            )}

            {!isTerminal && myTurn && (
              <div className="space-y-3 pt-3 border-t border-gray-800/60">
                <div className="flex gap-2">
                  <input
                    type="number"
                    min="0"
                    value={counterValue}
                    onChange={(e) => setCounterValue(e.target.value)}
                    placeholder="New ask"
                    className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm"
                  />
                  <button
                    disabled={acting || !counterValue}
                    onClick={() => act('counter', Number(counterValue))}
                    className="px-4 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-sm font-medium disabled:opacity-40"
                  >
                    Counter
                  </button>
                </div>
                <div className="flex gap-2">
                  <button
                    disabled={acting}
                    onClick={() => act('accept')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-40"
                  >
                    Accept
                  </button>
                  <button
                    disabled={acting}
                    onClick={() => act('walk')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-red-950/60 hover:bg-red-900/60 border border-red-800/50 text-red-300 text-sm font-semibold disabled:opacity-40"
                  >
                    Walk away
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <EnableAgenticButton
          sessionId={sessionId}
          token={token}
          visible={Boolean(view && !view.my_agentic_sealed && !isTerminal)}
          onEnabled={refresh}
        />

        <AgenticPanel
          sessionId={sessionId}
          token={token}
          visible={Boolean(view?.agentic_ready && !isTerminal)}
          onComplete={refresh}
        />

        <PackageAgenticPanel
          sessionId={sessionId}
          token={token}
          visible={Boolean(view?.package_agentic_ready && !isTerminal)}
          onComplete={refresh}
        />

        <AttestationPanel sessionId={sessionId} token={token} visible={Boolean(isTerminal)} />
      </div>
    </div>
  )
}
