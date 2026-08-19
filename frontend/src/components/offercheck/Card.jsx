// Shared surface primitive — replaces the `rounded-xl bg-bg-surface border border-border` +
// inline `style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}` pattern that was hand-copied onto
// nearly every panel across all nine pages (a real cross-page consistency risk on its own).
//
// `emphasis` is this system's whole answer to "what makes something look important vs secondary"
// (the task's explicit ask): `hero` gets the one radius step up (16px vs 12px), the deeper
// `shadow-elevated` stack, and a teal-tinted border-2 — reserved for exactly one card per page, the
// thing currently demanding the user's attention (mirrors the existing spotlight convention in
// CandidateSession/EmployerSession, now centralized). `flat` drops the shadow/border entirely for a
// card nested inside another card. `seal` is the one ceremonial exception — see Attestation.jsx.
import React from 'react'

const EMPHASIS = {
  default: 'rounded-xl border border-border shadow-card',
  hero: 'rounded-2xl border-2 border-teal shadow-elevated',
  spotlight: 'rounded-xl border-2 border-teal shadow-elevated',
  flat: 'rounded-lg border border-border',
  seal: 'rounded-2xl border border-teal-border shadow-seal',
}

const PADDING = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
}

export default function Card({ emphasis = 'default', padding = 'md', className = '', children, ...rest }) {
  return (
    <div className={`bg-bg-surface ${EMPHASIS[emphasis]} ${PADDING[padding]} ${className}`} {...rest}>
      {children}
    </div>
  )
}
