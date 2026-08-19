import React, { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getEnclaveAttestation, offercheckEmployerApproval, offercheckEmployerApprovalPackage, offercheckEmployerMove, offercheckEnableEmployerAgentic, offercheckEnableEmployerPackageAgentic, offercheckFileEmployerDispute, offercheckGetAttestation, offercheckGetCredential, offercheckGetDisputes, offercheckGetSession, offercheckSetEmployerBand, offercheckStartAgentic, offercheckStartAgenticPackage, offercheckUpdateEmployerDisputeStatus } from '../../api.js'

const SENIORITY_LABEL = { junior: 'Junior', mid: 'Mid-level', senior: 'Senior', staff: 'Staff+' }

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

// Dispute/contest surface (see app.offercheck.disputes) — mirrors that module's own constants/
// transition table exactly, so the UI never offers an action the backend would reject.
const DISPUTE_EVIDENCE_MAX_LENGTH = 1000 // app.offercheck.disputes.EVIDENCE_MAX_LENGTH
const DISPUTE_TYPE_LABEL = { process: 'Process', outcome: 'Outcome' }
const DISPUTE_STATUS_LABEL = { OPEN: 'Open', UNDER_REVIEW: 'Under review', RESOLVED: 'Resolved', DISMISSED: 'Dismissed' }
const DISPUTE_STATUS_BADGE = {
  OPEN: 'bg-sealed-subtle text-sealed-text',
  UNDER_REVIEW: 'bg-teal-subtle text-teal-text',
  RESOLVED: 'bg-success-subtle text-success-text',
  DISMISSED: 'bg-bg-elevated text-neutral',
}
// app.offercheck.disputes._VALID_TRANSITIONS: OPEN -> {UNDER_REVIEW, DISMISSED}, UNDER_REVIEW ->
// {RESOLVED, DISMISSED}; RESOLVED/DISMISSED are terminal (no further transitions offered).
const DISPUTE_NEXT_TRANSITIONS = { OPEN: ['UNDER_REVIEW', 'DISMISSED'], UNDER_REVIEW: ['RESOLVED', 'DISMISSED'], RESOLVED: [], DISMISSED: [] }
const TRANSITION_BUTTON_LABEL = { UNDER_REVIEW: 'Mark under review', RESOLVED: 'Mark resolved', DISMISSED: 'Dismiss' }
const OUTCOME_FIELD_LABEL = { final_gap_pct: 'Price movement from opening offer', market_percentile: 'Market percentile' }

function ordinal(n) {
  const rounded = Math.round(n)
  const mod100 = Math.abs(rounded) % 100
  if (mod100 >= 11 && mod100 <= 13) return `${rounded}th`
  switch (Math.abs(rounded) % 10) {
    case 1: return `${rounded}st`
    case 2: return `${rounded}nd`
    case 3: return `${rounded}rd`
    default: return `${rounded}th`
  }
}

function formatTimestamp(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Your turn',
  EMPLOYER_RESPONDED: 'Waiting for the candidate',
  CANDIDATE_COUNTERED: 'Your turn',
  PENDING_APPROVAL: 'Outcome reached — your approval needed',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired — no agreement reached',
  DECLINED: 'Declined',
  STALEMATE: 'Stalemate — no agreement reached',
}

const STATE_BADGE = {
  PENDING_EMPLOYER: 'bg-success-subtle text-success',
  EMPLOYER_RESPONDED: 'bg-bg-elevated text-neutral',
  CANDIDATE_COUNTERED: 'bg-success-subtle text-success',
  PENDING_APPROVAL: 'bg-sealed-subtle text-sealed-text',
  AGREED: 'bg-success-subtle text-success',
  WALKAWAY: 'bg-danger-subtle text-danger',
  EXPIRED: 'bg-bg-elevated text-neutral',
  DECLINED: 'bg-danger-subtle text-danger',
  STALEMATE: 'bg-bg-elevated text-neutral',
}

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border text-ink-primary placeholder:text-ink-muted text-sm focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.12] transition-all'
const labelClass = 'block text-xs font-medium text-ink-secondary mb-1.5'

function Spinner() {
  return <span className="inline-block w-3.5 h-3.5 border-2 border-white/60 border-t-transparent rounded-full animate-spin" />
}

// --- One spotlighted next action + stage spine ---
// Mirrors CandidateSession.jsx's getNextAction/getStageStatuses/StageSpine/ActionPanels exactly,
// adapted for two real differences on this side: there's no VerifyCredentialPanel (only the
// candidate can submit a provenance credential — this side just watches via
// ProvenanceStatusPanel), and there's a real precondition before any of the rest of the flow
// applies at all — the employer's band. getNextAction/getStageStatuses consume the exact same
// isTerminal/pendingApproval/myTurn/packageActive already derived in the component; they do not
// re-derive that logic.
const STAGE_ORDER = ['verify', 'choose', 'negotiating', 'decision', 'proof']
const STAGE_LABEL = {
  verify: 'Verify',
  choose: 'Choose mode',
  negotiating: 'Negotiating',
  decision: 'Decision',
  proof: 'Proof',
}

function getNextAction(view, { isTerminal, pendingApproval, myTurn, packageActive }) {
  if (!view) return null

  if (isTerminal) return { stage: 'proof', key: 'proof' }
  if (pendingApproval) return { stage: 'decision', key: 'approval' }
  if (!view.band_set) return { stage: 'choose', key: 'submitBand' }

  // The employer never verifies anything themselves — only the candidate can. While this
  // requirement is outstanding, the employer's own next action is genuinely "wait," not "verify."
  if (view.require_provenance_credential && !view.candidate_provenance_verified) {
    return { stage: 'verify', key: 'waitingForVerify' }
  }

  // "Choose mode" only applies before the negotiation has started at all. Gating this on "have I
  // sealed a track" alone breaks the very first manual turn: a fully-manual negotiator never
  // seals anything, so they'd be told to "choose" forever, even mid-turn. Any round history at
  // all — from either party — means the session is already underway.
  const negotiationStarted = Boolean(
    view.my_agentic_sealed || view.my_package_agentic_sealed || (view.history && view.history.length > 0)
  )
  if (!negotiationStarted) return { stage: 'choose', key: 'choose' }

  // Both tracks seal independently and can each become "ready to run" at different times. The
  // packageActive guard on the salary check matters for the documented edge case where the
  // scalar track already finished and negotiation has moved onto package.
  if (view.agentic_ready && !packageActive) return { stage: 'negotiating', key: 'runSalary' }
  if (view.package_agentic_ready) return { stage: 'negotiating', key: 'runPackage' }
  if (view.my_agentic_sealed && !view.agentic_ready) return { stage: 'negotiating', key: 'sealedWaitingSalary' }
  if (view.my_package_agentic_sealed && !view.package_agentic_ready) return { stage: 'negotiating', key: 'sealedWaitingPackage' }
  if (myTurn && !packageActive) return { stage: 'negotiating', key: 'respond' }
  return { stage: 'negotiating', key: 'waiting' }
}

// unresolvedNoAgreement: opt-in only, passed true from exactly one call site (EXPIRED-without-
// ever-reaching-PENDING_APPROVAL — see isExpiredNoAgreement in the component below). Every other
// terminal state (AGREED, WALKAWAY, DECLINED, STALEMATE) calls this with the flag unset/false and
// renders exactly as before — this only overrides 'negotiating'/'decision' from their normal
// 'done' (green checkmark, implying clean completion) to a distinct 'unresolved' status, since
// this specific case genuinely never produced a decision to complete.
function getStageStatuses(view, nextAction, { unresolvedNoAgreement = false } = {}) {
  if (!nextAction) return []
  const currentIndex = STAGE_ORDER.indexOf(nextAction.stage)
  const verifyApplicable = Boolean(view.require_provenance_credential)
  return STAGE_ORDER.map((key, i) => {
    if (key === 'verify' && !verifyApplicable) return { key, status: 'skip' }
    if (unresolvedNoAgreement && (key === 'negotiating' || key === 'decision')) return { key, status: 'unresolved' }
    if (i < currentIndex) return { key, status: 'done' }
    if (i === currentIndex) return { key, status: 'active' }
    return { key, status: 'future' }
  })
}

// Spatial "you are here" — read in under a second, no paragraph required. A "skip" stage (the
// Verify step on sessions that never required it) renders visibly de-emphasized rather than
// just unhighlighted, since it genuinely isn't part of this session's flow.
function StageSpine({ statuses }) {
  if (!statuses.length) return null
  return (
    <div className="mb-6 flex items-start">
      {statuses.map((s, i) => (
        <React.Fragment key={s.key}>
          <div className="flex flex-col items-center gap-1 flex-shrink-0 w-20">
            <div
              className={`w-3.5 h-3.5 rounded-full flex items-center justify-center flex-shrink-0 ${
                s.status === 'done' ? 'bg-success' :
                s.status === 'active' ? 'bg-teal ring-4 ring-teal/20' :
                s.status === 'unresolved' ? 'bg-sealed/60' :
                s.status === 'skip' ? 'bg-transparent border border-dashed border-border' :
                'bg-bg-elevated border border-border'
              }`}
            >
              {s.status === 'done' && (
                <svg className="w-2.5 h-2.5 text-white" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
              {/* Deliberately a dash, not a checkmark — this stage happened but didn't conclude
                  with an outcome, distinct from 'done'. Amber, not red: honest, not alarming. */}
              {s.status === 'unresolved' && (
                <svg className="w-2.5 h-2.5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeWidth={3} d="M6 12h12" />
                </svg>
              )}
            </div>
            <span
              className={`text-xs text-center leading-tight ${
                s.status === 'active' ? 'font-semibold text-ink-primary' :
                s.status === 'skip' ? 'text-ink-muted/40' :
                s.status === 'done' ? 'text-ink-secondary' :
                s.status === 'unresolved' ? 'text-sealed-text' :
                'text-ink-muted'
              }`}
            >
              {STAGE_LABEL[s.key]}
            </span>
          </div>
          {i < statuses.length - 1 && (
            <div className={`flex-1 h-px mt-1.5 ${s.status === 'done' ? 'bg-success/40' : 'bg-border'}`} />
          )}
        </React.Fragment>
      ))}
    </div>
  )
}

// Renders every action panel from ONE stable, always-mounted list, keyed and in a fixed order
// every render. The spotlighted item gets the highlighted-card treatment; non-spotlighted
// *collapsible* items are visually hidden (display:none) behind an "Other options" toggle.
//
// `collapsible` is the crucial distinction (see the regression this fixed — a real, shipped bug):
// only an actionable, not-yet-made CHOICE (an enable-agentic CTA) is ever fine to tuck behind a
// toggle. A PERSISTENT STATUS — ProvenanceStatusPanel's read-only text, a "waiting for the
// candidate" confirmation, a just-finished agentic run's result — must never be hidden just
// because something else is now the recommended next action, or it silently disappears the
// moment getNextAction() moves on. Callers pass `collapsible: false` for every such item; those
// always render in normal flow (optionally spotlighted, never hidden-by-default).
//
// Every item is unconditionally rendered every pass, in the same slot every render — only its
// className (and an optional title paragraph in its own fixed sibling slot) changes — so a
// component's internal state always survives regardless of which slot currently applies. See
// CandidateSession.jsx's ActionPanels for the full reasoning; this is the same component.
function ActionPanels({ items }) {
  const [open, setOpen] = useState(false)
  const otherCount = items.filter((it) => it.visible && it.collapsible && !it.isSpotlight).length

  return (
    <>
      {items.map((it) => {
        const hiddenBehindToggle = it.collapsible && !it.isSpotlight && !open
        return (
          <div
            key={it.key}
            className={
              !it.visible ? 'hidden' :
              it.isSpotlight ? 'mb-6 rounded-xl border-2 border-teal bg-bg-surface p-5' :
              hiddenBehindToggle ? 'hidden' : 'mb-3'
            }
            style={it.visible && it.isSpotlight ? { boxShadow: '0 0 0 4px rgba(13,148,136,0.08)' } : undefined}
          >
            {it.visible && it.isSpotlight && it.title && (
              <p className="text-sm font-semibold text-teal-text uppercase tracking-wide mb-3">{it.title}</p>
            )}
            {it.node}
          </div>
        )
      })}
      {otherCount > 0 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mb-6 text-xs font-medium text-ink-muted hover:text-ink-secondary underline underline-offset-2 transition-colors"
        >
          {open ? 'Hide other options' : `Other options (${otherCount})`}
        </button>
      )}
    </>
  )
}

// Pure orientation, no logic — mirrors CandidateSession.jsx's HowThisWorksStrip. A first-time
// visitor otherwise sees the band form, status card, EnableAgenticButton,
// EnablePackageAgenticButton, ProvenanceStatusPanel, ApprovalPanel, and AttestationPanel all with
// no explanation of order or purpose. Dismissed locally (no backend, no cross-session
// persistence) — this is a map, not a gate: doesn't touch any panel's visible={...} condition and
// isn't required reading to use the page.
function HowThisWorksStrip({ lines }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  return (
    <div className="mb-6 p-5 rounded-xl bg-teal-subtle border border-teal-border relative" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="absolute top-2.5 right-2.5 w-5 h-5 flex items-center justify-center rounded-md text-teal-text/60 hover:text-teal-text hover:bg-white/50 transition-colors"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      <p className="text-sm font-semibold text-teal-text uppercase tracking-wide mb-2 pr-6">How this works</p>
      <ol className="space-y-1.5">
        {lines.map((line, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-ink-secondary leading-relaxed">
            <span className="flex-shrink-0 w-4 h-4 rounded-full bg-white border border-teal-border text-teal-text text-[10px] font-bold flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <span>{line}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

const HOW_THIS_WORKS_LINES = [
  "See where things stand — you'll only ever see the gap, never the candidate's actual number.",
  'Respond yourself, or let an AI agent negotiate for you using a private authority limit only you set.',
  "If you required it, you'll see here once the candidate verifies their work history.",
  'Once there’s an outcome, you decide: approve it, decline it, or ask for another round.',
  'At the end, see cryptographic proof that everything ran exactly as claimed.',
]

// Small pill for the "Inside the TEE" boundary below. Mirrors CandidateSession.jsx's local
// TrustPill — Landing.jsx's TrustPill (devcred vertical) is dark-theme styled and isn't exported,
// so this is built from Offer Check's own light-mode success tokens instead (--color-success* is
// literally emerald, see tokens.css).
function TrustPill({ children }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white border border-success/30 text-success-text text-[10px] font-medium">
      {children}
    </span>
  )
}

// Verify, then release: wraps a sensitive input (sealed authority limit/budget) with a visually
// distinct boundary so it reads as "this goes into the attested enclave," plus the specific trust
// pills for what's actually attested here (see candidatesession_investigated_fix.md).
function TeeInputBoundary({ label, pills, children }) {
  return (
    <div className="p-3 rounded-lg bg-success-subtle border border-success/30 space-y-2.5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <span className="text-xs font-semibold text-success-text">🛡️ {label}</span>
        <div className="flex flex-wrap gap-1.5">
          {pills.map((p) => <TrustPill key={p}>{p}</TrustPill>)}
        </div>
      </div>
      {children}
    </div>
  )
}

// Shown inside a TeeInputBoundary while the enclave attestation is loading, or in place of it if
// verification failed — never a silent fallback to an unverified-but-usable form.
function EnclaveStatusNote({ loading, error }) {
  if (!loading && !error) return null
  return (
    <p className={`text-xs flex items-center gap-1.5 ${error ? 'text-danger' : 'text-sealed-text'}`}>
      {loading && <span className="inline-block w-3 h-3 border-2 border-sealed-text/60 border-t-transparent rounded-full animate-spin flex-shrink-0" />}
      {loading ? 'Verifying enclave attestation before enabling input…' : error}
    </p>
  )
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
        <span className="text-xs text-ink-muted">Gap: candidate's ask vs. your current position</span>
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

// Two attested external anchors, shown once AGREED — final_gap_pct (relative: did the price move
// from the employer's opening counter) and market_percentile (absolute: is the price sane against
// real external salary data). Both can be null on a perfectly normal session (no opening-counter
// anchor if the employer accepted immediately; no market data if the BLS/ONS lookup never matched
// this role) — rendered as a clear "unavailable" state rather than hidden or left blank. No source
// (BLS/ONS) is exposed anywhere in the attested payload, so this deliberately doesn't claim one.
function AttestedMetrics({ finalGapPct, marketPercentile }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      <div
        className="px-3 py-2 rounded-lg bg-bg-elevated border border-border"
        title="How far the final price moved from the employer's very first counter-offer — an anchor the negotiating agent never controlled."
      >
        <p className="text-[10px] uppercase tracking-wide text-ink-muted mb-0.5">Movement from opening offer</p>
        {finalGapPct != null ? (
          <p className="text-sm font-mono font-semibold text-ink-primary">
            {finalGapPct > 0 ? '+' : ''}{finalGapPct.toFixed(1)}% from opening offer
          </p>
        ) : (
          <p className="text-xs text-ink-muted italic">No opening-counter anchor on this session</p>
        )}
      </div>
      <div
        className="px-3 py-2 rounded-lg bg-bg-elevated border border-border"
        title="Where the agreed price falls against real external salary data for this role — an independent market comparator, computed once when the session agreed."
      >
        <p className="text-[10px] uppercase tracking-wide text-ink-muted mb-0.5">Market comparator</p>
        {marketPercentile != null ? (
          <p className="text-sm font-mono font-semibold text-ink-primary">{ordinal(marketPercentile)} percentile</p>
        ) : (
          <p className="text-xs text-ink-muted italic">Market data unavailable for this role</p>
        )}
      </div>
    </div>
  )
}

// One filed dispute — evidence, status, resolution note if present, and (if the dispute isn't
// already terminal) the buttons to advance it. Either party may act on either side's dispute, per
// app.offercheck.disputes' own actor gating (dismissing your own concern or acknowledging the
// other side's are both legitimate unilateral actions; RESOLVED is unilateral in this pass too —
// a documented judgment call, not a bug, see that module's docstring).
function DisputeRow({ sessionId, token, myActor, dispute, onChanged }) {
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState(null)
  const [note, setNote] = useState('')

  const updateFn = myActor === 'employer' ? offercheckUpdateEmployerDisputeStatus : offercheckUpdateCandidateDisputeStatus
  const nextOptions = DISPUTE_NEXT_TRANSITIONS[dispute.status] || []

  const transition = async (newStatus) => {
    setErr(null)
    setSubmitting(true)
    try {
      await updateFn(sessionId, dispute.dispute_id, { token, new_status: newStatus, resolution_note: note.trim() || undefined })
      setNote('')
      onChanged?.()
    } catch (e) {
      setErr(e.message || 'Could not update this dispute')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="p-3 rounded-lg border border-border bg-bg-elevated/40 space-y-2">
      <div className="flex items-center justify-between flex-wrap gap-1.5">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-ink-secondary">{DISPUTE_TYPE_LABEL[dispute.dispute_type]}</span>
          <span className="text-ink-muted text-xs">·</span>
          <span className="text-xs text-ink-muted">filed by {dispute.filed_by === myActor ? 'you' : dispute.filed_by === 'employer' ? 'employer' : 'candidate'}</span>
        </div>
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${DISPUTE_STATUS_BADGE[dispute.status] || 'bg-bg-elevated text-neutral'}`}>
          {DISPUTE_STATUS_LABEL[dispute.status] || dispute.status}
        </span>
      </div>

      {dispute.referenced_field && (
        <p className="text-[11px] text-ink-muted">References: {OUTCOME_FIELD_LABEL[dispute.referenced_field] || dispute.referenced_field}</p>
      )}

      <p className="text-xs text-ink-primary leading-relaxed whitespace-pre-wrap">{dispute.evidence}</p>

      {dispute.resolution_note && (
        <p className="text-xs text-ink-muted italic border-t border-border pt-2">Resolution note: {dispute.resolution_note}</p>
      )}

      <p className="text-[10px] text-ink-muted">
        Filed {formatTimestamp(dispute.filed_at)}
        {dispute.resolved_at ? ` · Resolved ${formatTimestamp(dispute.resolved_at)}` : ''}
      </p>

      {nextOptions.length > 0 && (
        <div className="pt-2 border-t border-border space-y-2">
          <input
            className={`${inputClass} text-xs py-1.5`}
            placeholder="Optional note…"
            value={note}
            maxLength={DISPUTE_EVIDENCE_MAX_LENGTH}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex gap-2">
            {nextOptions.map((status) => (
              <button
                key={status}
                type="button"
                disabled={submitting}
                onClick={() => transition(status)}
                className={`flex-1 px-2.5 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 transition-colors ${
                  status === 'RESOLVED'
                    ? 'bg-success hover:bg-success-hover text-white'
                    : status === 'DISMISSED'
                    ? 'bg-transparent border border-border-strong text-ink-secondary hover:bg-bg-elevated'
                    : 'bg-teal-subtle border border-teal-border text-teal-text hover:bg-teal-subtle/70'
                }`}
              >
                {submitting ? '…' : TRANSITION_BUTTON_LABEL[status]}
              </button>
            ))}
          </div>
          {err && <p className="text-[11px] text-danger">{err}</p>}
        </div>
      )}
    </div>
  )
}

// Filing form — collapsed to a single button until opened, matching EnableAgenticButton's own
// collapsed/expanded pattern on this page. Only ever rendered when session state is AGREED (see
// visible prop below), matching the backend's own SessionNotAgreed rejection rule, so the action
// is never even offered when it would just error. Outcome disputes gate their referenced_field
// options on the live SessionView's own final_gap_pct/market_percentile — no separate fetch needed
// for that check, since SessionView already carries both fields once AGREED.
function FileDisputeForm({ sessionId, token, myActor, view, visible, onFiled }) {
  const [open, setOpen] = useState(false)
  const [disputeType, setDisputeType] = useState('process')
  const [referencedField, setReferencedField] = useState('')
  const [evidence, setEvidence] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState(null)

  if (!visible) return null

  const fileFn = myActor === 'employer' ? offercheckFileEmployerDispute : offercheckFileCandidateDispute
  const finalGapAvailable = view?.final_gap_pct != null
  const marketPercentileAvailable = view?.market_percentile != null

  const submit = async (e) => {
    e.preventDefault()
    setErr(null)
    setSubmitting(true)
    try {
      await fileFn(sessionId, {
        token,
        dispute_type: disputeType,
        evidence,
        referenced_field: disputeType === 'outcome' ? (referencedField || null) : null,
      })
      setOpen(false)
      setEvidence('')
      setReferencedField('')
      setDisputeType('process')
      onFiled?.()
    } catch (e) {
      setErr({ message: e.message, status: e.status })
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <div className="mt-4">
        <button
          onClick={() => setOpen(true)}
          className="w-full px-4 py-2.5 rounded-lg bg-transparent border-[1.5px] border-border-strong text-ink-secondary text-sm font-medium hover:bg-bg-elevated transition-colors"
        >
          File a dispute
        </button>
        <p className="mt-1.5 text-xs text-ink-muted">
          Disagree with how this went, or with the result itself? File a dispute — it's recorded alongside the attestation, it never reopens the negotiation on its own.
        </p>
      </div>
    )
  }

  const isRateLimited = err?.status === 429
  const overSessionCap = isRateLimited && /per party per session/i.test(err.message || '')

  return (
    <form onSubmit={submit} className="mt-4 p-5 rounded-xl bg-bg-surface border border-border space-y-3">
      <p className="text-sm font-medium text-ink-primary">File a dispute</p>
      <p className="text-xs text-ink-muted">
        This is a flag for a human to review — filing never changes the outcome or reopens negotiation on its own.
      </p>

      <div>
        <label className={labelClass}>Dispute type</label>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => { setDisputeType('process'); setReferencedField('') }}
            className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${disputeType === 'process' ? 'bg-teal text-white border-teal' : 'bg-transparent border-border-strong text-ink-secondary hover:bg-bg-elevated'}`}
          >
            Process
          </button>
          <button
            type="button"
            onClick={() => setDisputeType('outcome')}
            className={`flex-1 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${disputeType === 'outcome' ? 'bg-teal text-white border-teal' : 'bg-transparent border-border-strong text-ink-secondary hover:bg-bg-elevated'}`}
          >
            Outcome
          </button>
        </div>
        <p className="mt-1.5 text-[11px] text-ink-muted">
          {disputeType === 'process'
            ? "The record doesn't match what happened, or a stated rule wasn't followed."
            : 'The negotiated result itself seems unfair — grounded in an attested figure below, not just a feeling.'}
        </p>
      </div>

      {disputeType === 'outcome' && (
        <div>
          <label className={labelClass}>Which attested figure?</label>
          <div className="space-y-1.5">
            <label className={`flex items-center gap-2 text-xs ${finalGapAvailable ? 'text-ink-primary cursor-pointer' : 'text-ink-muted/50 cursor-not-allowed'}`}>
              <input
                type="radio"
                name="referenced_field"
                disabled={!finalGapAvailable}
                checked={referencedField === 'final_gap_pct'}
                onChange={() => setReferencedField('final_gap_pct')}
              />
              Price movement from opening offer{!finalGapAvailable && ' — not available on this session'}
            </label>
            <label className={`flex items-center gap-2 text-xs ${marketPercentileAvailable ? 'text-ink-primary cursor-pointer' : 'text-ink-muted/50 cursor-not-allowed'}`}>
              <input
                type="radio"
                name="referenced_field"
                disabled={!marketPercentileAvailable}
                checked={referencedField === 'market_percentile'}
                onChange={() => setReferencedField('market_percentile')}
              />
              Market percentile{!marketPercentileAvailable && ' — not available on this session'}
            </label>
          </div>
        </div>
      )}

      <div>
        <label className={labelClass}>Evidence / reasoning</label>
        <textarea
          className={`${inputClass} min-h-[90px]`}
          value={evidence}
          maxLength={DISPUTE_EVIDENCE_MAX_LENGTH}
          onChange={(e) => setEvidence(e.target.value)}
          placeholder="Explain what happened, with specifics (round numbers, dates, quoted terms)."
          required
        />
        <p className="mt-1 text-[11px] text-ink-muted text-right">{evidence.length} / {DISPUTE_EVIDENCE_MAX_LENGTH}</p>
      </div>

      {err && (
        isRateLimited ? (
          <p className="text-xs text-sealed-text bg-sealed-subtle border border-sealed-border rounded-lg px-3 py-2">
            {overSessionCap ? "You've reached the dispute limit for this session (3 per party)." : 'Rate limit reached — try again in a bit.'}
          </p>
        ) : (
          <p className="text-xs text-danger">{err.message}</p>
        )
      )}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting || !evidence.trim() || (disputeType === 'outcome' && !referencedField)}
          className="flex-1 px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-semibold disabled:opacity-50 transition-colors"
        >
          {submitting ? 'Filing…' : 'File dispute'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 rounded-lg bg-bg-elevated hover:bg-border text-ink-secondary text-sm transition-colors">
          Cancel
        </button>
      </div>
    </form>
  )
}

// Container: filing form + the live dispute list. Visually secondary by design — plain bordered
// card (no spotlight treatment), placed after AttestationPanel at the bottom of the page. Only
// ever visible when session.state === 'AGREED' specifically (not just any terminal state, and not
// packageActive/activeState) — disputes are scoped to the scalar outcome per
// app.offercheck.disputes, exactly matching disputesData's own {agreed_price, final_gap_pct,
// market_percentile} fields.
function DisputesPanel({ sessionId, token, myActor, view, visible, disputesData, onChanged }) {
  if (!visible) return null
  const list = disputesData?.disputes || []

  return (
    <div className="mt-4 p-5 rounded-xl bg-bg-surface border border-border">
      <p className="text-xs font-semibold text-ink-secondary uppercase tracking-wide mb-1">Disputes</p>
      <p className="text-xs text-ink-muted mb-2">
        A record of any concerns either side has raised about this outcome — visible to both parties.
      </p>

      {list.length > 0 && (
        <div className="space-y-2 mb-2">
          {list.map((d) => (
            <DisputeRow key={d.dispute_id} sessionId={sessionId} token={token} myActor={myActor} dispute={d} onChanged={onChanged} />
          ))}
        </div>
      )}

      <FileDisputeForm sessionId={sessionId} token={token} myActor={myActor} view={view} visible onFiled={onChanged} />
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
    <div className="mt-4 p-5 rounded-xl bg-bg-surface border border-border" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
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

function EnableAgenticButton({ sessionId, token, visible, onEnabled, enclaveVerified, enclaveLoading, enclaveError }) {
  const [open, setOpen] = useState(false)
  const [authorityLimit, setAuthorityLimit] = useState('')
  const [priorities, setPriorities] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')

  if (!visible) return null

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    setSubmitting(true)
    try {
      await offercheckEnableEmployerAgentic(sessionId, {
        token,
        employer_authority_limit: Number(authorityLimit),
        employer_priorities: priorities.trim() || undefined,
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
          An AI agent will negotiate on your behalf, using the private authority limit you set below — it will never agree to a number above that limit.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="mt-4 p-5 rounded-xl bg-bg-surface border border-border space-y-3">
      <p className="text-sm font-medium text-ink-primary">Enable AI negotiation</p>
      <p className="text-xs text-ink-muted">
        A Claude agent will negotiate on your behalf once the candidate is ready too. Your authority limit is sealed — never shown to the candidate.
      </p>
      <TeeInputBoundary label="Inside the TEE — sealed, never shown to the other side" pills={['Intel TDX', 'DCAP verified']}>
        <EnclaveStatusNote loading={enclaveLoading} error={enclaveError} />
        <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border">
          <label className="block text-xs font-medium text-sealed-text mb-1.5">🔒 Your signing authority limit — private, only you see this</label>
          <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={authorityLimit} onChange={(e) => setAuthorityLimit(e.target.value)} placeholder="195000" required disabled={!enclaveVerified} />
        </div>
      </TeeInputBoundary>
      <div>
        <label className={labelClass}>Priorities (optional)</label>
        <input className={inputClass} value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="equity is more flexible than base" />
      </div>
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !authorityLimit || !enclaveVerified} className="flex-1 px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-semibold disabled:opacity-50 transition-colors">
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

function EnablePackageAgenticButton({ sessionId, token, visible, onEnabled, enclaveVerified, enclaveLoading, enclaveError }) {
  const [open, setOpen] = useState(false)
  const [budget, setBudget] = useState('')
  const [priorities, setPriorities] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')

  if (!visible) return null

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    setSubmitting(true)
    try {
      await offercheckEnableEmployerPackageAgentic(sessionId, {
        token,
        employer_total_comp_budget: Number(budget),
        employer_priorities: priorities.trim() || undefined,
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
          An AI agent will negotiate the full compensation package on your behalf, using the private budget you set below — it will never agree above that budget.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="mt-3 p-5 rounded-xl bg-bg-surface border border-border space-y-3">
      <p className="text-sm font-medium text-ink-primary">Enable AI negotiation (full package)</p>
      <p className="text-xs text-ink-muted">
        A Claude agent will negotiate the full compensation package on your behalf. Your authority limit is sealed — never shown to the candidate.
      </p>
      <TeeInputBoundary label="Inside the TEE — sealed, never shown to the other side" pills={['Intel TDX', 'DCAP verified']}>
        <EnclaveStatusNote loading={enclaveLoading} error={enclaveError} />
        <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border">
          <label className="block text-xs font-medium text-sealed-text mb-1.5">🔒 Your authority limit — total comp, private</label>
          <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="300000" required disabled={!enclaveVerified} />
        </div>
      </TeeInputBoundary>
      <div>
        <label className={labelClass}>Priorities (optional)</label>
        <input className={inputClass} value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="equity is more flexible than base" />
      </div>
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={submitting || !budget || !enclaveVerified} className="flex-1 px-4 py-2 rounded-lg bg-teal hover:bg-teal-hover text-white text-sm font-semibold disabled:opacity-50 transition-colors">
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
    <div className="mt-4 p-5 rounded-xl bg-teal-subtle border border-teal-border">
      {!result && (
        <>
          <p className="text-sm font-medium text-ink-primary mb-1">Let AI agents negotiate</p>
          <p className="text-xs text-ink-secondary mb-3">
            Both sides have sealed their private numbers. Two Claude agents will negotiate from here —
            your band never crosses to the candidate's agent, only offer amounts and moves do.
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
            myActor="employer"
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
    <div className="mt-4 p-5 rounded-xl bg-teal-subtle border border-teal-border">
      {!result && (
        <>
          <p className="text-sm font-medium text-ink-primary mb-1">Let AI agents negotiate the full package</p>
          <p className="text-xs text-ink-secondary mb-3">
            Base, equity, signing bonus, annual bonus, remote policy, start date, and PTO — negotiated
            simultaneously. Budgets and floors never cross, only the package on the table each round.
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

// Employer counterpart to CandidateSession.jsx's ApprovalPanel — see that component's docstring.
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
        await offercheckEmployerApprovalPackage(sessionId, { token, decision })
      } else {
        await offercheckEmployerApproval(sessionId, { token, decision })
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
      <div className="mt-4 p-5 rounded-xl bg-bg-surface border border-border">
        <p className="text-sm text-ink-primary mb-1">
          You voted to <span className="font-semibold">{APPROVAL_LABEL[myVote]}</span>.
        </p>
        <p className="text-xs text-ink-muted italic">
          {otherVote ? `The candidate voted to ${APPROVAL_LABEL[otherVote]}.` : 'Waiting for the candidate to respond…'}
        </p>
      </div>
    )
  }

  return (
    <div className="mt-4 p-5 rounded-xl bg-bg-surface border border-border space-y-3">
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
          The candidate already voted to {APPROVAL_LABEL[otherVote]}.
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

// Read-only status for the employer's side of app.offercheck.provenance — the candidate is
// the only party who can trigger verification (see CandidateSession.jsx's VerifyCredentialPanel);
// this just surfaces the outcome once it exists. Shows nothing when there's nothing to show
// (not required, not yet verified) rather than a permanent empty placeholder.
function ProvenanceStatusPanel({ visible, view }) {
  if (!visible) return null
  if (!view.require_provenance_credential && !view.candidate_provenance_verified) return null

  if (view.candidate_provenance_verified) {
    const c = view.candidate_provenance_credential
    return (
      <div className="mt-4 p-5 rounded-xl bg-success-subtle border border-success/30">
        <p className="text-xs font-semibold text-success-text mb-1">✓ Candidate's git-provenance credential verified</p>
        {c && (
          <>
            <p className="text-xs text-ink-muted">
              {SENIORITY_LABEL[c.seniority_level] || c.seniority_level} · {c.years_active}y active · {c.total_commits} commits analyzed
              {c.primary_languages?.length > 0 ? ` · ${c.primary_languages.join(', ')}` : ''}
            </p>
            {c.qualitative_assessment && (
              <p className="text-xs text-ink-muted mt-1 italic">{c.qualitative_assessment}</p>
            )}
          </>
        )}
      </div>
    )
  }

  return (
    <div className="mt-4 px-4 py-2.5 rounded-lg bg-sealed-subtle border border-sealed-border text-sealed-text text-xs">
      Waiting for the candidate to verify their git-provenance credential — you required this before they can respond.
    </div>
  )
}

export default function EmployerSession() {
  const { sessionId } = useParams()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const isDemo = searchParams.get('demo') === '1'

  const [view, setView] = useState(null)
  const [error, setError] = useState('')
  const [band, setBand] = useState({ band_min: '', band_mid: '', band_max: '' })
  const [bandGap, setBandGap] = useState(null)
  const [counterValue, setCounterValue] = useState('')
  const [acting, setActing] = useState(false)
  const [disputesData, setDisputesData] = useState(null)
  const pollRef = useRef(null)

  // Verify, then release: the enclave's own attestation (not the session/negotiation
  // receipt — that one 409s until the session is terminal, see AttestationPanel below)
  // is fetched once up front and gates every sensitive input on this page.
  const [enclaveAttestation, setEnclaveAttestation] = useState(null)
  const [enclaveLoading, setEnclaveLoading] = useState(true)
  const [enclaveError, setEnclaveError] = useState('')

  useEffect(() => {
    let cancelled = false
    getEnclaveAttestation()
      .then((data) => { if (!cancelled) setEnclaveAttestation(data) })
      .catch((e) => { if (!cancelled) setEnclaveError(e.message || 'Enclave attestation could not be verified') })
      .finally(() => { if (!cancelled) setEnclaveLoading(false) })
    return () => { cancelled = true }
  }, [])

  const enclaveVerified = Boolean(enclaveAttestation) && !enclaveError

  const refresh = async () => {
    try {
      const data = await offercheckGetSession(sessionId, token)
      setView(data)
      setError('')
      // Piggybacked onto the same poll tick/interval, not a separate fetch loop — disputes are
      // only fileable/relevant once the scalar state is AGREED specifically (see
      // app.offercheck.disputes), and this way they never poll tighter than the main session poll.
      // Non-fatal: a transient disputes-fetch failure must not break the main session poll.
      if (data.state === 'AGREED') {
        try {
          const dv = await offercheckGetDisputes(sessionId, token)
          setDisputesData(dv)
        } catch {
          // ignore — next poll tick will retry
        }
      }
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
  const myTurn = view && (packageActive ? view.package_turn === 'employer' : view.turn === 'employer')
  const myVoteForTrace = view && (packageActive ? view.my_package_approval_vote : view.my_approval_vote)
  const otherVoteForTrace = view && (packageActive ? view.other_package_approval_vote : view.other_approval_vote)

  // EXPIRED is set in exactly one place in the backend state machine (negotiation.py::apply_move's
  // round-limit check) and never touched by the PENDING_APPROVAL reopen path (which produces
  // STALEMATE instead, a different terminal state, left untouched by this change) — so
  // activeState === 'EXPIRED' alone reliably identifies "ran out of rounds without ever reaching
  // an agreement," with no need to separately check agreed_price (which can hold a stale value
  // from an earlier accept that got reopened away from — checking it would be actively misleading
  // here, not just redundant). Scoped to activeState (not view.state alone) so this also covers a
  // package-mode negotiation that round-limited out, matching the same pill/label this augments.
  const isExpiredNoAgreement = Boolean(activeState === 'EXPIRED')

  // One spotlighted next action + stage spine — both keyed off the exact derivation above,
  // never a second simplified version of it (see getNextAction's own docstring).
  const nextAction = getNextAction(view, { isTerminal, pendingApproval, myTurn, packageActive })
  const stageStatuses = view ? getStageStatuses(view, nextAction, { unresolvedNoAgreement: isExpiredNoAgreement }) : []
  const bandIsSpotlighted = Boolean(nextAction && nextAction.key === 'submitBand')
  // Panels/banners that live inside the status card itself (approval, manual respond, the
  // fallback waiting line) don't get their own spotlight wrapper — the card as a whole gets the
  // highlighted-border treatment instead, matching CandidateSession.jsx's cardIsSpotlighted.
  const cardIsSpotlighted = Boolean(nextAction && ['respond', 'approval', 'waiting'].includes(nextAction.key))

  // Hoisted so each is the exact same expression already used as that component's own `visible`
  // prop below — never a parallel/divergent computation, just named once and reused for both
  // the real prop and the spotlight-vs-collapse decision.
  const provenanceVisible = Boolean(view && (view.require_provenance_credential || view.candidate_provenance_verified))
  const salaryChoiceVisible = Boolean(view?.band_set && !view?.my_agentic_sealed && !isTerminal)
  const salaryNudgeVisible = Boolean(view?.band_set && !view?.my_agentic_sealed && view?.other_agentic_sealed && !isTerminal)
  const salaryWaitingVisible = Boolean(view?.band_set && view?.my_agentic_sealed && !view?.agentic_ready && !isTerminal)
  const packageChoiceVisible = Boolean(view?.band_set && !view?.my_package_agentic_sealed && !isTerminal)
  const packageNudgeVisible = Boolean(view?.band_set && !view?.my_package_agentic_sealed && view?.other_package_agentic_sealed && !isTerminal)
  const packageWaitingVisible = Boolean(view?.band_set && view?.my_package_agentic_sealed && !view?.package_agentic_ready && !isTerminal)
  const runSalaryVisible = Boolean(view?.agentic_ready && !isTerminal)
  const runPackageVisible = Boolean(view?.package_agentic_ready && !isTerminal)

  const loadDemoBand = () => {
    setBand({ band_min: '155000', band_mid: '175000', band_max: '195000' })
  }

  // If the candidate loaded demo data before generating this link, the link carries &demo=1 —
  // prefill (never auto-submit) the matching demo band so a solo demo run doesn't need a second
  // "Load demo data" click on this side. The candidate's own numbers are never read or copied
  // here — this is still an independent, hardcoded demo value, same privacy boundary as always.
  useEffect(() => {
    if (isDemo) loadDemoBand()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo])

  const submitBand = async (e) => {
    e.preventDefault()
    setError('')
    setActing(true)
    try {
      const body = {
        employer_token: token,
        band_min: Number(band.band_min),
        band_mid: Number(band.band_mid),
        band_max: Number(band.band_max),
      }
      const result = await offercheckSetEmployerBand(sessionId, body)
      setBandGap(result.gap_pct)
      await refresh()
    } catch (err) {
      setError(err.message || 'Could not submit band')
    } finally {
      setActing(false)
    }
  }

  const act = async (move, value) => {
    setActing(true)
    setError('')
    try {
      const data = await offercheckEmployerMove(sessionId, { token, move, value: value ?? null })
      setView(data)
    } catch (err) {
      setError(err.message || 'Move failed')
    } finally {
      setActing(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-3xl mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-ink-primary mb-2">Competing offer verification</h1>
        <p className="text-sm text-ink-muted mb-8">
          Your band stays private. You'll only ever see the gap percentage.
        </p>

        <HowThisWorksStrip lines={HOW_THIS_WORKS_LINES} />

        {view && <StageSpine statuses={stageStatuses} />}

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
        )}

        {view && !view.band_set && (
          <form
            onSubmit={submitBand}
            className={`p-6 rounded-xl bg-bg-surface space-y-4 ${bandIsSpotlighted ? 'border-2 border-teal' : 'border border-border'}`}
            style={bandIsSpotlighted
              ? { boxShadow: '0 0 0 4px rgba(13,148,136,0.08)' }
              : { boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
          >
            <div className="flex justify-end -mt-1 -mb-2">
              <button
                type="button"
                onClick={loadDemoBand}
                className="px-2.5 py-1 rounded-md bg-bg-elevated hover:bg-border text-ink-secondary hover:text-ink-primary text-xs font-medium transition-all"
              >
                Load demo data
              </button>
            </div>
            <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border space-y-3">
              <p className="text-xs font-medium text-sealed-text">🔒 Your salary band — private, only you see this</p>
              <div>
                <label className="block text-xs font-medium text-sealed-text mb-1.5">Band minimum</label>
                <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={band.band_min} onChange={(e) => setBand((b) => ({ ...b, band_min: e.target.value }))} placeholder="155000" required />
              </div>
              <div>
                <label className="block text-xs font-medium text-sealed-text mb-1.5">Band midpoint</label>
                <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={band.band_mid} onChange={(e) => setBand((b) => ({ ...b, band_mid: e.target.value }))} placeholder="175000" required />
              </div>
              <div>
                <label className="block text-xs font-medium text-sealed-text mb-1.5">Band maximum</label>
                <input className={`${inputClass} text-sealed-text`} type="number" min="0" value={band.band_max} onChange={(e) => setBand((b) => ({ ...b, band_max: e.target.value }))} placeholder="195000" required />
              </div>
            </div>

            <p className="text-xs text-ink-muted pt-2 border-t border-border">
              You can enable AI negotiation from this page after submitting your band.
            </p>

            <button
              type="submit"
              disabled={acting}
              className="w-full px-6 py-3 rounded-xl bg-teal hover:bg-teal-hover text-white font-semibold text-sm transition-all disabled:opacity-50"
            >
              {acting ? 'Checking…' : 'See the gap'}
            </button>
          </form>
        )}

        {view && view.band_set && (
          <div
            className={`p-6 rounded-xl bg-bg-surface ${cardIsSpotlighted ? 'border-2 border-teal' : 'border border-border'}`}
            style={cardIsSpotlighted
              ? { boxShadow: '0 0 0 4px rgba(13,148,136,0.08)' }
              : { boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
          >
            {/* Scoped strictly to isExpiredNoAgreement — every other terminal state keeps the
                plain pill below as its only outcome indicator, exactly as before this change. */}
            {isExpiredNoAgreement && (
              <div className="mb-4 p-4 rounded-lg bg-sealed-subtle border border-sealed-border">
                <p className="text-sm font-semibold text-sealed-text mb-1.5">This negotiation didn't reach an agreement</p>
                {view.gap_pct != null && (
                  <p className="font-mono font-bold text-2xl text-sealed-text mb-1">{Math.abs(view.gap_pct).toFixed(1)}% apart</p>
                )}
                <p className="text-xs text-sealed-text/80 leading-relaxed mb-3">
                  The two sides were still this far apart when the {view.max_rounds}-round limit was reached, with no agreement in place.
                </p>
                <Link
                  to="/offercheck/company/new"
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-teal-subtle border-[1.5px] border-teal text-teal text-sm font-medium hover:bg-teal-subtle/70 transition-all"
                >
                  Start a new negotiation
                </Link>
              </div>
            )}

            <div className="flex items-center justify-between mb-4">
              <span className={`inline-block px-2.5 py-1 rounded-md text-sm font-semibold ${STATE_BADGE[activeState] || 'bg-bg-elevated text-neutral'}`}>
                {STATE_LABEL[activeState] || activeState}
              </span>
              <span className="text-xs font-mono text-ink-muted">round {activeRound} of {view.max_rounds}</span>
            </div>

            <GapMeter gapPct={bandGap ?? view.gap_pct} />

            {view.my_current_value != null && (
              <p className="text-xs text-ink-muted mb-4">
                Your current offer: <span className="font-mono font-semibold text-ink-primary">${view.my_current_value.toLocaleString()}</span>
              </p>
            )}

            {view.state === 'AGREED' && (
              <p className="text-sm text-success font-medium mb-4">
                Agreed at ${view.agreed_price?.toLocaleString()}
              </p>
            )}

            {view.state === 'AGREED' && (
              <AttestedMetrics finalGapPct={view.final_gap_pct} marketPercentile={view.market_percentile} />
            )}

            <RoundHistory history={view.history} myActor="employer" />

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

            {/* The human approval-gate decision, appended to the trace so it doesn't only live in
                ApprovalPanel's own status text — a viewer scrolling the trace alone should be able
                to see their own final call, not just a list of agent moves that can look unresolved.
                Only the viewer's own vote is shown here; the other party's vote is already surfaced
                by ApprovalPanel itself, so repeating it here would be redundant. */}
            {myVoteForTrace && (
              <div className="mb-4 flex justify-end">
                <div className="max-w-[80%] px-3 py-1.5 rounded-lg text-xs bg-sealed-subtle border border-sealed-border text-sealed-text">
                  <div className="flex items-center justify-between gap-3 mb-0.5">
                    <span className="font-medium">You</span>
                    <span className="text-[10px] text-ink-muted">your decision</span>
                  </div>
                  <div className="font-mono uppercase font-semibold">
                    {APPROVAL_LABEL[myVoteForTrace]}
                  </div>
                </div>
              </div>
            )}

            {/* Only reachable via a one-sided decline (see negotiation.py::_resolve_approval —
                a decline resolves the session immediately without waiting for the other vote), so
                the viewer here never got a turn to approve/decline. Without this, the trace would
                just stop after the last agent move with no acknowledgement the session is over. */}
            {!myVoteForTrace && otherVoteForTrace && isTerminal && (
              <div className="mb-4 flex justify-start">
                <div className="max-w-[80%] px-3 py-1.5 rounded-lg text-xs bg-bg-elevated border border-border text-ink-primary">
                  <div className="flex items-center justify-between gap-3 mb-0.5">
                    <span className="font-medium">Candidate</span>
                    <span className="text-[10px] text-ink-muted">ended it before your vote</span>
                  </div>
                  <div className="font-mono uppercase font-semibold">
                    {APPROVAL_LABEL[otherVoteForTrace]}
                  </div>
                </div>
              </div>
            )}

            {!isTerminal && !myTurn && !pendingApproval && (
              <p className="text-xs text-ink-muted italic">Waiting for the candidate to respond…</p>
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
                    placeholder="New offer"
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
                    Meet the gap
                  </button>
                  <button
                    disabled={acting}
                    onClick={() => act('walk')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-danger hover:bg-danger-hover text-white text-sm font-semibold disabled:opacity-40 transition-colors"
                  >
                    Decline
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {view && (() => {
          // Each node is built exactly once, with the exact same `visible` prop the panel has
          // always had — only how it's WRAPPED (spotlighted vs. collapsible-vs-always-shown)
          // changes, via ActionPanels below, never a change to any visible={...} condition.
          //
          // ProvenanceStatusPanel is 100% persistent status (both its internal branches — waiting
          // vs. verified — are read-only, neither is an actionable choice), so it's collapsible:
          // false outright, no split needed. salary/package are each split into a COLLAPSIBLE
          // actionable node (a not-yet-made choice) and a NON-collapsible persistent-status node
          // — see ActionPanels' own docstring for why conflating the two was a shipped regression.
          const provenanceNode = <ProvenanceStatusPanel visible={Boolean(view)} view={view} />

          const salaryChoiceNode = (
            <>
              {salaryNudgeVisible && (
                <div className="mb-2 px-4 py-2.5 rounded-lg bg-teal-subtle border border-teal-border text-teal-text text-xs">
                  The candidate has already enabled AI negotiation (salary) — enable yours to get started.
                </div>
              )}
              <EnableAgenticButton
                sessionId={sessionId}
                token={token}
                visible={salaryChoiceVisible}
                onEnabled={refresh}
                enclaveVerified={enclaveVerified}
                enclaveLoading={enclaveLoading}
                enclaveError={enclaveError}
              />
            </>
          )
          const salaryWaitingNode = salaryWaitingVisible ? (
            <div className="px-4 py-2.5 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs flex items-center gap-2">
              <span>✓ AI negotiation enabled (salary) — waiting for the candidate to enable their side too.</span>
            </div>
          ) : null

          const packageChoiceNode = (
            <>
              {packageNudgeVisible && (
                <div className="mb-2 px-4 py-2.5 rounded-lg bg-teal-subtle border border-teal-border text-teal-text text-xs">
                  The candidate has already enabled package AI negotiation — enable yours to get started.
                </div>
              )}
              <EnablePackageAgenticButton
                sessionId={sessionId}
                token={token}
                visible={packageChoiceVisible}
                onEnabled={refresh}
                enclaveVerified={enclaveVerified}
                enclaveLoading={enclaveLoading}
                enclaveError={enclaveError}
              />
            </>
          )
          const packageWaitingNode = packageWaitingVisible ? (
            <div className="px-4 py-2.5 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs flex items-center gap-2">
              <span>✓ Package AI negotiation enabled — waiting for the candidate to enable their side too.</span>
            </div>
          ) : null

          const runSalaryNode = (
            <AgenticPanel sessionId={sessionId} token={token} view={view} visible={runSalaryVisible} onComplete={refresh} />
          )
          const runPackageNode = (
            <PackageAgenticPanel sessionId={sessionId} token={token} view={view} visible={runPackageVisible} onComplete={refresh} />
          )

          const isChoose = nextAction?.key === 'choose'
          const items = [
            {
              // Persistent status — never collapsible. Neither of ProvenanceStatusPanel's own
              // internal branches (waiting / verified) is an actionable choice for the employer.
              key: 'verify', node: provenanceNode, collapsible: false,
              visible: provenanceVisible,
              isSpotlight: nextAction?.key === 'waitingForVerify',
              title: 'Waiting for the candidate',
            },
            {
              key: 'salaryChoice', node: salaryChoiceNode, collapsible: true,
              visible: salaryChoiceVisible,
              isSpotlight: isChoose,
              title: 'Do this next — choose how to negotiate',
            },
            {
              key: 'salaryWaiting', node: salaryWaitingNode, collapsible: false,
              visible: salaryWaitingVisible,
              isSpotlight: nextAction?.key === 'sealedWaitingSalary',
              title: 'Waiting for the candidate',
            },
            {
              // No title here when spotlighted alongside salaryChoice (isChoose is their only
              // shared trigger) — repeating "Do this next — choose how to negotiate" on both
              // adjacent cards would just be duplicate text; the clarifying paragraph above
              // already explains the pair.
              key: 'packageChoice', node: packageChoiceNode, collapsible: true,
              visible: packageChoiceVisible,
              isSpotlight: isChoose,
            },
            {
              key: 'packageWaiting', node: packageWaitingNode, collapsible: false,
              visible: packageWaitingVisible,
              isSpotlight: nextAction?.key === 'sealedWaitingPackage',
              title: 'Waiting for the candidate',
            },
            {
              // Non-collapsible: once an agentic run completes, its result (agreed price / round
              // history) must persist even after pendingApproval immediately supersedes 'runSalary'
              // as the recommended action — the same regression class as ProvenanceStatusPanel,
              // since AgenticPanel keeps rendering its own cached result once visible flips.
              key: 'runSalary', node: runSalaryNode, collapsible: false,
              visible: runSalaryVisible,
              isSpotlight: nextAction?.key === 'runSalary',
              title: 'Do this next',
            },
            {
              key: 'runPackage', node: runPackageNode, collapsible: false,
              visible: runPackageVisible,
              isSpotlight: nextAction?.key === 'runPackage',
              title: 'Do this next',
            },
          ]

          return (
            <>
              {/* Only shown when both choice buttons are the spotlight together — confirmed against
                  EnablePackageAgenticButton's own visible={!isTerminal} that a track can still be
                  added after starting the other, right up until this track's own outcome is final. */}
              {isChoose && (
                <p className="mb-3 text-xs text-ink-secondary">
                  Choose one to start: salary only, or the full package (salary + equity + benefits).
                  You can add the other track later, but only before this one finishes.
                </p>
              )}

              <ActionPanels items={items} />
            </>
          )
        })()}

        <div
          className={nextAction?.key === 'proof' ? 'rounded-xl border-2 border-teal p-5' : ''}
          style={nextAction?.key === 'proof' ? { boxShadow: '0 0 0 4px rgba(13,148,136,0.08)' } : undefined}
        >
          {nextAction?.key === 'proof' && (
            <p className="text-sm font-semibold text-teal-text uppercase tracking-wide mb-3">See what happened</p>
          )}
          <AttestationPanel sessionId={sessionId} token={token} visible={Boolean(isTerminal)} />
          <DisputesPanel
            sessionId={sessionId}
            token={token}
            myActor="employer"
            view={view}
            visible={Boolean(view && view.state === 'AGREED')}
            disputesData={disputesData}
            onChanged={refresh}
          />
        </div>
      </div>
    </div>
  )
}
