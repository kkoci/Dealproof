import React, { useState } from 'react'

function truncate(str, maxLen = 60) {
  if (!str) return ''
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen) + '...'
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // fallback for older browsers
      const el = document.createElement('textarea')
      el.value = text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all bg-gray-700/60 hover:bg-gray-600/60 text-gray-300 hover:text-white border border-gray-600/40 hover:border-gray-500/60"
      title="Copy full attestation"
    >
      {copied ? (
        <>
          <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span className="text-emerald-400">Copied</span>
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          Copy
        </>
      )}
    </button>
  )
}

function TeeModeLabel({ mode }) {
  if (!mode) return null
  const isProduction = mode === 'production'
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
        isProduction
          ? 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50'
          : 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50'
      }`}
    >
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
      </svg>
      TEE: {isProduction ? 'Production' : 'Simulation'}
    </span>
  )
}

export default function AttestationCard({ attestation, dealId, onInspect, dcapData, dcapLoading }) {
  const isSimulation = !attestation || attestation.startsWith('sim_quote:') || attestation.startsWith('sim_')

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="text-sm font-semibold text-gray-200">TEE Attestation</span>
        </div>
        <TeeModeLabel mode={isSimulation ? 'simulation' : 'production'} />
      </div>

      <div className="px-4 py-3">
        <div className="flex items-start gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-xs text-gray-500 uppercase tracking-wider font-medium">Quote</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs font-mono text-gray-300 bg-gray-950/60 rounded-lg px-3 py-2 border border-gray-800/60 break-all leading-relaxed">
                {attestation ? truncate(attestation, 60) : <span className="text-gray-600 italic">No attestation</span>}
              </code>
              {attestation && <CopyButton text={attestation} />}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onInspect}
            disabled={dcapLoading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 hover:text-indigo-300 border border-indigo-700/40 hover:border-indigo-600/60 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {dcapLoading ? (
              <>
                <div className="w-3 h-3 border border-indigo-400 border-t-transparent rounded-full animate-spin" />
                Loading...
              </>
            ) : (
              <>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                Inspect DCAP Quote
              </>
            )}
          </button>
        </div>
      </div>

      {dcapData && (
        <div className="px-4 pb-4">
          <div className="rounded-lg border border-gray-800/60 bg-gray-950/50 overflow-hidden">
            <div className="px-3 py-2 border-b border-gray-800/40 bg-gray-900/40">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">DCAP Quote Details</span>
            </div>
            <table className="w-full text-xs">
              <tbody>
                {[
                  { label: 'Mode', value: dcapData.mode },
                  { label: 'Version', value: dcapData.version },
                  { label: 'TEE Type', value: dcapData.tee_type },
                  {
                    label: 'QE Vendor ID',
                    value: dcapData.qe_vendor_id
                      ? dcapData.qe_vendor_id.slice(0, 16) + (dcapData.qe_vendor_id.length > 16 ? '...' : '')
                      : 'N/A',
                    mono: true,
                  },
                  {
                    label: 'Deal Terms Hash',
                    value: dcapData.deal_terms_hash
                      ? dcapData.deal_terms_hash.slice(0, 16) + (dcapData.deal_terms_hash.length > 16 ? '...' : '')
                      : 'N/A',
                    mono: true,
                  },
                  { label: 'Status', value: dcapData.verification_status },
                ].map((row) => (
                  <tr key={row.label} className="border-b border-gray-800/30 last:border-0">
                    <td className="px-3 py-2 text-gray-500 font-medium w-36">{row.label}</td>
                    <td className={`px-3 py-2 text-gray-200 ${row.mono ? 'font-mono' : ''}`}>
                      {String(row.value ?? 'N/A')}
                    </td>
                  </tr>
                ))}
                {dcapData.error && (
                  <tr>
                    <td className="px-3 py-2 text-red-400 font-medium">Error</td>
                    <td className="px-3 py-2 text-red-300 font-mono">{dcapData.error}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
