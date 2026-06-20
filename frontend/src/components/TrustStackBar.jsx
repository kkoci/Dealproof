import React from 'react'

function TrustRow({ label, status, value, mono }) {
  const statusConfig = {
    active:   { dot: 'bg-emerald-400', badge: 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50', label: 'ACTIVE' },
    verified: { dot: 'bg-emerald-400', badge: 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50', label: 'VERIFIED' },
    pending:  { dot: 'bg-yellow-400 animate-pulse', badge: 'bg-yellow-950/50 text-yellow-300 border-yellow-800/50', label: 'PENDING' },
    failed:   { dot: 'bg-red-400', badge: 'bg-red-950/50 text-red-300 border-red-800/50', label: 'FAILED' },
  }
  const cfg = statusConfig[status] || statusConfig.verified

  return (
    <div className="flex items-center gap-3 py-2.5 px-4 border-b border-gray-800/40 last:border-b-0">
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
      <span className="text-xs font-mono text-gray-400 flex-1 min-w-0">{label}</span>
      {value && (
        <span className={`text-xs truncate max-w-[120px] ${mono ? 'font-mono text-gray-500' : 'text-gray-500'}`}>
          {value}
        </span>
      )}
      <span className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border flex-shrink-0 ${cfg.badge}`}>
        {cfg.label}
      </span>
    </div>
  )
}

export default function TrustStackBar({ corpusRoot, credentialHash, teeQuote }) {
  const short = (h) => h ? `0x${h.slice(0, 8)}…` : null
  const hasQuote = !!teeQuote

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-2">
          <svg className="w-3.5 h-3.5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          Trust Stack
        </h3>
      </div>
      <TrustRow label="TDX ENCLAVE" status="active" />
      <TrustRow label="DCAP ATTESTATION" status={hasQuote ? 'verified' : 'pending'} />
      <TrustRow label="METRICS CORPUS" status={corpusRoot ? 'verified' : 'pending'} value={short(corpusRoot)} mono />
      <TrustRow label="DILIGENCE CREDENTIAL" status={credentialHash ? 'verified' : 'pending'} value={short(credentialHash)} mono />
    </div>
  )
}
