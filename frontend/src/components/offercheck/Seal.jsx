// The one ceremonial treatment in the system — ring + inset highlight (Card emphasis="seal") plus
// the SealIcon, reserved for exactly the moments something has been cryptographically proven: the
// TDX attestation receipt, a filed-dispute confirmation, StageSpine's "done" mark. Everywhere else in
// this vertical stays calm and flat on purpose — concentrating the emphasis here is what makes it read
// as significant instead of decorative.
import React from 'react'
import Card from './Card.jsx'
import { SealIcon } from './icons.jsx'

export function SealMark({ size = 'md', className = '' }) {
  const dims = size === 'lg' ? 'w-14 h-14' : size === 'sm' ? 'w-8 h-8' : 'w-10 h-10'
  const iconSize = size === 'lg' ? 28 : size === 'sm' ? 16 : 20
  return (
    <div
      className={`${dims} rounded-full bg-teal-subtle border border-teal-border flex items-center justify-center text-teal shadow-seal shrink-0 ${className}`}
    >
      <SealIcon size={iconSize} />
    </div>
  )
}

export default function Seal({ eyebrow, title, children, className = '' }) {
  return (
    <Card emphasis="seal" padding="lg" className={className}>
      <div className="flex items-start gap-4">
        <SealMark />
        <div className="flex-1 min-w-0">
          {eyebrow && <p className="text-data-label uppercase text-teal-text mb-1">{eyebrow}</p>}
          {title && <h3 className="text-base font-semibold text-ink-primary mb-2">{title}</h3>}
          {children}
        </div>
      </div>
    </Card>
  )
}
