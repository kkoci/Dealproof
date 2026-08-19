// The signature element (v4 design plan). Gap-to-current-position IS the product's real mechanic —
// this makes the "two sides finding equilibrium" metaphor literal instead of decorating with it: a
// beam pivoting on a fixed fulcrum, tilting toward whichever side is further from agreement. Deliberately
// restrained (max ~7° of tilt, no illustrated pans/chains/weights) after an explicit self-critique pass
// flagged a literal seesaw graphic as gimmicky for a calm, high-stakes financial product — the beam reads
// as an instrument, not a toy. Zero gap resolves to the same teal hue as "verified" elsewhere in this
// system: the payoff of the metaphor is that equilibrium and attestation are visually the same idea.
//
// Drop-in replacement for the old per-file GapMeter — identical `{ gapPct }` prop, same null/undefined
// handling (renders nothing pre-negotiation).
import React from 'react'

const MAX_TILT_DEG = 7

export default function BalanceMeter({ gapPct, label = "Gap to current position" }) {
  if (gapPct === null || gapPct === undefined) return null

  const abs = Math.abs(gapPct)
  const tone = abs > 5 ? 'large' : abs > 2 ? 'closing' : 'zero'
  const textClass = { large: 'text-gap-large', closing: 'text-gap-closing', zero: 'text-gap-zero' }[tone]
  const strokeClass = { large: 'stroke-gap-large', closing: 'stroke-gap-closing', zero: 'stroke-gap-zero' }[tone]
  const fillClass = { large: 'fill-gap-large', closing: 'fill-gap-closing', zero: 'fill-gap-zero' }[tone]

  const clamped = Math.max(-50, Math.min(50, gapPct))
  const angle = (clamped / 50) * MAX_TILT_DEG

  return (
    <div className="mb-6">
      <div className="flex items-baseline justify-between mb-3">
        <span className="text-data-label uppercase text-ink-muted">{label}</span>
        <span className={`font-mono tnum text-hero-sm ${textClass}`}>
          {gapPct > 0 ? '+' : ''}{gapPct.toFixed(1)}%
        </span>
      </div>
      <svg viewBox="0 0 200 34" className="w-full h-8" aria-hidden="true">
        {/* fulcrum — fixed, never rotates */}
        <path d="M100 16 L94 28 L106 28 Z" className="fill-border-strong" />
        <g
          className={`${strokeClass} transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]`}
          style={{ transform: `rotate(${angle}deg)`, transformOrigin: '100px 16px' }}
        >
          <line x1="26" y1="16" x2="174" y2="16" strokeWidth="2" strokeLinecap="round" />
          <circle cx="26" cy="16" r="4.5" className={fillClass} stroke="none" />
          <circle cx="174" cy="16" r="4.5" className={fillClass} stroke="none" />
        </g>
      </svg>
    </div>
  )
}
