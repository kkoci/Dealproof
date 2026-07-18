import React, { useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useSearchParams } from 'react-router-dom'
import { offercheckCandidateApproval, offercheckCandidateApprovalPackage, offercheckCandidateMove, offercheckEnableCandidateAgentic, offercheckEnableCandidatePackageAgentic, offercheckGetAttestation, offercheckGetCredential, offercheckGetSession, offercheckStartAgentic, offercheckStartAgenticPackage } from '../../api.js'

const APPROVAL_LABEL = { approve: 'approve', request_more_rounds: 'ask for more rounds', decline: 'decline' }
const TERMINAL_STATES = ['AGREED', 'WALKAWAY', 'EXPIRED', 'DECLINED', 'STALEMATE']

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

const POLL_MS = 1500

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12] transition-all'
const labelClass = 'block text-xs font-medium text-ink-secondary mb-1.5'

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Waiting for the employer',
  EMPLOYER_RESPONDED: 'Your turn',
  CANDIDATE_COUNTERED: 'Waiting for the employer',
  PENDING_APPROVAL: 'Outcome reached — your approval needed',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired — no agreement reached',
  DECLINED: 'Declined',
  STALEMATE: 'Stalemate — no agreement reached',
}

const STATE_BADGE = {
  PENDING_EMPLOYER: 'bg-bg-elevated text-neutral',
  EMPLOYER_RESPONDED: 'bg-success-subtle text-success',
  CANDIDATE_COUNTERED: 'bg-bg-elevated text-neutral',
  PENDING_APPROVAL: 'bg-sealed-subtle text-sealed-text',
  AGREED: 'bg-success-subtle text-success',
  WALKAWAY: 'bg-danger-subtle text-danger',
  EXPIRED: 'bg-bg-elevated text-neutral',
  DECLINED: 'bg-danger-subtle text-danger',
  STALEMATE: 'bg-bg-elevated text-neutral',
}

function Spinner() {
  return <span className="inline-block w-3.5 h-3.5 border-2 border-white/60 border-t-transparent rounded-full animate-spin" />
}

function GapMeter({ gapPct }) {
  if (gapPct === null || gapPct === undefined) return null
  const abs = Math.abs(gapPct)
  const color = abs > 5 ? 'text-gap-large' : abs > 2 ? 'text-gap-closing' : 'text-gap-zero'
  const fill = abs > 5 ? 'bg-gap-large' : abs > 2 ? 'bg-gap-closing' : 'bg-gap-zero'
  const clamped = Math.max(-50, Math.min(50, gapPct))
  const pos = ((clamped + 50) / 100) * 100
  return (
    <div className="mb-6">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-xs text-ink-muted">Gap to employer's current position</span>
        <span className={`font-mono font-bold text-3xl ${color}`}>
          {gapPct > 0 ? '+' : ''}{gapPct.toFixed(1)}%
        </span>
      </div>
      <div className="relative h-1.5 rounded-full bg-border">
        <div
          className={`absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full ${fill}`}
          style={{ left: `${Math.min(50, pos)}%`, width: `${Math.abs(pos - 50)}%` }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow shadow-black/20 border border-border-strong"
          style={{ left: `calc(${pos}% - 6px)` }}
        />
      </div>
    </div>
  )
}

// Chat-bubble round history — own moves right-aligned/teal, the other party's left-aligned/grey.
// Works for both the live polled view.history and a just-completed agentic result.transcript
// (callers normalize transcript rounds to the same {round_number, actor, move, value} shape).
function RoundHistory({ history, myActor }) {
  if (!history || history.length === 0) return null
  return (
    <div className="mb-4 space-y-2">
      {history.map((h) => {
        const isMine = h.actor === myActor
        return (
          <div key={h.round_number} className={`flex ${isMine ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] px-3 py-1.5 rounded-lg text-xs ${
                isMine
                  ? 'bg-teal-subtle border border-teal-border text-teal-text'
                  : 'bg-bg-elevated border border-border text-ink-primary'
              }`}
            >
              <div className="flex items-center justify-between gap-3 mb-0.5">
                <span className="font-medium">{h.actor === 'employer' ? 'Employer' : 'Candidate'}</span>
                <span className="text-[10px] text-ink-muted">Round {h.round_number}</span>
              </div>
              <div className="font-mono uppercase font-semibold">
                {h.move}{h.value != null ? ` $${h.value.toLocaleString()}` : ''}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// Compact per-term comparison table for package rounds — used both for the live polled
// view.package_history and a just-completed package agentic result.transcript (same shape:
// {round, actor, move, package, total_comp}).
function PackageRoundHistory({ history }) {
  if (!history || history.length === 0) return null
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-xs min-w-[420px]">
        <thead>
          <tr className="text-ink-muted border-b border-border">
            <th className="text-left font-medium py-1 px-1">Term</th>
            {history.map((r) => (
              <th key={r.round} className="text-right font-medium py-1 px-1">
                R{r.round} {r.actor === 'employer' ? '🏢' : '🧑'}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Object.keys(PACKAGE_TERM_LABELS).map((field, fi) => {
            const values = history.map((r) => r.package?.[field])
            return (
              <tr key={field} className={fi % 2 === 0 ? '' : 'bg-bg-elevated/60'}>
                <td className="py-1 px-1 text-ink-secondary">{PACKAGE_TERM_LABELS[field]}</td>
                {values.map((v, i) => {
                  const changed = i > 0 && values[i - 1] != null && v !== values[i - 1]
                  return (
                    <td key={i} className={`text-right py-1 px-1 font-mono ${changed ? 'text-teal font-semibold' : 'text-ink-primary'}`}>
                      {formatPackageValue(field, v)}
                    </td>
                  )
                })}
              </tr>
            )
          })}
          <tr className="border-t border-border">
            <td className="py-1 px-1 text-ink-secondary font-medium">Total comp</td>
            {history.map((r) => (
              <td key={r.round} className="text-right py-1 px-1 font-mono text-ink-primary font-semibold">
                {r.total_comp != null ? `$${Math.round(r.total_comp).toLocaleString()}` : '—'}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
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
    <div className="mt-4 p-4 rounded-xl bg-bg-surface border border-border" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      {receipt ? (
        <>
          {receipt.tee_attested ? (
            <div className="flex items-center gap-2 mb-2 px-2.5 py-1 rounded-md bg-success-subtle border border-success w-fit">
              <span className="text-xs font-semibold text-success-text">🛡️ Verified by Intel TDX</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-2 px-2.5 py-1 rounded-md bg-sealed-subtle border border-sealed-border w-fit">
              <span className="text-xs font-semibold text-sealed-text">Simulation mode — no real TEE hardware</span>
            </div>
          )}
          <p className="text-xs text-ink-muted leading-relaxed mb-2">
            {receipt.tee_attested
              ? 'Verified by secure, tamper-proof computation — neither side could see or alter the other’s private numbers, and the result can’t be faked.'
              : 'This demo run skipped the real secure hardware — for testing only, not a verified result.'}
          </p>
          <p className="text-[11px] font-mono text-ink-muted break-all mb-3">{receipt.attestation}</p>
          {cred && (
            <div className="pt-3 border-t border-border">
              <span className={`text-xs font-semibold ${cred.genuine_negotiation ? 'text-success' : 'text-sealed'}`}>
                {cred.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
              </span>
              <p className="text-xs text-ink-muted mt-1">{cred.summary}</p>
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-ink-muted italic">{err || 'Loading attestation receipt…'}</p>
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
      setErr(/already sealed/i.test(e.message || '') ? 'AI negotiation already enabled' : (e.message || 'Could not enable AI negotiation'))
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-4">
        <button
          onClick={() => setOpen(true)}
          className="w-full px-4 py-2.5 rounded-lg bg-teal-subtle border-[1.5px] border-teal text-teal text-sm font-medium hover:bg-teal-subtle/70 transition-all"
        >
          Enable AI negotiation
        </button>
        <p className="mt-1.5 text-xs text-ink-muted">
          An AI agent will negotiate on your behalf, using the private floor you set below — it will never agree to a number below that floor.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="mt-4 p-4 rounded-xl bg-bg-surface border border-border space-y-3">
      <p className="text-sm font-medium text-ink-primary">Enable AI negotiation</p>
      <p className="text-xs text-ink-muted">
        A Claude agent will negotiate on your behalf once the employer is ready too. Your floor is sealed — never shown to the employer, even to their agent.
      </p>
      <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border">
        <label className="block text-xs font-medium text-sealed-text mb-1.5">🔒 Your walk-away floor — private, only you see this</label>
        <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={floor} onChange={(e) => setFloor(e.target.value)} placeholder="175000" required />
      </div>
      <div>
        <label className={labelClass}>Priorities (optional)</label>
        <input className={inputClass} value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="base matters more than equity" />
      </div>
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !floor} className="flex-1 px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-semibold disabled:opacity-50 transition-colors">
          {submitting ? 'Sealing…' : 'Seal & enable'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-lg bg-bg-elevated hover:bg-border text-ink-secondary text-sm transition-colors">
          Cancel
        </button>
      </div>
      <p className="text-[11px] text-ink-muted">
        Sealing locks in your number privately — the other side never sees it, only the eventual outcome.
      </p>
    </form>
  )
}

function EnablePackageAgenticButton({ sessionId, token, visible, onEnabled }) {
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
      await offercheckEnableCandidatePackageAgentic(sessionId, {
        token,
        candidate_total_comp_floor: Number(floor),
        candidate_package_priorities: priorities.trim() || undefined,
      })
      setOpen(false)
      onEnabled?.()
    } catch (e) {
      setErr(/already sealed/i.test(e.message || '') ? 'AI negotiation already enabled' : (e.message || 'Could not enable AI negotiation'))
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-3">
        <button
          onClick={() => setOpen(true)}
          className="w-full px-4 py-2.5 rounded-lg bg-teal-subtle border-[1.5px] border-teal text-teal text-sm font-medium hover:bg-teal-subtle/70 transition-all"
        >
          Enable AI negotiation (full package)
        </button>
        <p className="mt-1.5 text-xs text-ink-muted">
          An AI agent will negotiate your full compensation package on your behalf, using the private floor you set below — it will never agree below that floor.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="mt-3 p-4 rounded-xl bg-bg-surface border border-border space-y-3">
      <p className="text-sm font-medium text-ink-primary">Enable AI negotiation (full package)</p>
      <p className="text-xs text-ink-muted">
        A Claude agent will negotiate the full compensation package on your behalf. Your floor is sealed — never shown to the employer.
      </p>
      <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border">
        <label className="block text-xs font-medium text-sealed-text mb-1.5">🔒 Your walk-away floor — total comp, private</label>
        <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={floor} onChange={(e) => setFloor(e.target.value)} placeholder="250000" required />
      </div>
      <div>
        <label className={labelClass}>Priorities (optional)</label>
        <input className={inputClass} value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="base matters more than equity" />
      </div>
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !floor} className="flex-1 px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-semibold disabled:opacity-50 transition-colors">
          {submitting ? 'Sealing…' : 'Seal & enable'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-lg bg-bg-elevated hover:bg-border text-ink-secondary text-sm transition-colors">
          Cancel
        </button>
      </div>
      <p className="text-[11px] text-ink-muted">
        Sealing locks in your number privately — the other side never sees it, only the eventual outcome.
      </p>
    </form>
  )
}

function AgenticPanel({ sessionId, token, visible, view, onComplete }) {
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
    <div className="mt-4 p-4 rounded-xl bg-teal-subtle border border-teal-border">
      {!result && (
        <>
          <p className="text-sm font-medium text-ink-primary mb-1">Let AI agents negotiate</p>
          <p className="text-xs text-ink-secondary mb-3">
            Both sides have sealed their private numbers. Two Claude agents will negotiate from here —
            your floor never crosses to the employer's agent, only offer amounts and moves do.
          </p>
          <button
            onClick={run}
            disabled={running}
            className="w-full px-4 py-2.5 rounded-lg bg-success hover:bg-success-hover text-white text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
          >
            {running ? (
              <>
                <Spinner />
                Agents negotiating… Round {view?.round_number ?? 0} of {view?.max_rounds ?? 5}
              </>
            ) : 'Let agents negotiate'}
          </button>
          {err && <p className="text-xs text-danger mt-2">{err}</p>}
        </>
      )}
      {result && (
        <>
          <span className="inline-block text-[10px] uppercase tracking-wide text-teal-text font-semibold bg-white px-1.5 py-0.5 rounded mb-2">
            Negotiated by AI agents
          </span>
          <p className="text-sm font-semibold text-ink-primary mb-2">
            {result.state === 'AGREED'
              ? `Agents agreed at $${result.agreed_price?.toLocaleString()}`
              : result.state === 'WALKAWAY'
                ? 'Agents walked away'
                : 'Agents ran out of rounds'}
          </p>
          <RoundHistory
            history={result.transcript.map((r) => ({ round_number: r.round, actor: r.actor, move: r.move, value: r.value }))}
            myActor="candidate"
          />
        </>
      )}
    </div>
  )
}

function PackageAgenticPanel({ sessionId, token, visible, view, onComplete }) {
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
    <div className="mt-4 p-4 rounded-xl bg-teal-subtle border border-teal-border">
      {!result && (
        <>
          <p className="text-sm font-medium text-ink-primary mb-1">Let AI agents negotiate the full package</p>
          <p className="text-xs text-ink-secondary mb-3">
            Base, equity, signing bonus, annual bonus, remote policy, start date, and PTO — negotiated
            simultaneously. Floors and budgets never cross, only the package on the table each round.
          </p>
          <button
            onClick={run}
            disabled={running}
            className="w-full px-4 py-2.5 rounded-lg bg-success hover:bg-success-hover text-white text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2 transition-colors"
          >
            {running ? (
              <>
                <Spinner />
                Agents negotiating… Round {view?.package_round_number ?? 0} of {view?.max_rounds ?? 5}
              </>
            ) : 'Let agents negotiate (full package)'}
          </button>
          {err && <p className="text-xs text-danger mt-2">{err}</p>}
        </>
      )}
      {result && (
        <>
          <span className="inline-block text-[10px] uppercase tracking-wide text-teal-text font-semibold bg-white px-1.5 py-0.5 rounded mb-2">
            Negotiated by AI agents
          </span>
          <p className="text-sm font-semibold text-ink-primary mb-3">
            {result.state === 'AGREED'
              ? 'Agreed package'
              : result.state === 'WALKAWAY'
                ? 'Agents walked away'
                : 'Agents ran out of rounds'}
          </p>
          <div className="mb-3">
            <PackageRoundHistory history={result.transcript} />
          </div>
          {result.credential && (
            <div className="pt-3 border-t border-teal-border">
              <span className={`text-xs font-semibold ${result.credential.genuine_negotiation ? 'text-success' : 'text-sealed'}`}>
                {result.credential.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
              </span>
              <p className="text-xs text-ink-muted mt-1">{result.credential.summary}</p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// The one human touchpoint per negotiation cycle: agents (or a human) reach an outcome,
// PENDING_APPROVAL, and each side casts exactly one vote — approve, ask for more rounds, or
// decline. Never turn-based (current_turn() returns null here), so both sides can act any time.
function ApprovalPanel({ sessionId, token, visible, view, packageMode, onVoted }) {
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')

  if (!visible) return null

  const myVote = packageMode ? view.my_package_approval_vote : view.my_approval_vote
  const otherVote = packageMode ? view.other_package_approval_vote : view.other_approval_vote

  const vote = async (decision) => {
    setErr('')
    setSubmitting(true)
    try {
      if (packageMode) {
        await offercheckCandidateApprovalPackage(sessionId, { token, decision })
      } else {
        await offercheckCandidateApproval(sessionId, { token, decision })
      }
      onVoted?.()
    } catch (e) {
      setErr(e.message || 'Could not record your vote')
    } finally {
      setSubmitting(false)
    }
  }

  if (myVote) {
    return (
      <div className="mt-4 p-4 rounded-xl bg-bg-surface border border-border">
        <p className="text-sm text-ink-primary mb-1">
          You voted to <span className="font-semibold">{APPROVAL_LABEL[myVote]}</span>.
        </p>
        <p className="text-xs text-ink-muted italic">
          {otherVote ? `The employer voted to ${APPROVAL_LABEL[otherVote]}.` : 'Waiting for the employer to respond…'}
        </p>
      </div>
    )
  }

  return (
    <div className="mt-4 p-4 rounded-xl bg-bg-surface border border-border space-y-3">
      <p className="text-sm font-medium text-ink-primary">
        {packageMode ? 'Agents reached a package agreement — your call' : 'Agents reached an outcome — your call'}
      </p>
      {!packageMode && view.agreed_price != null && (
        <p className="text-xs text-ink-muted">
          Agreed price: <span className="font-mono font-semibold text-ink-primary">${view.agreed_price.toLocaleString()}</span>
        </p>
      )}
      {otherVote && (
        <p className="text-xs text-teal-text bg-teal-subtle border border-teal-border rounded-lg px-3 py-2">
          The employer already voted to {APPROVAL_LABEL[otherVote]}.
        </p>
      )}
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="flex gap-2">
        <button disabled={submitting} onClick={() => vote('approve')} className="flex-1 px-3 py-2.5 rounded-lg bg-success hover:bg-success-hover text-white text-sm font-semibold disabled:opacity-40 transition-colors">
          Approve
        </button>
        <button disabled={submitting} onClick={() => vote('request_more_rounds')} className="flex-1 px-3 py-2.5 rounded-lg bg-transparent border-[1.5px] border-border-strong text-ink-secondary text-sm font-medium hover:bg-bg-elevated disabled:opacity-40 transition-colors">
          More rounds
        </button>
        <button disabled={submitting} onClick={() => vote('decline')} className="flex-1 px-3 py-2.5 rounded-lg bg-danger hover:bg-danger-hover text-white text-sm font-semibold disabled:opacity-40 transition-colors">
          Decline
        </button>
      </div>
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
  //
  // Both channels can be enabled at once (nothing stops sealing both authority limits), and
  // start-agentic runs the scalar negotiation to completion synchronously. If the scalar side
  // finishes first — before package_round_number ever ticks past 0 — activeState/isTerminal must
  // not lock onto the scalar's terminal state, or the not-yet-run package button/panel vanish
  // for good (package_round_number can never become > 0 once its own "enable"/"run" controls are
  // hidden). So package also counts as "active" once it's merely enabled and the scalar channel
  // already finished, as long as package itself isn't terminal yet.
  const packageStarted = view && view.package_round_number > 0
  const packageEnabled = view && view.package_agentic_ready
  const scalarTerminal = view && TERMINAL_STATES.includes(view.state)
  const packageTerminal = view && TERMINAL_STATES.includes(view.package_state)
  const packageActive = view && (packageStarted || (packageEnabled && scalarTerminal && !packageTerminal))
  const activeState = view && (packageActive ? view.package_state : view.state)
  const activeRound = view && (packageActive ? view.package_round_number : view.round_number)
  const isTerminal = view && TERMINAL_STATES.includes(activeState)
  const pendingApproval = view && activeState === 'PENDING_APPROVAL'
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
        <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary mb-2">Verification status</h1>

        {consistency && !consistency.verified && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-sealed-subtle border border-sealed-border text-sealed-text text-xs">
            Heads up — some details didn't pass the consistency check: {consistency.issues.join('; ')}
          </div>
        )}

        {absoluteEmployerLink && !view?.band_set && (
          <div className="mb-6 p-4 rounded-xl bg-bg-surface border border-border" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <p className="text-xs text-ink-muted mb-2">Send this link to the employer:</p>
            <div className="flex gap-2">
              <input
                readOnly
                value={absoluteEmployerLink}
                className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-bg-elevated border border-border text-ink-secondary text-xs font-mono"
                onFocus={(e) => e.target.select()}
              />
              <button
                onClick={() => navigator.clipboard?.writeText(absoluteEmployerLink)}
                className="px-3 py-2 rounded-lg bg-teal-subtle border-[1.5px] border-teal hover:bg-teal-subtle/70 text-teal text-xs font-medium transition-all"
              >
                Copy
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
        )}

        {view && (
          <div className="p-5 rounded-xl bg-bg-surface border border-border" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
            <div className="flex items-center justify-between mb-4">
              <span className={`inline-block px-2.5 py-1 rounded-md text-sm font-semibold ${STATE_BADGE[activeState] || 'bg-bg-elevated text-neutral'}`}>
                {STATE_LABEL[activeState] || activeState}
              </span>
              <span className="text-xs font-mono text-ink-muted">round {activeRound} of {view.max_rounds}</span>
            </div>

            <GapMeter gapPct={view.gap_pct} />

            {view.my_current_value != null && (
              <p className="text-xs text-ink-muted mb-4">
                Your current ask: <span className="font-mono font-semibold text-ink-primary">${view.my_current_value.toLocaleString()}</span>
              </p>
            )}

            {view.state === 'AGREED' && (
              <p className="text-sm text-success font-medium mb-4">
                Agreed at ${view.agreed_price?.toLocaleString()}
              </p>
            )}

            <RoundHistory history={view.history} myActor="candidate" />

            {view.package_history.length > 0 && (
              <div className="mb-4 pt-3 border-t border-border">
                <p className="text-xs text-ink-muted mb-2">Package negotiation</p>
                <PackageRoundHistory history={view.package_history} />
              </div>
            )}

            {view.package_converged_hint && !isTerminal && (
              <div className="mb-4 px-3 py-2 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs">
                Within 2% of total comp — consider accepting.
              </div>
            )}

            {!isTerminal && !myTurn && !pendingApproval && (
              <p className="text-xs text-ink-muted italic">Waiting for the other side to respond…</p>
            )}

            <ApprovalPanel
              sessionId={sessionId}
              token={token}
              visible={Boolean(pendingApproval)}
              view={view}
              packageMode={Boolean(packageActive)}
              onVoted={refresh}
            />

            {!isTerminal && myTurn && !packageActive && !pendingApproval && (
              <div className="space-y-3 pt-3 border-t border-border">
                <div className="flex gap-2">
                  <input
                    type="number"
                    min="0"
                    value={counterValue}
                    onChange={(e) => setCounterValue(e.target.value)}
                    placeholder="New ask"
                    className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12]"
                  />
                  <button
                    disabled={acting || !counterValue}
                    onClick={() => act('counter', Number(counterValue))}
                    className="px-4 py-2 rounded-lg bg-transparent border-[1.5px] border-border-strong text-ink-secondary text-sm font-medium hover:bg-bg-elevated disabled:opacity-40 transition-colors"
                  >
                    Counter
                  </button>
                </div>
                <div className="flex gap-2">
                  <button
                    disabled={acting}
                    onClick={() => act('accept')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-success hover:bg-success-hover text-white text-sm font-semibold disabled:opacity-40 transition-colors"
                  >
                    Accept
                  </button>
                  <button
                    disabled={acting}
                    onClick={() => act('walk')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-danger hover:bg-danger-hover text-white text-sm font-semibold disabled:opacity-40 transition-colors"
                  >
                    Walk away
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Three real states, distinct copy for each (see EnableAgenticButton/onEnabled): neither
            sealed -> plain CTA below with no extra note; other side already sealed -> nudge banner
            ABOVE the CTA; I've sealed, other side hasn't -> green confirmation banner (no CTA,
            it's already gone). Once both are sealed, agentic_ready flips and AgenticPanel takes
            over with its own "both sides have sealed... Let agents negotiate" copy — that's the
            fourth state, the transition into the actual negotiation starting. */}
        {view && !view.my_agentic_sealed && view.other_agentic_sealed && !isTerminal && (
          <div className="mt-4 px-4 py-2.5 rounded-lg bg-teal-subtle border border-teal-border text-teal-text text-xs">
            The employer has already enabled AI negotiation (salary) — enable yours to get started.
          </div>
        )}
        <EnableAgenticButton
          sessionId={sessionId}
          token={token}
          visible={Boolean(view && !view.my_agentic_sealed && !isTerminal)}
          onEnabled={refresh}
        />
        {view && view.my_agentic_sealed && !view.agentic_ready && !isTerminal && (
          <div className="mt-4 px-4 py-2.5 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs flex items-center gap-2">
            <span>✓ AI negotiation enabled (salary) — waiting for the employer to enable their side too.</span>
          </div>
        )}

        {view && !view.my_package_agentic_sealed && view.other_package_agentic_sealed && !isTerminal && (
          <div className="mt-3 px-4 py-2.5 rounded-lg bg-teal-subtle border border-teal-border text-teal-text text-xs">
            The employer has already enabled package AI negotiation — enable yours to get started.
          </div>
        )}
        <EnablePackageAgenticButton
          sessionId={sessionId}
          token={token}
          visible={Boolean(view && !view.my_package_agentic_sealed && !isTerminal)}
          onEnabled={refresh}
        />
        {view && view.my_package_agentic_sealed && !view.package_agentic_ready && !isTerminal && (
          <div className="mt-3 px-4 py-2.5 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs flex items-center gap-2">
            <span>✓ Package AI negotiation enabled — waiting for the employer to enable their side too.</span>
          </div>
        )}

        <AgenticPanel
          sessionId={sessionId}
          token={token}
          view={view}
          visible={Boolean(view?.agentic_ready && !isTerminal)}
          onComplete={refresh}
        />

        <PackageAgenticPanel
          sessionId={sessionId}
          token={token}
          view={view}
          visible={Boolean(view?.package_agentic_ready && !isTerminal)}
          onComplete={refresh}
        />

        <AttestationPanel sessionId={sessionId} token={token} visible={Boolean(isTerminal)} />
      </div>
    </div>
  )
}
