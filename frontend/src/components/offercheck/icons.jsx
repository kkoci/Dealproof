// Offer Check's own stroke-icon set — see docs/design/luxe/SKILL.md's Icon System. Every icon here
// is `fill="none"`, `stroke="currentColor"`, `stroke-width: 1.5`, round caps/joins — one visual voice,
// zero external icon package. Replaces the emoji (🔒, 🛡️, ✓) previously scattered through this
// vertical's copy, which read as informal/gamified — the opposite of the calm, provably-honest tone
// this product needs (see the v4 design plan's "no emoji" decision).
//
// Sizes follow the skill's convention: 16px inline, 20px controls, 24px navigation — pass `size`,
// default 20.
import React from 'react'

const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round' }

export function LockIcon({ size = 16, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={className} {...base}>
      <rect x="4.5" y="9" width="11" height="8" rx="1.5" />
      <path d="M6.5 9V6.5a3.5 3.5 0 0 1 7 0V9" />
    </svg>
  )
}

// The "verification seal" — the product's one recurring proof mark. Concentric offset rings plus a
// centered tick, evoking a hardware-attestation chip or an embossed stamp impression, deliberately
// NOT the generic circle-checkmark "verified" badge every SaaS product already uses. Used at exactly
// three moments: the TDX attestation badge, a filed-dispute confirmation, and StageSpine's 'done'
// mark — see the v4 design plan for why concentrating it, rather than decorating with it, is the point.
export function SealIcon({ size = 20, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5.5" strokeDasharray="1.5 2.6" strokeOpacity="0.6" />
      <path d="M9 12.2l2 2 4-4.4" />
    </svg>
  )
}

export function ChevronDownIcon({ size = 16, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={className} {...base}>
      <path d="M5 7.5l5 5 5-5" />
    </svg>
  )
}

export function CopyIcon({ size = 14, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={className} {...base}>
      <rect x="7.5" y="7.5" width="9" height="9" rx="1.5" />
      <path d="M4.5 12.5v-7a1.5 1.5 0 0 1 1.5-1.5h7" />
    </svg>
  )
}

export function CheckIcon({ size = 14, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={className} {...base}>
      <path d="M4 10.5l4 4 8-9" />
    </svg>
  )
}

export function CloseIcon({ size = 14, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={className} {...base}>
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  )
}

export function ArrowRightIcon({ size = 14, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={className} {...base}>
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  )
}

export function SpinnerIcon({ size = 14, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" className={`animate-spin ${className}`} fill="none">
      <circle cx="10" cy="10" r="8" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M18 10a8 8 0 0 0-8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function DashIcon({ size = 10, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} {...base} strokeWidth={3}>
      <path d="M6 12h12" />
    </svg>
  )
}
