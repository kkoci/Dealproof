// The signature element (v5 "The Enclave" design plan) — a radial instrument gauge, replacing v4's
// horizontal balance-beam. Same drop-in contract as before (`{ gapPct, label }`, same null/undefined
// handling), only the rendering changed, so every existing call site in CandidateSession/
// EmployerSession keeps working untouched.
//
// Why a gauge over a beam: the brief asked for real compositional risk and a moment worth
// screenshotting. A thin line with two dots is calm but forgettable; a dial with a needle reads
// immediately as "instrument you'd trust with a real reading" — the same category of object as a
// pressure gauge or a seismograph, which is exactly the register this whole direction is built on.
// The needle sweeps ±80° off vertical (not a full ±90°) so it never lies flat even at the extremes.
// Colour logic is unchanged from v4: large gap = gold/attention, closing = green, near-zero = cyan
// ("signal locked") — see tokens.css for why zero-gap is deliberately NOT the same hue as the
// attestation/proof accent this time (two distinct registers: ceremonial copper vs. technical cyan).
import React from 'react'

const MAX_SWEEP_DEG = 80
const TICK_STEPS = [-80, -60, -40, -20, 0, 20, 40, 60, 80]

function pointAt(cx, cy, r, deg) {
  const rad = (deg * Math.PI) / 180
  return { x: cx + r * Math.sin(rad), y: cy - r * Math.cos(rad) }
}

export default function BalanceMeter({ gapPct, label = 'Gap to current position' }) {
  if (gapPct === null || gapPct === undefined) return null

  const abs = Math.abs(gapPct)
  const tone = abs > 5 ? 'large' : abs > 2 ? 'closing' : 'zero'
  const textClass = { large: 'text-gap-large', closing: 'text-gap-closing', zero: 'text-gap-zero' }[tone]
  const strokeClass = { large: 'stroke-gap-large', closing: 'stroke-gap-closing', zero: 'stroke-gap-zero' }[tone]
  const fillClass = { large: 'fill-gap-large', closing: 'fill-gap-closing', zero: 'fill-gap-zero' }[tone]
  const glowClass = {
    large: 'drop-shadow-[0_0_10px_var(--color-gap-large)]',
    closing: 'drop-shadow-[0_0_10px_var(--color-gap-closing)]',
    zero: 'drop-shadow-[0_0_14px_var(--color-gap-zero)]',
  }[tone]

  const clamped = Math.max(-50, Math.min(50, gapPct))
  const needleDeg = (clamped / 50) * MAX_SWEEP_DEG

  const cx = 110
  const cy = 122
  const trackR = 98
  const tickInnerR = 82
  const needleLen = 76

  const trackStart = pointAt(cx, cy, trackR, -90)
  const trackEnd = pointAt(cx, cy, trackR, 90)
  const needleTip = pointAt(cx, cy, needleLen, needleDeg)

  return (
    <div className="mb-2">
      <div className="flex items-baseline justify-between mb-2">
        {label && <span className="text-data-label uppercase text-ink-muted">{label}</span>}
        <span className={`font-display font-semibold tabular-nums text-hero-sm ${textClass} ${!label ? 'mx-auto' : ''}`}>
          {gapPct > 0 ? '+' : ''}{gapPct.toFixed(1)}%
        </span>
      </div>
      <div className="relative w-full" style={{ maxWidth: 320, margin: '0 auto' }}>
        <svg viewBox="0 0 220 132" className="w-full h-auto" aria-hidden="true">
          {/* outer track — white-alpha rather than the border tokens: this needs to read clearly
              as an instrument bezel regardless of exactly which dark surface it sits on. */}
          <path
            d={`M ${trackStart.x} ${trackStart.y} A ${trackR} ${trackR} 0 0 1 ${trackEnd.x} ${trackEnd.y}`}
            fill="none"
            stroke="rgba(255,255,255,0.14)"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          {/* tick marks */}
          {TICK_STEPS.map((deg) => {
            const inner = pointAt(cx, cy, tickInnerR, deg)
            const outer = pointAt(cx, cy, trackR, deg)
            const isCenter = deg === 0
            return (
              <line
                key={deg}
                x1={inner.x}
                y1={inner.y}
                x2={outer.x}
                y2={outer.y}
                stroke={isCenter ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.22)'}
                strokeWidth={isCenter ? 2 : 1.25}
                strokeLinecap="round"
              />
            )
          })}
          {/* needle */}
          <g className={`${strokeClass} ${glowClass} transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]`}>
            <line x1={cx} y1={cy} x2={needleTip.x} y2={needleTip.y} strokeWidth="2.5" strokeLinecap="round" />
          </g>
          <circle cx={cx} cy={cy} r="5" className={`${fillClass} ${glowClass}`} stroke="none" />
        </svg>
      </div>
    </div>
  )
}
