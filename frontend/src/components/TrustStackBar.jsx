import React, { useEffect, useState } from 'react'

function truncateHash(h, len = 12) {
  if (!h) return null
  const clean = h.startsWith('0x') ? h : '0x' + h
  return clean.slice(0, len + 2) + '...'
}

function StackRow({ label, status, value, delay = 0 }) {
  const [filled, setFilled] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setFilled(true), delay)
    return () => clearTimeout(t)
  }, [delay])

  const isActive = status === 'ACTIVE' || status === 'VERIFIED'

  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-gray-800/40 last:border-0">
      <span className="w-36 text-xs font-mono text-gray-400 shrink-0">{label}</span>

      {/* bar */}
      <div className="flex-1 h-1.5 rounded-full bg-gray-800/60 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${
            isActive ? 'bg-emerald-500' : 'bg-indigo-500'
          }`}
          style={{ width: filled ? '100%' : '0%' }}
        />
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {value && (
          <span className="text-xs font-mono text-gray-500">{truncateHash(value)}</span>
        )}
        <span
          className={`text-xs font-semibold font-mono px-2 py-0.5 rounded-full border ${
            isActive
              ? 'text-emerald-400 border-emerald-800/60 bg-emerald-950/40'
              : 'text-indigo-400 border-indigo-800/60 bg-indigo-950/40'
          }`}
        >
          {status}
        </span>
      </div>
    </div>
  )
}

export default function TrustStackBar({ corpusRoot, credentialHash, teeAttested }) {
  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="text-sm font-semibold text-gray-200">Trust Stack</span>
        </div>
      </div>
      <div className="px-4 py-1">
        <StackRow label="TDX ENCLAVE"      status="ACTIVE"   delay={0} />
        <StackRow label="DCAP ATTESTATION" status={teeAttested ? 'VERIFIED' : 'SIMULATION'} delay={150} />
        <StackRow label="REPO CORPUS"      status="VERIFIED" value={corpusRoot}    delay={300} />
        <StackRow label="DEV CREDENTIAL"   status="VERIFIED" value={credentialHash} delay={450} />
      </div>
    </div>
  )
}
