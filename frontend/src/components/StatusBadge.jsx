import React from 'react'

const STATUS_CONFIG = {
  pending: {
    label: 'Pending',
    className: 'bg-gray-700/60 text-gray-300 border-gray-600/50',
    dot: 'bg-gray-400',
    pulse: false,
  },
  negotiating: {
    label: 'Negotiating',
    className: 'bg-blue-900/40 text-blue-300 border-blue-700/50',
    dot: 'bg-blue-400',
    pulse: true,
  },
  agreed: {
    label: 'Agreed',
    className: 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50',
    dot: 'bg-emerald-400',
    pulse: false,
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-900/40 text-red-300 border-red-700/50',
    dot: 'bg-red-400',
    pulse: false,
  },
  verification_failed: {
    label: 'Verification Failed',
    className: 'bg-orange-900/40 text-orange-300 border-orange-700/50',
    dot: 'bg-orange-400',
    pulse: false,
  },
}

export default function StatusBadge({ status, className = '' }) {
  const config = STATUS_CONFIG[status] || {
    label: status || 'Unknown',
    className: 'bg-gray-700/60 text-gray-300 border-gray-600/50',
    dot: 'bg-gray-400',
    pulse: false,
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${config.className} ${className}`}
    >
      <span className="relative flex h-2 w-2">
        {config.pulse && (
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${config.dot}`}
          />
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${config.dot}`} />
      </span>
      {config.label}
    </span>
  )
}
