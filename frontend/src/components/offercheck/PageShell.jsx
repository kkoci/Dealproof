// The repeated top-level page wrapper (min-height flex column, max-w-3xl centered column,
// consistent vertical rhythm) that was hand-copied at the top of every page's JSX. `width` escapes
// exist for the two genuine outliers: Landing's wider marketing hero and CompanyRegister's narrower
// single-card auth form.
import React from 'react'

const WIDTH = {
  md: 'max-w-md',
  lg: 'max-w-2xl',
  xl: 'max-w-3xl',
  '2xl': 'max-w-4xl',
}

export default function PageShell({ width = 'xl', className = '', children }) {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className={`w-full ${WIDTH[width]} mx-auto ${className}`}>{children}</div>
    </div>
  )
}
