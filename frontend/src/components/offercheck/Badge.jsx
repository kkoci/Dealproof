// Generic status-pill primitive. Each page's own STATE_BADGE / DISPUTE_STATUS_BADGE lookup still
// decides which `tone` a given backend status maps to — that mapping is business logic and stays
// where it is. This only standardizes how a tone renders, so every badge in the vertical (session
// state, dispute status, gap-magnitude, agentic-ready) shares one visual vocabulary.
import React from 'react'

const TONE = {
  teal: 'bg-teal-subtle text-teal-text border-teal-border',
  sealed: 'bg-sealed-subtle text-sealed-text border-sealed-border',
  success: 'bg-success-subtle text-success-text border-success/20',
  danger: 'bg-danger-subtle text-danger-text border-danger/20',
  neutral: 'bg-neutral-subtle text-ink-secondary border-border',
}

export default function Badge({ tone = 'neutral', dot = false, className = '', children }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${TONE[tone]} ${className}`}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />}
      {children}
    </span>
  )
}
