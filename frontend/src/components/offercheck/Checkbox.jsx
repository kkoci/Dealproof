// Custom checkbox — luxe Controls chapter ("no native chrome ships"): the native input is kept for
// keyboard/screen-reader semantics but visually hidden, a styled box (driven by React state, not CSS
// sibling tricks, so the check mark itself is unambiguous) sits next to it.
import React from 'react'
import { CheckIcon } from './icons.jsx'

export default function Checkbox({ checked, onChange, children, className = '', ...rest }) {
  return (
    <label className={`flex items-start gap-2.5 cursor-pointer group ${className}`}>
      <input type="checkbox" checked={checked} onChange={onChange} className="sr-only peer" {...rest} />
      <span
        className={`flex items-center justify-center w-4 h-4 mt-0.5 shrink-0 rounded-[5px] border-[1.5px]
          transition-colors duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] peer-focus-visible:ring-[3px] peer-focus-visible:ring-teal/[0.14]
          ${checked ? 'bg-teal border-teal' : 'bg-bg-input border-border-strong group-hover:border-teal'}`}
      >
        {checked && <CheckIcon size={11} className="text-white" />}
      </span>
      <span className="text-xs text-ink-secondary">{children}</span>
    </label>
  )
}
