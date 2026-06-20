import React from 'react'
import { Link } from 'react-router-dom'

function FlowStep({ icon, label, sub }) {
  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <div className="w-14 h-14 rounded-2xl bg-gray-800/80 border border-gray-700/60 flex items-center justify-center shadow-lg">
        {icon}
      </div>
      <div className="text-sm font-semibold text-gray-200">{label}</div>
      {sub && <div className="text-xs text-gray-500 max-w-[120px] leading-relaxed">{sub}</div>}
    </div>
  )
}

function Arrow() {
  return (
    <div className="hidden sm:flex items-center text-gray-700 mt-4">
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5l7 7-7 7" />
      </svg>
    </div>
  )
}

export default function DevCredLanding() {
  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 sm:py-24">
        <div className="w-full max-w-3xl mx-auto text-center">

          {/* badge */}
          <div className="flex justify-center mb-8">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-indigo-950/60 border border-indigo-800/50 text-indigo-400 text-xs font-medium">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0117.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              TEE-Attested Developer Credential
            </span>
          </div>

          {/* hero icon */}
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-2xl shadow-indigo-900/60">
              <svg className="w-8 h-8 sm:w-10 sm:h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
            </div>
          </div>

          {/* headline */}
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white mb-4 tracking-tight">
            Dev Credential
          </h1>
          <p className="text-lg sm:text-xl text-gray-300 font-medium mb-4">
            Your private repos. A verifiable credential. No code leaves the enclave.
          </p>
          <p className="text-sm sm:text-base text-gray-500 max-w-xl mx-auto leading-relaxed mb-12">
            Authorise read-only access to your private repos. An Intel TDX enclave reads
            your commit history and issues a <span className="text-gray-300 font-medium">SeniorDevCredential</span> — proving
            seniority level, language depth, and contribution patterns without exposing
            a single line of employer code.
          </p>

          {/* CTA */}
          <div className="flex flex-col sm:flex-row gap-4 items-center justify-center mb-16">
            <Link
              to="/devcred/new"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Generate my credential
            </Link>
          </div>

          {/* flow diagram */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-2 mb-16">
            <FlowStep
              label="GitHub OAuth"
              sub="Read-only token, one-time use"
              icon={
                <svg className="w-6 h-6 text-gray-300" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
                </svg>
              }
            />
            <Arrow />
            <FlowStep
              label="Enclave reads commits"
              sub="Intel TDX — your diffs never leave"
              icon={
                <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              }
            />
            <Arrow />
            <FlowStep
              label="Credential issued"
              sub="Shareable, cryptographically attested"
              icon={
                <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                </svg>
              }
            />
          </div>

          {/* privacy pills */}
          <div className="flex flex-wrap justify-center gap-2 mb-16">
            {[
              'No code stored',
              'No employer names',
              'No repo names',
              'Token used once',
              'TDX-attested',
            ].map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-800/60 border border-gray-700/40 text-gray-400 text-xs font-medium"
              >
                <svg className="w-3 h-3 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {label}
              </span>
            ))}
          </div>

          {/* three steps */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
            {[
              {
                step: '01',
                title: 'Paste a read-only token',
                desc: 'Generate a GitHub PAT with repo:read scope. It is used once and discarded — never written to disk.',
              },
              {
                step: '02',
                title: 'Select your repos',
                desc: 'Add one or more private repos in owner/repo format. The enclave fetches commit metadata only — no file contents.',
              },
              {
                step: '03',
                title: 'Share the credential',
                desc: 'Receive a signed SeniorDevCredential with your seniority level, languages, and specialisms. Share a link with any recruiter.',
              },
            ].map((item) => (
              <div key={item.step} className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40">
                <div className="text-xs font-mono text-indigo-500 mb-2">{item.step}</div>
                <h3 className="text-sm font-semibold text-gray-200 mb-1.5">{item.title}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
