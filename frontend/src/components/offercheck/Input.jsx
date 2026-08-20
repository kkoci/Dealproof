// Shared form-field primitives. `appearance: none` on Select per luxe's Controls chapter ("no
// native chrome ships") — restyled with a custom chevron rather than a full custom listbox, since
// every select in this vertical has ≤3 options and is genuinely low-stakes (the skill's own
// "throwaway form" exception). Behavior (value/onChange/required/etc.) is untouched — these only
// change how the control looks.
import React from 'react'
import { ChevronDownIcon } from './icons.jsx'

// border-strong (not border-DEFAULT) — on the v5 dark surface, bg-input and border-DEFAULT sit too
// close in luminance to read as a clear field edge; a form control needs a more visible boundary
// than a static card does.
const fieldBase =
  'w-full px-3 py-2.5 rounded-lg bg-bg-input border border-border-strong text-ink-primary placeholder:text-ink-muted text-sm ' +
  'transition-[border-color,box-shadow] duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] ' +
  'focus:outline-none focus:border-teal focus:ring-[3px] focus:ring-teal/[0.18] ' +
  'disabled:opacity-50 disabled:cursor-not-allowed'

export function FieldLabel({ children, className = '' }) {
  return <label className={`block text-xs font-medium text-ink-secondary mb-1.5 ${className}`}>{children}</label>
}

export const Input = React.forwardRef(function Input({ className = '', mono = false, ...rest }, ref) {
  return <input ref={ref} className={`${fieldBase} ${mono ? 'font-mono tnum' : ''} ${className}`} {...rest} />
})

export const Textarea = React.forwardRef(function Textarea({ className = '', ...rest }, ref) {
  return <textarea ref={ref} className={`${fieldBase} resize-none ${className}`} {...rest} />
})

export function Select({ className = '', children, ...rest }) {
  return (
    <div className="relative">
      <select
        className={`${fieldBase} appearance-none pr-9 cursor-pointer ${className}`}
        {...rest}
      >
        {children}
      </select>
      <ChevronDownIcon size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted" />
    </div>
  )
}
