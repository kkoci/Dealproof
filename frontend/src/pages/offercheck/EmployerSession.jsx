import React, { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getEnclaveAttestation, offercheckClaimSession, offercheckEmployerApproval, offercheckEmployerApprovalPackage, offercheckEmployerMove, offercheckEnableEmployerAgentic, offercheckEnableEmployerPackageAgentic, offercheckFileEmployerDispute, offercheckGetAttestation, offercheckGetCredential, offercheckGetDisputes, offercheckGetSession, offercheckSetEmployerBand, offercheckStartAgentic, offercheckStartAgenticPackage, offercheckUpdateEmployerDisputeStatus } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'
import Badge from '../../components/offercheck/Badge.jsx'
import BalanceMeter from '../../components/offercheck/BalanceMeter.jsx'
import { SealMark } from '../../components/offercheck/Seal.jsx'
import { FieldLabel, Input, Textarea } from '../../components/offercheck/Input.jsx'
import { LockIcon, CheckIcon, CloseIcon } from '../../components/offercheck/icons.jsx'

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
const DISPUTE_STATUS_TONE = {
  OPEN: 'sealed',
  UNDER_REVIEW: 'teal',
  RESOLVED: 'success',
  DISMISSED: 'neutral',
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

const STATE_TONE = {
  PENDING_EMPLOYER: 'success',
  EMPLOYER_RESPONDED: 'neutral',
  CANDIDATE_COUNTERED: 'success',
  PENDING_APPROVAL: 'sealed',
  AGREED: 'success',
  WALKAWAY: 'danger',
  EXPIRED: 'neutral',
  DECLINED: 'danger',
  STALEMATE: 'neutral',
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
              {s.status === 'done' && <CheckIcon size={9} className="text-white" />}
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
        if (!it.visible || hiddenBehindToggle) {
          return <div key={it.key} className="hidden">{it.node}</div>
        }
        return (
          <div key={it.key} className={it.isSpotlight ? 'mb-6' : 'mb-3'}>
            {it.isSpotlight ? (
              <Card emphasis="spotlight" padding="lg">
                {it.title && <p className="text-sm font-semibold text-teal-text uppercase tracking-wide mb-3">{it.title}</p>}
                {it.node}
              </Card>
            ) : it.node}
          </div>
        )
      })}
      {otherCount > 0 && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="focus-ring rounded mb-6 text-xs font-medium text-ink-muted hover:text-ink-secondary underline underline-offset-2 transition-colors"
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
    <Card padding="lg" className="mb-6 !bg-teal-subtle !border-teal-border relative">
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss"
        className="focus-ring absolute top-2.5 right-2.5 w-5 h-5 flex items-center justify-center rounded-md text-teal-text/60 hover:text-teal-text hover:bg-bg-elevated transition-colors"
      >
        <CloseIcon size={13} />
      </button>
      <p className="text-sm font-semibold text-teal-text uppercase tracking-wide mb-2 pr-6">How this works</p>
      <ol className="space-y-1.5">
        {lines.map((line, i) => (
          <li key={i} className="flex items-start gap-2 text-xs text-ink-secondary leading-relaxed">
            <span className="flex-shrink-0 w-4 h-4 rounded-full bg-bg-surface border border-teal-border text-teal-text text-[10px] font-bold flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <span>{line}</span>
          </li>
        ))}
      </ol>
    </Card>
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
// TrustPill.
function TrustPill({ children }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg-surface border border-success/30 text-success-text text-[10px] font-medium">
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
        <span className="flex items-center gap-1.5 text-xs font-semibold text-success-text">
          <LockIcon size={13} />
          {label}
        </span>
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
              <div className="font-mono tnum uppercase font-semibold">
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
                R{r.round} <span className="text-[9px] uppercase text-ink-muted">{r.actor === 'employer' ? 'Emp' : 'Cand'}</span>
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
                    <td key={i} className={`text-right py-1 px-1 font-mono tnum ${changed ? 'text-teal font-semibold' : 'text-ink-primary'}`}>
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
              <td key={r.round} className="text-right py-1 px-1 font-mono tnum text-ink-primary font-semibold">
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
        <p className="text-data-label uppercase text-ink-muted mb-0.5">Movement from opening offer</p>
        {finalGapPct != null ? (
          <p className="text-sm font-mono tnum font-semibold text-ink-primary">
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
        <p className="text-data-label uppercase text-ink-muted mb-0.5">Market comparator</p>
        {marketPercentile != null ? (
          <p className="text-sm font-mono tnum font-semibold text-ink-primary">{ordinal(marketPercentile)} percentile</p>
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
        <Badge tone={DISPUTE_STATUS_TONE[dispute.status] || 'neutral'}>
          {DISPUTE_STATUS_LABEL[dispute.status] || dispute.status}
        </Badge>
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
          <Input
            className="!text-xs !py-1.5"
            placeholder="Optional note…"
            value={note}
            maxLength={DISPUTE_EVIDENCE_MAX_LENGTH}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex gap-2">
            {nextOptions.map((status) => (
              <Button
                key={status}
                size="sm"
                fullWidth
                loading={submitting}
                variant={status === 'RESOLVED' ? 'success' : status === 'DISMISSED' ? 'secondary' : 'subtle'}
                onClick={() => transition(status)}
              >
                {TRANSITION_BUTTON_LABEL[status]}
              </Button>
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
        <Button variant="secondary" fullWidth onClick={() => setOpen(true)}>
          File a dispute
        </Button>
        <p className="mt-1.5 text-xs text-ink-muted">
          Disagree with how this went, or with the result itself? File a dispute — it's recorded alongside the attestation, it never reopens the negotiation on its own.
        </p>
      </div>
    )
  }

  const isRateLimited = err?.status === 429
  const overSessionCap = isRateLimited && /per party per session/i.test(err.message || '')

  return (
    <form onSubmit={submit} className="mt-4">
      <Card padding="lg" className="space-y-3">
        <p className="text-sm font-medium text-ink-primary">File a dispute</p>
        <p className="text-xs text-ink-muted">
          This is a flag for a human to review — filing never changes the outcome or reopens negotiation on its own.
        </p>

        <div>
          <FieldLabel>Dispute type</FieldLabel>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              fullWidth
              variant={disputeType === 'process' ? 'primary' : 'secondary'}
              onClick={() => { setDisputeType('process'); setReferencedField('') }}
            >
              Process
            </Button>
            <Button
              type="button"
              size="sm"
              fullWidth
              variant={disputeType === 'outcome' ? 'primary' : 'secondary'}
              onClick={() => setDisputeType('outcome')}
            >
              Outcome
            </Button>
          </div>
          <p className="mt-1.5 text-[11px] text-ink-muted">
            {disputeType === 'process'
              ? "The record doesn't match what happened, or a stated rule wasn't followed."
              : 'The negotiated result itself seems unfair — grounded in an attested figure below, not just a feeling.'}
          </p>
        </div>

        {disputeType === 'outcome' && (
          <div>
            <FieldLabel>Which attested figure?</FieldLabel>
            <div className="space-y-1.5">
              <label className={`flex items-center gap-2 text-xs ${finalGapAvailable ? 'text-ink-primary cursor-pointer' : 'text-ink-muted/50 cursor-not-allowed'}`}>
                <input
                  type="radio"
                  name="referenced_field"
                  className="accent-teal"
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
                  className="accent-teal"
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
          <FieldLabel>Evidence / reasoning</FieldLabel>
          <Textarea
            className="min-h-[90px]"
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
          <Button
            type="submit"
            fullWidth
            loading={submitting}
            disabled={!evidence.trim() || (disputeType === 'outcome' && !referencedField)}
          >
            {submitting ? 'Filing…' : 'File dispute'}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </Card>
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
    <Card padding="lg" className="mt-4">
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
    </Card>
  )
}

// Surfaces once a terminal session's proof is withheld because no company was
// ever attached to it — the common case for a candidate-initiated session,
// which (unlike the employer-invite flow) has no point in its flow where a
// company gets attached automatically. Mirrors POST /sessions/{id}/claim's own
// docstring: "a session that couldn't be billed the first time... can be
// unlocked later... without redoing the negotiation." Reads
// `payment_required` off the already-fetched SessionView — no new backend
// field needed, that boolean already exists specifically for this.
function ClaimCompanyPanel({ sessionId, visible, onClaimed }) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('offercheck_api_key') || '')
  const [submitting, setSubmitting] = useState(false)
  const [err, setErr] = useState('')
  const [result, setResult] = useState(null)

  if (!visible) return null

  const submit = async (e) => {
    e.preventDefault()
    setErr('')
    setSubmitting(true)
    try {
      const data = await offercheckClaimSession(sessionId, apiKey.trim())
      setResult(data)
      if (!data.payment_required) onClaimed?.()
    } catch (e) {
      setErr(
        /already claimed/i.test(e.message || '')
          ? 'This session is already billed to a different company account.'
          : (e.message || 'Could not attach that company account'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card emphasis="default" padding="lg" className="mb-4">
      <p className="text-sm font-semibold text-ink-primary mb-1">Bill this to your company account</p>
      <p className="text-xs text-ink-muted leading-relaxed mb-3">
        This negotiation happened without a company account attached, so the attested proof below is on
        hold. Enter your Offer Check API key to bill this verification to your account and unlock it —
        the negotiation outcome itself doesn't change either way.
      </p>
      {result && result.payment_required && (
        <p className="mb-3 text-xs text-sealed-text">
          Account attached, but it has no verification credit left — see Plans for how to add more.
        </p>
      )}
      <form onSubmit={submit} className="space-y-3">
        <div>
          <FieldLabel>Company API key</FieldLabel>
          <Input
            mono
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="oc_live_… or oc_test_…"
            required
          />
        </div>
        {err && (
          <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-xs">{err}</div>
        )}
        <Button type="submit" variant="secondary" size="sm" loading={submitting}>
          {submitting ? 'Attaching…' : 'Attach and unlock proof'}
        </Button>
      </form>
    </Card>
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
    <Card emphasis="seal" padding="lg" className="mt-4">
      {receipt ? (
        <>
          {receipt.tee_attested ? (
            <div className="flex items-center gap-3 mb-3">
              <SealMark size="md" ignite />
              <div>
                <p className="text-data-label uppercase text-teal-text/70">Cryptographic proof</p>
                <span className="text-sm font-display font-semibold text-teal-text">Verified by Intel TDX</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-2 px-2.5 py-1 rounded-md bg-sealed-subtle border border-sealed-border w-fit">
              <span className="text-xs font-semibold text-sealed-text">Simulation mode — no real TEE hardware</span>
            </div>
          )}
          <p className="text-xs text-ink-muted leading-relaxed mb-3">
            {receipt.tee_attested
              ? 'Verified by secure, tamper-proof computation — neither side could see or alter the other’s private numbers, and the result can’t be faked.'
              : 'This demo run skipped the real secure hardware — for testing only, not a verified result.'}
          </p>
          <div className="rounded-lg bg-bg-elevated border border-border px-3 py-2.5 mb-3">
            <p className="text-data-label uppercase text-ink-muted mb-1">Quote</p>
            <p className="text-[11px] font-mono tnum text-teal-text/90 break-all leading-relaxed">{receipt.attestation}</p>
          </div>
          {cred && (
            <div className="pt-3 border-t border-teal-border">
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
    </Card>
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
        <Button variant="subtle" fullWidth onClick={() => setOpen(true)}>
          Enable AI negotiation
        </Button>
        <p className="mt-1.5 text-xs text-ink-muted">
          An AI agent will negotiate on your behalf, using the private authority limit you set below — it will never agree to a number above that limit.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="mt-4">
      <Card padding="lg" className="space-y-3">
        <p className="text-sm font-medium text-ink-primary">Enable AI negotiation</p>
        <p className="text-xs text-ink-muted">
          A Claude agent will negotiate on your behalf once the candidate is ready too. Your authority limit is sealed — never shown to the candidate.
        </p>
        <TeeInputBoundary label="Inside the TEE — sealed, never shown to the other side" pills={['Intel TDX', 'DCAP verified']}>
          <EnclaveStatusNote loading={enclaveLoading} error={enclaveError} />
          <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border">
            <label className="flex items-center gap-1.5 text-xs font-medium text-sealed-text mb-1.5">
              <LockIcon size={12} />
              Your signing authority limit — private, only you see this
            </label>
            <Input mono className="!text-sealed-text" type="number" min="0" value={authorityLimit} onChange={(e) => setAuthorityLimit(e.target.value)} placeholder="195000" required disabled={!enclaveVerified} />
          </div>
        </TeeInputBoundary>
        <div>
          <FieldLabel>Priorities (optional)</FieldLabel>
          <Input value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="equity is more flexible than base" />
        </div>
        {err && <p className="text-xs text-danger">{err}</p>}
        <div className="flex gap-2">
          <Button type="submit" fullWidth loading={submitting} disabled={!authorityLimit || !enclaveVerified}>
            {submitting ? 'Sealing…' : 'Seal & enable'}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
        <p className="text-[11px] text-ink-muted">
          Sealing locks in your number privately — the other side never sees it, only the eventual outcome.
        </p>
      </Card>
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
        <Button variant="subtle" fullWidth onClick={() => setOpen(true)}>
          Enable AI negotiation (full package)
        </Button>
        <p className="mt-1.5 text-xs text-ink-muted">
          An AI agent will negotiate the full compensation package on your behalf, using the private budget you set below — it will never agree above that budget.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="mt-3">
      <Card padding="lg" className="space-y-3">
        <p className="text-sm font-medium text-ink-primary">Enable AI negotiation (full package)</p>
        <p className="text-xs text-ink-muted">
          A Claude agent will negotiate the full compensation package on your behalf. Your authority limit is sealed — never shown to the candidate.
        </p>
        <TeeInputBoundary label="Inside the TEE — sealed, never shown to the other side" pills={['Intel TDX', 'DCAP verified']}>
          <EnclaveStatusNote loading={enclaveLoading} error={enclaveError} />
          <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border">
            <label className="flex items-center gap-1.5 text-xs font-medium text-sealed-text mb-1.5">
              <LockIcon size={12} />
              Your authority limit — total comp, private
            </label>
            <Input mono className="!text-sealed-text" type="number" min="0" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="300000" required disabled={!enclaveVerified} />
          </div>
        </TeeInputBoundary>
        <div>
          <FieldLabel>Priorities (optional)</FieldLabel>
          <Input value={priorities} onChange={(e) => setPriorities(e.target.value)} placeholder="equity is more flexible than base" />
        </div>
        {err && <p className="text-xs text-danger">{err}</p>}
        <div className="flex gap-2">
          <Button type="submit" fullWidth loading={submitting} disabled={!budget || !enclaveVerified}>
            {submitting ? 'Sealing…' : 'Seal & enable'}
          </Button>
          <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
        <p className="text-[11px] text-ink-muted">
          Sealing locks in your number privately — the other side never sees it, only the eventual outcome.
        </p>
      </Card>
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
    <Card padding="lg" className="mt-4 !bg-teal-subtle !border-teal-border">
      {!result && (
        <>
          <p className="text-sm font-medium text-ink-primary mb-1">Let AI agents negotiate</p>
          <p className="text-xs text-ink-secondary mb-3">
            Both sides have sealed their private numbers. Two Claude agents will negotiate from here —
            your band never crosses to the candidate's agent, only offer amounts and moves do.
          </p>
          <Button variant="success" fullWidth loading={running} onClick={run}>
            {running ? `Agents negotiating… Round ${view?.round_number ?? 0} of ${view?.max_rounds ?? 5}` : 'Let agents negotiate'}
          </Button>
          {err && <p className="text-xs text-danger mt-2">{err}</p>}
        </>
      )}
      {result && (
        <>
          <Badge tone="teal" className="mb-2">Negotiated by AI agents</Badge>
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
    </Card>
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
    <Card padding="lg" className="mt-4 !bg-teal-subtle !border-teal-border">
      {!result && (
        <>
          <p className="text-sm font-medium text-ink-primary mb-1">Let AI agents negotiate the full package</p>
          <p className="text-xs text-ink-secondary mb-3">
            Base, equity, signing bonus, annual bonus, remote policy, start date, and PTO — negotiated
            simultaneously. Budgets and floors never cross, only the package on the table each round.
          </p>
          <Button variant="success" fullWidth loading={running} onClick={run}>
            {running ? `Agents negotiating… Round ${view?.package_round_number ?? 0} of ${view?.max_rounds ?? 5}` : 'Let agents negotiate (full package)'}
          </Button>
          {err && <p className="text-xs text-danger mt-2">{err}</p>}
        </>
      )}
      {result && (
        <>
          <Badge tone="teal" className="mb-2">Negotiated by AI agents</Badge>
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
    </Card>
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
      <Card padding="lg" className="mt-4">
        <p className="text-sm text-ink-primary mb-1">
          You voted to <span className="font-semibold">{APPROVAL_LABEL[myVote]}</span>.
        </p>
        <p className="text-xs text-ink-muted italic">
          {otherVote ? `The candidate voted to ${APPROVAL_LABEL[otherVote]}.` : 'Waiting for the candidate to respond…'}
        </p>
      </Card>
    )
  }

  return (
    <Card padding="lg" className="mt-4 space-y-3">
      <p className="text-sm font-medium text-ink-primary">
        {packageMode ? 'Agents reached a package agreement — your call' : 'Agents reached an outcome — your call'}
      </p>
      {!packageMode && view.agreed_price != null && (
        <p className="text-xs text-ink-muted">
          Agreed price: <span className="font-mono tnum font-semibold text-ink-primary">${view.agreed_price.toLocaleString()}</span>
        </p>
      )}
      {otherVote && (
        <p className="text-xs text-teal-text bg-teal-subtle border border-teal-border rounded-lg px-3 py-2">
          The candidate already voted to {APPROVAL_LABEL[otherVote]}.
        </p>
      )}
      {err && <p className="text-xs text-danger">{err}</p>}
      <div className="flex gap-2">
        <Button variant="success" size="sm" fullWidth loading={submitting} onClick={() => vote('approve')}>
          Approve
        </Button>
        <Button variant="secondary" size="sm" fullWidth loading={submitting} onClick={() => vote('request_more_rounds')}>
          More rounds
        </Button>
        <Button variant="destructive" size="sm" fullWidth loading={submitting} onClick={() => vote('decline')}>
          Decline
        </Button>
      </div>
    </Card>
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
      <Card padding="lg" className="mt-4 !bg-success-subtle !border-success/30">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-success-text mb-1">
          <CheckIcon size={12} />
          Candidate's git-provenance credential verified
        </p>
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
      </Card>
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
    <PageShell>
      <h1 className="font-display text-hero-sm text-ink-primary mb-2">Competing offer verification</h1>
      <p className="text-sm text-ink-muted mb-8">
        Your band stays private. You'll only ever see the gap percentage.
      </p>

      <HowThisWorksStrip lines={HOW_THIS_WORKS_LINES} />

      {view && <StageSpine statuses={stageStatuses} />}

      {error && (
        <div className="mb-4 px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
      )}

      {view && !view.band_set && (
        <form onSubmit={submitBand}>
          <Card emphasis={bandIsSpotlighted ? 'spotlight' : 'default'} padding="lg" className="space-y-4">
            <div className="flex justify-end -mt-1 -mb-2">
              <Button type="button" variant="secondary" size="sm" onClick={loadDemoBand}>
                Load demo data
              </Button>
            </div>
            <div className="p-3 rounded-lg bg-sealed-subtle border border-dashed border-sealed-border space-y-3">
              <p className="flex items-center gap-1.5 text-xs font-medium text-sealed-text">
                <LockIcon size={12} />
                Your salary band — private, only you see this
              </p>
              <div>
                <FieldLabel className="!text-sealed-text">Band minimum</FieldLabel>
                <Input mono className="!text-sealed-text" type="number" min="0" value={band.band_min} onChange={(e) => setBand((b) => ({ ...b, band_min: e.target.value }))} placeholder="155000" required />
              </div>
              <div>
                <FieldLabel className="!text-sealed-text">Band midpoint</FieldLabel>
                <Input mono className="!text-sealed-text" type="number" min="0" value={band.band_mid} onChange={(e) => setBand((b) => ({ ...b, band_mid: e.target.value }))} placeholder="175000" required />
              </div>
              <div>
                <FieldLabel className="!text-sealed-text">Band maximum</FieldLabel>
                <Input mono className="!text-sealed-text" type="number" min="0" value={band.band_max} onChange={(e) => setBand((b) => ({ ...b, band_max: e.target.value }))} placeholder="195000" required />
              </div>
            </div>

            <p className="text-xs text-ink-muted pt-2 border-t border-border">
              You can enable AI negotiation from this page after submitting your band.
            </p>

            <Button type="submit" size="lg" fullWidth loading={acting}>
              {acting ? 'Checking…' : 'See the gap'}
            </Button>
          </Card>
        </form>
      )}

      {view && view.band_set && (
        <Card emphasis={cardIsSpotlighted ? 'spotlight' : 'default'} padding="lg">
          {/* Scoped strictly to isExpiredNoAgreement — every other terminal state keeps the
              plain pill below as its only outcome indicator, exactly as before this change. */}
          {isExpiredNoAgreement && (
            <div className="mb-4 p-4 rounded-lg bg-sealed-subtle border border-sealed-border">
              <p className="text-sm font-semibold text-sealed-text mb-1.5">This negotiation didn't reach an agreement</p>
              {view.gap_pct != null && (
                <p className="font-mono tnum font-bold text-2xl text-sealed-text mb-1">{Math.abs(view.gap_pct).toFixed(1)}% apart</p>
              )}
              <p className="text-xs text-sealed-text/80 leading-relaxed mb-3">
                The two sides were still this far apart when the {view.max_rounds}-round limit was reached, with no agreement in place.
              </p>
              <Button as={Link} to="/offercheck/company/new" variant="subtle" size="sm">
                Start a new negotiation
              </Button>
            </div>
          )}

          <div className="flex items-center justify-between mb-4">
            <Badge tone={STATE_TONE[activeState] || 'neutral'}>{STATE_LABEL[activeState] || activeState}</Badge>
            <span className="text-xs font-mono tnum text-ink-muted">round {activeRound} of {view.max_rounds}</span>
          </div>

          <BalanceMeter gapPct={bandGap ?? view.gap_pct} />

          {view.my_current_value != null && (
            <p className="text-xs text-ink-muted mb-4">
              Your current offer: <span className="font-mono tnum font-semibold text-ink-primary">${view.my_current_value.toLocaleString()}</span>
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
                <Input
                  type="number"
                  min="0"
                  value={counterValue}
                  onChange={(e) => setCounterValue(e.target.value)}
                  placeholder="New offer"
                  className="flex-1 min-w-0"
                />
                <Button variant="secondary" loading={acting} disabled={!counterValue} onClick={() => act('counter', Number(counterValue))}>
                  Counter
                </Button>
              </div>
              <div className="flex gap-2">
                <Button variant="success" fullWidth loading={acting} onClick={() => act('accept')}>
                  Meet the gap
                </Button>
                <Button variant="destructive" fullWidth loading={acting} onClick={() => act('walk')}>
                  Decline
                </Button>
              </div>
            </div>
          )}
        </Card>
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
          <div className="px-4 py-2.5 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs flex items-center gap-1.5">
            <CheckIcon size={12} className="shrink-0" />
            <span>AI negotiation enabled (salary) — waiting for the candidate to enable their side too.</span>
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
          <div className="px-4 py-2.5 rounded-lg bg-success-subtle border border-success/30 text-success-text text-xs flex items-center gap-1.5">
            <CheckIcon size={12} className="shrink-0" />
            <span>Package AI negotiation enabled — waiting for the candidate to enable their side too.</span>
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

      <div>
        {nextAction?.key === 'proof' ? (
          <Card emphasis="spotlight" padding="lg">
            <p className="text-sm font-semibold text-teal-text uppercase tracking-wide mb-3">See what happened</p>
            <ClaimCompanyPanel sessionId={sessionId} visible={Boolean(isTerminal && view?.payment_required)} onClaimed={refresh} />
            <AttestationPanel sessionId={sessionId} token={token} visible={Boolean(isTerminal && !view?.payment_required)} />
            <DisputesPanel
              sessionId={sessionId}
              token={token}
              myActor="employer"
              view={view}
              visible={Boolean(view && view.state === 'AGREED')}
              disputesData={disputesData}
              onChanged={refresh}
            />
          </Card>
        ) : (
          <>
            <ClaimCompanyPanel sessionId={sessionId} visible={Boolean(isTerminal && view?.payment_required)} onClaimed={refresh} />
            <AttestationPanel sessionId={sessionId} token={token} visible={Boolean(isTerminal && !view?.payment_required)} />
            <DisputesPanel
              sessionId={sessionId}
              token={token}
              myActor="employer"
              view={view}
              visible={Boolean(view && view.state === 'AGREED')}
              disputesData={disputesData}
              onChanged={refresh}
            />
          </>
        )}
      </div>
    </PageShell>
  )
}
