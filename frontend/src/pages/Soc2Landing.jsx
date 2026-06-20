import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const CONTROLS = [
  { id: 'CC6.1', label: 'MFA Enforcement',      pass: true  },
  { id: 'CC6.2', label: 'Least Privilege',       pass: true  },
  { id: 'CC6.3', label: 'Access Logging',        pass: true  },
  { id: 'CC6.6', label: 'No Public S3',          pass: false },
  { id: 'CC7.1', label: 'CloudTrail Active',     pass: true  },
  { id: 'CC7.2', label: 'Alerting Configured',   pass: true  },
]

function ControlRow({ id, label, pass, delay }) {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay)
    return () => clearTimeout(t)
  }, [delay])

  return (
    <div className={`flex items-center justify-between px-4 py-2.5 rounded-lg border transition-all duration-500 ${
      visible ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-4'
    } ${pass
      ? 'border-emerald-800/40 bg-emerald-950/20'
      : 'border-red-800/40 bg-red-950/20'
    }`}>
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-gray-600 w-10">{id}</span>
        <span className="text-sm text-gray-300">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        {pass ? (
          <>
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs font-mono font-semibold text-emerald-400">PASS</span>
          </>
        ) : (
          <>
            <div className="w-1.5 h-1.5 rounded-full bg-red-400" />
            <span className="text-xs font-mono font-semibold text-red-400">FINDING</span>
          </>
        )}
      </div>
    </div>
  )
}

function TeeChip() {
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/50 border border-emerald-800/50 text-emerald-400 text-xs font-mono">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
      </span>
      Intel TDX Enclave · Active
    </div>
  )
}

export default function Soc2Landing() {
  const [started, setStarted] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setStarted(true), 200)
    return () => clearTimeout(t)
  }, [])

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">

      {/* hero */}
      <div className="flex-1 flex flex-col lg:flex-row items-center gap-12 lg:gap-20 px-6 py-16 sm:py-24 max-w-6xl mx-auto w-full">

        {/* left — copy */}
        <div className={`flex-1 transition-all duration-700 ${started ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
          <div className="mb-6">
            <TeeChip />
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white leading-tight mb-6 tracking-tight">
            SOC 2 compliance,{' '}
            <span className="text-emerald-400">proven</span>{' '}
            without exposing your secrets.
          </h1>

          <p className="text-lg text-gray-400 leading-relaxed mb-8 max-w-lg">
            Upload your AWS config JSON. An Intel TDX enclave evaluates six CC6/CC7
            controls and issues a cryptographically attested credential — your auditor
            gets proof, your IAM policies stay private.
          </p>

          <div className="flex flex-wrap gap-3 mb-10">
            {[
              'Raw configs never leave the enclave',
              'DCAP-attested credential',
              'Under 60 seconds',
            ].map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-800/60 border border-gray-700/40 text-gray-400 text-xs font-medium">
                <svg className="w-3 h-3 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {t}
              </span>
            ))}
          </div>

          <Link
            to="/soc2"
            className="inline-flex items-center gap-3 px-8 py-4 rounded-xl bg-emerald-700 hover:bg-emerald-600 text-white font-semibold text-base transition-all shadow-lg shadow-emerald-900/40 hover:shadow-emerald-900/60 hover:-translate-y-0.5 active:translate-y-0"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            Run a compliance audit
          </Link>
        </div>

        {/* right — live control feed */}
        <div className={`w-full lg:w-[380px] flex-shrink-0 transition-all duration-700 delay-200 ${started ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
          <div className="rounded-2xl border border-gray-800/60 bg-gray-900/40 overflow-hidden shadow-2xl">

            {/* fake terminal bar */}
            <div className="flex items-center gap-1.5 px-4 py-3 border-b border-gray-800/60 bg-gray-900/60">
              <div className="w-3 h-3 rounded-full bg-red-500/60" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/60" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/60" />
              <span className="ml-3 text-xs font-mono text-gray-600">AcmeCorp · SOC2ControlCredential</span>
            </div>

            {/* controls */}
            <div className="p-4 space-y-2">
              {CONTROLS.map((c, i) => (
                <ControlRow key={c.id} {...c} delay={400 + i * 120} />
              ))}
            </div>

            {/* attestation footer */}
            <div className="px-4 py-3 border-t border-gray-800/60 bg-gray-900/40 space-y-1">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-gray-600">corpus_root</span>
                <span className="text-gray-500">0x9c1d4e8f…</span>
              </div>
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-gray-600">credential_hash</span>
                <span className="text-gray-500">0x4e8fa21b…</span>
              </div>
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-gray-600">tee_quote</span>
                <span className="text-emerald-500">verified ✓</span>
              </div>
            </div>
          </div>

          {/* caption */}
          <p className="text-center text-xs text-gray-600 mt-3 font-mono">
            Example credential — 5/6 controls effective
          </p>
        </div>
      </div>

      {/* how it works */}
      <div className={`border-t border-gray-800/40 px-6 py-12 transition-all duration-700 delay-500 ${started ? 'opacity-100' : 'opacity-0'}`}>
        <div className="max-w-4xl mx-auto">
          <p className="text-center text-xs font-mono text-gray-600 uppercase tracking-widest mb-8">How it works</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              {
                step: '01',
                title: 'Paste your AWS config',
                body: 'IAM policies, CloudTrail config, S3 bucket policies, CloudWatch alarms — paste JSON directly or run the provided AWS CLI commands.',
              },
              {
                step: '02',
                title: 'Enclave evaluates controls',
                body: 'Six CC6/CC7 controls are checked deterministically inside the Intel TDX TEE. Your raw policies never leave the enclave.',
              },
              {
                step: '03',
                title: 'Download the credential',
                body: 'Receive a SOC2ControlCredential with a DCAP attestation quote. Share it with your auditor — they can verify it without seeing your infrastructure.',
              },
            ].map((item) => (
              <div key={item.step} className="p-5 rounded-xl bg-gray-900/40 border border-gray-800/40">
                <div className="text-xs font-mono text-emerald-600 mb-3">{item.step}</div>
                <h3 className="text-sm font-semibold text-gray-200 mb-2">{item.title}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{item.body}</p>
              </div>
            ))}
          </div>

          <div className="flex justify-center mt-10">
            <Link
              to="/soc2"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-emerald-800/50 text-emerald-400 hover:bg-emerald-950/40 text-sm font-medium transition-all"
            >
              Start auditing
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
