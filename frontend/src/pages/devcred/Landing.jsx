import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const CREDENTIAL = {
  handle: 'kkoci',
  seniority: 'SENIOR',
  languages: ['Go', 'TypeScript', 'Python'],
  specializations: ['Distributed Systems', 'TEE / Confidential Compute', 'API Design'],
  years: '8.3',
  commits: '2,841',
  testCulture: true,
  confidence: 'high',
  assessment: 'Sustained multi-language output across production systems. Strong test discipline and architectural consistency over 8+ years.',
  corpusRoot: '0xa3f9c1d4',
  credHash: '0x7e2b8f41',
}

function Tag({ children, color = 'indigo' }) {
  const cls = {
    indigo: 'bg-indigo-950/50 border-indigo-800/40 text-indigo-300',
    gray:   'bg-gray-800/50 border-gray-700/40 text-gray-400',
  }[color]
  return (
    <span className={`inline-block px-2 py-0.5 rounded-md border text-xs font-mono ${cls}`}>
      {children}
    </span>
  )
}

function CredentialCard({ visible }) {
  return (
    <div className={`rounded-2xl border border-gray-800/60 bg-gray-900/50 overflow-hidden shadow-2xl transition-all duration-700 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>

      {/* header */}
      <div className="px-5 py-4 border-b border-gray-800/40 bg-gray-900/60 flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-indigo-400 mb-1">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
            SeniorDevCredential
          </div>
          <div className="text-lg font-bold text-white">@{CREDENTIAL.handle}</div>
        </div>
        <span className="px-3 py-1.5 rounded-full border border-emerald-700/60 bg-emerald-950/40 text-emerald-300 text-sm font-bold tracking-wide">
          {CREDENTIAL.seniority}
        </span>
      </div>

      {/* body */}
      <div className="px-5 py-4 space-y-3.5">

        <div>
          <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1.5">Languages</div>
          <div className="flex flex-wrap gap-1.5">
            {CREDENTIAL.languages.map(l => <Tag key={l}>{l}</Tag>)}
          </div>
        </div>

        <div>
          <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1.5">Specialisms</div>
          <div className="flex flex-wrap gap-1.5">
            {CREDENTIAL.specializations.map(s => <Tag key={s} color="gray">{s}</Tag>)}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1">Years Active</div>
            <div className="text-sm font-semibold text-gray-200">{CREDENTIAL.years}</div>
          </div>
          <div>
            <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1">Commits</div>
            <div className="text-sm font-semibold text-gray-200">{CREDENTIAL.commits}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1">Test Culture</div>
            <div className="text-sm font-semibold text-emerald-400">✓ Present</div>
          </div>
          <div>
            <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1">Confidence</div>
            <div className="text-sm font-semibold text-emerald-400 capitalize">{CREDENTIAL.confidence}</div>
          </div>
        </div>

        <div>
          <div className="text-xs font-mono text-gray-600 uppercase tracking-wider mb-1.5">Assessment</div>
          <p className="text-xs text-gray-400 leading-relaxed">{CREDENTIAL.assessment}</p>
        </div>

        <div className="pt-2 border-t border-gray-800/40 space-y-1.5">
          {[
            { label: 'Corpus Root',      value: CREDENTIAL.corpusRoot },
            { label: 'Credential Hash',  value: CREDENTIAL.credHash  },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-xs font-mono text-gray-600">{label}</span>
              <span className="text-xs font-mono text-gray-500">{value}…</span>
            </div>
          ))}
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-gray-600">TDX Attestation</span>
            <span className="text-xs font-mono text-emerald-500">verified ✓</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function TrustPill({ children }) {
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-800/60 border border-gray-700/40 text-gray-400 text-xs font-medium">
      <svg className="w-3 h-3 text-emerald-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
      {children}
    </span>
  )
}

export default function DevCredLanding() {
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
            Your commit history<br />
            is your resume.<br />
            <span className="text-indigo-400">Now it's verifiable.</span>
          </h1>

          <p className="text-lg text-gray-400 leading-relaxed mb-8 max-w-lg">
            Authorise read-only access to your private repos. An Intel TDX enclave
            reads your commit history and issues a <span className="text-gray-200 font-medium">SeniorDevCredential</span> — proving
            seniority, languages, and contribution patterns without exposing a single
            line of employer code.
          </p>

          <div className="flex flex-wrap gap-2 mb-10">
            <TrustPill>No code stored</TrustPill>
            <TrustPill>No employer names</TrustPill>
            <TrustPill>No repo names</TrustPill>
            <TrustPill>Token used once</TrustPill>
            <TrustPill>TDX-attested</TrustPill>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              to="/devcred/new"
              className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              Generate my credential
            </Link>
          </div>
        </div>

        {/* right — credential card preview */}
        <div className={`w-full lg:w-[380px] flex-shrink-0 transition-all duration-700 delay-300 ${started ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
          <CredentialCard visible={started} />
          <p className="text-center text-xs text-gray-600 mt-3 font-mono">
            Example credential — your output will vary
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
                title: 'Paste a read-only token',
                body: 'Generate a GitHub PAT with repo:read scope. It\'s used once inside the enclave and immediately discarded — never written to disk or logged.',
              },
              {
                step: '02',
                title: 'Select your private repos',
                body: 'Add one or more repos in owner/repo format. The enclave fetches commit metadata only — no file contents, no diffs, no employer code.',
              },
              {
                step: '03',
                title: 'Share your credential',
                body: 'Receive a signed SeniorDevCredential with a TDX attestation quote. Share a link with any recruiter — they get proof, you stay in control.',
              },
            ].map((item) => (
              <div key={item.step} className="p-5 rounded-xl bg-gray-900/40 border border-gray-800/40">
                <div className="text-xs font-mono text-indigo-500 mb-3">{item.step}</div>
                <h3 className="text-sm font-semibold text-gray-200 mb-2">{item.title}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{item.body}</p>
              </div>
            ))}
          </div>

          <div className="flex justify-center mt-10">
            <Link
              to="/devcred/new"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-indigo-800/50 text-indigo-400 hover:bg-indigo-950/40 text-sm font-medium transition-all"
            >
              Get started — takes under 2 minutes
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
