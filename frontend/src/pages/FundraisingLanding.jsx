import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const METRICS = [
  { label: 'MoM Growth',              value: '+12.4%',      ok: true  },
  { label: 'Gross Margin',            value: '71.2%',       ok: true  },
  { label: 'Top Customer Conc.',      value: '18.3%',       ok: true  },
  { label: 'Runway',                  value: '18.2 months', ok: true  },
  { label: 'Monthly Churn',           value: '1.8%',        ok: true  },
  { label: 'ARR Consistency',         value: 'delta +2.1%', ok: true  },
]

function MetricRow({ label, value, ok, delay }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])

  return (
    <div className={`flex items-center justify-between px-4 py-2.5 rounded-lg border transition-all duration-500 ${
      visible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'
    } ${ok ? 'border-emerald-800/40 bg-emerald-950/15' : 'border-red-800/40 bg-red-950/15'}`}>
      <span className="text-sm text-gray-300">{label}</span>
      <div className="flex items-center gap-3">
        <span className={`text-sm font-mono font-semibold ${ok ? 'text-emerald-300' : 'text-red-300'}`}>{value}</span>
        <span className={`text-[10px] font-mono font-bold tracking-wider px-2 py-0.5 rounded border ${
          ok ? 'text-emerald-400 border-emerald-800/50 bg-emerald-950/30' : 'text-red-400 border-red-800/50'
        }`}>
          {ok ? 'VERIFIED' : 'FLAGGED'}
        </span>
      </div>
    </div>
  )
}

function BeforeAfter({ started }) {
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 transition-all duration-700 delay-700 ${started ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
      {/* Before */}
      <div className="rounded-xl border border-gray-800/40 bg-gray-900/30 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-gray-800/40 bg-gray-900/50 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-red-500/60" />
          <span className="text-xs font-mono text-gray-500">What VCs normally ask for</span>
        </div>
        <div className="px-4 py-3 space-y-1.5 text-xs font-mono text-gray-600">
          <p>→ Raw bank statements</p>
          <p>→ Full QuickBooks export</p>
          <p>→ Customer list with ARR</p>
          <p>→ Payroll details</p>
          <p>→ Cap table</p>
          <p className="text-red-500/60 pt-1">Everything. Shared with everyone.</p>
        </div>
      </div>

      {/* After */}
      <div className="rounded-xl border border-emerald-800/30 bg-emerald-950/10 overflow-hidden">
        <div className="px-4 py-2.5 border-b border-emerald-800/30 bg-emerald-950/20 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-mono text-emerald-500">What they get instead</span>
        </div>
        <div className="px-4 py-3 space-y-1.5 text-xs font-mono text-gray-400">
          <p>✓ MoM growth — verified</p>
          <p>✓ Gross margin — verified</p>
          <p>✓ Runway — verified</p>
          <p>✓ Churn rate — verified</p>
          <p>✓ ARR consistency — verified</p>
          <p className="text-emerald-400/80 pt-1">TDX-attested. Raw data stays private.</p>
        </div>
      </div>
    </div>
  )
}

export default function FundraisingLanding() {
  const [started, setStarted] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setStarted(true), 150)
    return () => clearTimeout(t)
  }, [])

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">

      {/* hero */}
      <div className="flex-1 flex flex-col lg:flex-row items-center gap-12 lg:gap-16 px-6 py-16 sm:py-20 max-w-6xl mx-auto w-full">

        {/* left — copy */}
        <div className={`flex-1 transition-all duration-700 ${started ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>

          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-950/60 border border-indigo-800/50 text-indigo-400 text-xs font-mono mb-6">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-400" />
            </span>
            Intel TDX Enclave · Active
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 tracking-tight">
            Your metrics are real.<br />
            <span className="text-indigo-400">Prove it without</span><br />
            showing everything.
          </h1>

          <p className="text-lg text-gray-400 leading-relaxed mb-8 max-w-lg">
            An Intel TDX enclave verifies your financial metrics and issues a
            cryptographic <span className="text-gray-200 font-medium">FundraisingCredential</span> —
            investors get proof your numbers are accurate without ever seeing
            your raw bank statements, customer list, or payroll.
          </p>

          <div className="flex flex-wrap gap-2 mb-10">
            {[
              'Raw financials stay private',
              'Cryptographically verified',
              'Under 60 seconds',
              'TDX-attested',
            ].map(t => (
              <span key={t} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-800/60 border border-gray-700/40 text-gray-400 text-xs font-medium">
                <svg className="w-3 h-3 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {t}
              </span>
            ))}
          </div>

          <Link
            to="/fundraising/new"
            className="inline-flex items-center gap-3 px-8 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            Run diligence
          </Link>
        </div>

        {/* right — live metric feed */}
        <div className={`w-full lg:w-[400px] flex-shrink-0 transition-all duration-700 delay-300 ${started ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
          <div className="rounded-2xl border border-gray-800/60 bg-gray-900/40 overflow-hidden shadow-2xl">

            {/* terminal bar */}
            <div className="flex items-center gap-1.5 px-4 py-3 border-b border-gray-800/60 bg-gray-900/60">
              <div className="w-3 h-3 rounded-full bg-red-500/60" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/60" />
              <span className="ml-3 text-xs font-mono text-gray-600">AcmeCorp · FundraisingCredential</span>
            </div>

            <div className="p-4 space-y-2">
              {METRICS.map((m, i) => (
                <MetricRow key={m.label} {...m} delay={500 + i * 130} />
              ))}
            </div>

            {/* attestation footer */}
            <div className="px-4 py-3 border-t border-gray-800/60 bg-gray-900/40 space-y-1">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-gray-600">corpus_root</span>
                <span className="text-gray-500">0xb7f2a19c…</span>
              </div>
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-gray-600">credential_hash</span>
                <span className="text-gray-500">0x3e9d5c82…</span>
              </div>
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-gray-600">tee_quote</span>
                <span className="text-emerald-500">verified ✓</span>
              </div>
            </div>
          </div>
          <p className="text-center text-xs text-gray-600 mt-3 font-mono">
            Example credential — 6/6 metrics verified
          </p>
        </div>
      </div>

      {/* before / after */}
      <div className={`px-6 pb-10 max-w-6xl mx-auto w-full transition-all duration-700 delay-500 ${started ? 'opacity-100' : 'opacity-0'}`}>
        <p className="text-center text-xs font-mono text-gray-600 uppercase tracking-widest mb-6">The difference</p>
        <BeforeAfter started={started} />
      </div>

      {/* how it works */}
      <div className={`border-t border-gray-800/40 px-6 py-12 transition-all duration-700 delay-700 ${started ? 'opacity-100' : 'opacity-0'}`}>
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-mono text-gray-600 uppercase tracking-widest mb-8">How it works</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              {
                step: '01',
                title: 'Enter your metrics',
                body: 'Paste MoM growth, gross margin, runway, churn, and ARR figures. No raw statements, no customer names — just the numbers you want verified.',
              },
              {
                step: '02',
                title: 'Enclave verifies them',
                body: 'Six financial metrics are recomputed and cross-checked inside an Intel TDX TEE. The enclave proves the math — your underlying data never leaves.',
              },
              {
                step: '03',
                title: 'Share with your investor',
                body: 'Download a FundraisingCredential with a DCAP attestation quote. Your VC gets a tamper-proof verification link — no NDA required to share it.',
              },
            ].map(item => (
              <div key={item.step} className="p-5 rounded-xl bg-gray-900/40 border border-gray-800/40">
                <div className="text-xs font-mono text-indigo-500 mb-3">{item.step}</div>
                <h3 className="text-sm font-semibold text-gray-200 mb-2">{item.title}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{item.body}</p>
              </div>
            ))}
          </div>

          <div className="flex justify-center mt-10">
            <Link
              to="/fundraising/new"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-indigo-800/50 text-indigo-400 hover:bg-indigo-950/40 text-sm font-medium transition-all"
            >
              Generate your credential
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </Link>
          </div>
        </div>
      </div>

    </div>
  )
}
