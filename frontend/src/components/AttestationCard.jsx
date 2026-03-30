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
        <div className="px-4 pb-4 space-y-3">
          {/* intel_verified headline */}
          <div
            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border ${
              dcapData.intel_verified
                ? 'bg-emerald-950/40 border-emerald-800/50'
                : dcapData.mode === 'simulation'
                ? 'bg-yellow-950/40 border-yellow-800/50'
                : 'bg-red-950/30 border-red-800/40'
            }`}
          >
            {dcapData.intel_verified ? (
              <svg className="w-4 h-4 text-emerald-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0117.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            )}
            <div>
              <div className={`text-sm font-semibold ${dcapData.intel_verified ? 'text-emerald-300' : dcapData.mode === 'simulation' ? 'text-yellow-300' : 'text-gray-300'}`}>
                {dcapData.intel_verified
                  ? 'Intel DCAP Fully Verified'
                  : dcapData.mode === 'simulation'
                  ? 'Simulation Mode — No Hardware Attestation'
                  : 'Partial Verification'}
              </div>
              <div className={`text-xs font-mono mt-0.5 ${dcapData.intel_verified ? 'text-emerald-500' : 'text-gray-500'}`}>
                {dcapData.verification_status}
              </div>
            </div>
          </div>

          {/* 4-step chain (production only) */}
          {dcapData.mode === 'production' && (
            <div className="rounded-lg border border-gray-800/60 bg-gray-950/50 overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-800/40 bg-gray-900/40">
                <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Verification Chain</span>
              </div>
              <div className="divide-y divide-gray-800/30">
                {[
                  { step: '1', label: 'PCK Cert Chain → Intel Root CA', ok: dcapData.cert_chain_valid, detail: dcapData.pck_cert_subject },
                  { step: '2', label: 'QE Report Signature (PCK key)', ok: dcapData.qe_sig_valid },
                  { step: '3', label: 'ATT Key Binding (QE REPORTDATA)', ok: dcapData.att_key_binding_valid },
                  { step: '4', label: 'TD Report Signature (ATT key)', ok: dcapData.td_sig_valid },
                ].map((row) => (
                  <div key={row.step} className="flex items-center gap-3 px-3 py-2.5">
                    <span className="text-xs font-mono text-gray-600 w-4 flex-shrink-0">{row.step}</span>
                    <span className="flex-1 text-xs text-gray-300">{row.label}</span>
                    {row.detail && (
                      <span className="text-xs font-mono text-gray-500 truncate max-w-[120px]" title={row.detail}>{row.detail}</span>
                    )}
                    {row.ok === true && (
                      <svg className="w-4 h-4 text-emerald-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    )}
                    {row.ok === false && (
                      <svg className="w-4 h-4 text-red-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    )}
                    {row.ok === null && (
                      <span className="text-xs text-gray-600">—</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quote metadata */}
          <div className="rounded-lg border border-gray-800/60 bg-gray-950/50 overflow-hidden">
            <div className="px-3 py-2 border-b border-gray-800/40 bg-gray-900/40">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Quote Metadata</span>
            </div>
            <table className="w-full text-xs">
              <tbody>
                {[
                  { label: 'Version', value: dcapData.version },
                  { label: 'TEE Type', value: dcapData.tee_type },
                  {
                    label: 'Deal Terms Hash',
                    value: dcapData.deal_terms_hash
                      ? dcapData.deal_terms_hash.slice(0, 20) + '...'
                      : null,
                    mono: true,
                  },
                ].filter(r => r.value != null).map((row) => (
                  <tr key={row.label} className="border-b border-gray-800/30 last:border-0">
                    <td className="px-3 py-2 text-gray-500 font-medium w-36">{row.label}</td>
                    <td className={`px-3 py-2 text-gray-200 ${row.mono ? 'font-mono' : ''}`}>
                      {String(row.value)}
                    </td>
                  </tr>
                ))}
                {dcapData.error && (
                  <tr>
                    <td className="px-3 py-2 text-red-400 font-medium">Error</td>
                    <td className="px-3 py-2 text-red-300 font-mono break-all">{dcapData.error}</td>
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
