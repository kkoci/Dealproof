// Shared button primitive — one place that owns every variant used across the Offer Check vertical,
// replacing nine files' worth of hand-copied Tailwind strings (a real consistency risk the v4 plan
// flagged explicitly). Visual-only: callers still own onClick/type/disabled/children exactly as
// before — no behavior moves here.
//
// `as` lets this render as react-router's `Link` (or a plain `a`) instead of a `<button>`, so a
// link that should look like a button never nests an actual <button> inside an <a> (invalid HTML —
// two interactive elements, broken focus order). Pass `as={Link} to="/somewhere"`.
//
// Motion note (reads for the follow-up interaction pass): press feedback (scale(0.96) on :active,
// 100ms) is kept because it already existed, inconsistently, on some buttons in this codebase before
// this revamp — this centralizes it, it doesn't add a new motion system. Everything past that
// (hover-lift, spring settle, choreographed entrances) is deliberately NOT added here; that's prompt
// 2's job, and it can be added to this one component to reach every button at once.
import React from 'react'
import { SpinnerIcon } from './icons.jsx'

const SIZE = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-6 text-sm gap-2',
}

const VARIANT = {
  primary: 'bg-teal text-white hover:bg-teal-hover border border-transparent',
  success: 'bg-success text-white hover:bg-success-hover border border-transparent',
  destructive: 'bg-danger text-white hover:bg-danger-hover border border-transparent',
  secondary: 'bg-transparent text-ink-secondary border-[1.5px] border-border-strong hover:bg-bg-elevated',
  subtle: 'bg-teal-subtle text-teal border-[1.5px] border-teal hover:bg-teal-subtle/70',
  ghost: 'bg-transparent text-teal hover:text-teal-hover border border-transparent px-0 h-auto',
}

export function buttonClass({ variant = 'primary', size = 'md', fullWidth = false, className = '' } = {}) {
  const isGhost = variant === 'ghost'
  return [
    'focus-ring inline-flex items-center justify-center rounded-lg font-semibold',
    'transition-[background-color,border-color,color,transform] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)]',
    'active:scale-[0.96] active:duration-100 disabled:active:scale-100',
    'disabled:opacity-50 disabled:cursor-not-allowed',
    isGhost ? 'text-sm font-medium' : SIZE[size],
    VARIANT[variant],
    fullWidth ? 'w-full' : '',
    className,
  ].join(' ')
}

export default function Button({
  as: Component = 'button',
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  fullWidth = false,
  className = '',
  children,
  ...rest
}) {
  const extra = Component === 'button' ? { disabled: disabled || loading } : {}
  return (
    <Component className={buttonClass({ variant, size, fullWidth, className })} {...extra} {...rest}>
      {loading && <SpinnerIcon size={size === 'lg' ? 16 : 14} />}
      {children}
    </Component>
  )
}
