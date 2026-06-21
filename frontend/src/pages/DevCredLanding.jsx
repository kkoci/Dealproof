import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestDevCred, evaluateDevCred } from '../api.js'

// ---------------------------------------------------------------------------
// Demo scenario — used by one-click demo buttons
// ---------------------------------------------------------------------------

const _GENUINE_SENIOR_COMMITS = (() => {
  const commits = []
  const goFiles = ['pkg/server.go', 'pkg/handler.go', 'pkg/router.go', 'internal/db.go', 'internal/config.go']
  const pyFiles = ['scripts/deploy.py', 'tools/metrics.py', 'scripts/migrate.py']
  for (let i = 0; i < 300; i++) {
    const frac = i / 300
    const year = 2016 + Math.floor(frac * 8)
    const month = String(1 + (i % 12)).padStart(2, '0')
    const day = String(1 + (i % 28)).padStart(2, '0')
    const isTest = i % 4 === 0
    const files = i % 3 === 0
      ? pyFiles.slice(0, 2)
      : goFiles.slice(0, 3)
    if (isTest) files.push('tests/server_test.go')
    commits.push({
      sha: `commit_${String(i).padStart(5, '0')}`,
      author: 'senior-dev',
      timestamp: `${year}-${month}-${day}T10:00:00Z`,
      message: `feat: implement feature ${i} with detailed description and context`,
      diff_stat: { additions: 80, deletions: 20 },
      changed_files: files,
    })
  }
  return commits
})()

const _ADVERSARIAL_COMMITS = (() => {
  const commits = []
  for (let i = 0; i < 25; i++) {
    const month = String(1 + (i % 12)).padStart(2, '0')
    commits.push({
      sha: `adv_${String(i).padStart(3, '0')}`,
      author: 'adv-dev',
      timestamp: `2023-${month}-15T10:00:00Z`,
      message: 'Refactored the distributed consensus layer to improve Byzantine fault-tolerance using Raft protocol — led architecture across 12 microservices',
      diff_stat: { additions: 3, deletions: 1 },
      changed_files: ['main.py'],
    })
  }
  return commits
})()

// ---------------------------------------------------------------------------
// Demo runner
// ---------------------------------------------------------------------------

function useDemoRunner() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(null)
  const [error, setError] = useState(null)

  async function runDemo(scenarioKey, commits, handle) {
    setLoading(scenarioKey)
    setError(null)
    try {
      const credId = `demo-${scenarioKey}-${Date.now()}`
      await ingestDevCred({
        credential_id: credId,
        developer_handle: handle,
        mode: 'direct',
        commits,
      })
      const cred = await evaluateDevCred(credId, {})
      navigate(`/devcred/${credId}`, { state: { cred } })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(null)
    }
  }

  return { loading, error, runDemo }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function DevCredLanding() {
  const navigate = useNavigate()
  const { loading, error, runDemo } = useDemoRunner()

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-gray-950 text-gray-100">

      {/* Hero */}
      <div className="max-w-5xl mx-auto px-4 pt-20 pb-16 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-teal-800/50 bg-teal-950/30 text-xs text-teal-400 font-mono mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse" />
          Powered by Intel TDX · Phala Cloud
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold text-gray-100 leading-tight mb-4">
          Your private repos.
          <br />
          <span className="text-teal-400">A verifiable credential.</span>
        </h1>

        <p className="text-lg text-gray-400 max-w-2xl mx-auto mb-8 leading-relaxed">
          No code leaves the enclave. The enclave reasons over your commit history
          and issues a{' '}
          <span className="text-gray-200 font-semibold">SeniorDevCredential</span>
          {' '}— proving seniority level, language depth, and contribution patterns
          without exposing employer code or repo names.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <button
            onClick={() => navigate('/devcred/new')}
            className="px-6 py-3 rounded-xl bg-teal-600 hover:bg-teal-500 text-white font-semibold transition-colors flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Generate my credential
          </button>
        </div>
      </div>

      {/* SCAE callout */}
      <div className="max-w-4xl mx-auto px-4 mb-16">
        <div className="rounded-2xl border border-amber-800/30 bg-amber-950/10 px-6 py-5">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-900/40 border border-amber-800/40 flex items-center justify-center flex-shrink-0 mt-0.5">
              <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold text-amber-300 mb-1">SCAE Resistance</p>
              <p className="text-sm text-gray-400 leading-relaxed">
                A developer can write impressive commit messages claiming to have{' '}
                <em>"led distributed consensus architecture"</em>. The deterministic inspector
                doesn't read messages — it reads actual diff sizes, file counts, and date
                ranges. Impressive words on tiny 3-line commits get caught.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* One-click demo cards */}
      <div className="max-w-4xl mx-auto px-4 mb-20">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest text-center mb-6">
          One-click demos
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Genuine senior */}
          <button
            onClick={() => runDemo('senior', _GENUINE_SENIOR_COMMITS, 'senior-dev')}
            disabled={!!loading}
            className="relative group text-left rounded-2xl border border-emerald-800/30 bg-emerald-950/10 px-6 py-5 hover:border-emerald-700/50 hover:bg-emerald-950/20 transition-all disabled:opacity-50"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
                Genuine Senior
              </span>
              {loading === 'senior' ? (
                <div className="w-4 h-4 border-2 border-emerald-500/40 border-t-emerald-400 rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4 text-emerald-600 group-hover:text-emerald-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
            <p className="text-sm text-gray-300 font-semibold mb-1">8 years · Go + Python · 25% test ratio</p>
            <p className="text-xs text-gray-500 leading-relaxed">
              300 commits, consistent contribution, deep language coverage.
              Expected result: <span className="text-emerald-400">Senior</span>, high confidence.
            </p>
          </button>

          {/* SCAE: adversarial messages */}
          <button
            onClick={() => runDemo('scae', _ADVERSARIAL_COMMITS, 'adv-dev')}
            disabled={!!loading}
            className="relative group text-left rounded-2xl border border-amber-800/30 bg-amber-950/10 px-6 py-5 hover:border-amber-700/50 hover:bg-amber-950/20 transition-all disabled:opacity-50"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                SCAE: Adversarial Messages
              </span>
              {loading === 'scae' ? (
                <div className="w-4 h-4 border-2 border-amber-500/40 border-t-amber-400 rounded-full animate-spin" />
              ) : (
                <svg className="w-4 h-4 text-amber-600 group-hover:text-amber-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              )}
            </div>
            <p className="text-sm text-gray-300 font-semibold mb-1">1 year · 25 commits · 3-line diffs</p>
            <p className="text-xs text-gray-500 leading-relaxed">
              Impressive messages claiming "distributed consensus architecture."
              Expected result: <span className="text-amber-400">Junior</span> — hard floor holds.
            </p>
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-lg bg-red-950/40 border border-red-800/50 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}
      </div>

      {/* How it works */}
      <div className="max-w-4xl mx-auto px-4 mb-20">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-widest text-center mb-8">
          How it works
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            {
              step: '01',
              title: 'Authenticate',
              desc: 'Paste a read-only GitHub token or upload commits directly. Token is used once and discarded — never written to disk.',
              color: 'text-teal-400',
            },
            {
              step: '02',
              title: 'Enclave analyzes',
              desc: 'GitInspectorAgent computes hard findings from diff sizes, dates, and language distribution. No code leaves the enclave.',
              color: 'text-indigo-400',
            },
            {
              step: '03',
              title: 'Credential issued',
              desc: 'SeniorDevCredential attested by Intel TDX. Share with a recruiter — they verify the DCAP quote, not your CV.',
              color: 'text-emerald-400',
            },
          ].map(({ step, title, desc, color }) => (
            <div key={step} className="rounded-xl border border-gray-800/60 bg-gray-900/30 px-5 py-5">
              <p className={`text-xs font-mono font-bold mb-2 ${color}`}>{step}</p>
              <p className="text-sm font-semibold text-gray-200 mb-2">{title}</p>
              <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Trust stack illustration */}
      <div className="max-w-lg mx-auto px-4 mb-20">
        <div className="rounded-2xl border border-gray-800/60 bg-gray-900/20 px-6 py-6 space-y-3">
          {[
            { label: 'TDX ENCLAVE',      color: 'bg-teal-500', status: 'ACTIVE' },
            { label: 'DCAP ATTESTATION', color: 'bg-indigo-500', status: 'VERIFIED' },
            { label: 'REPO CORPUS',      color: 'bg-violet-500', status: '0x9c1d…' },
            { label: 'DEV CREDENTIAL',   color: 'bg-emerald-500', status: '0x4e8f…' },
          ].map(({ label, color, status }) => (
            <div key={label} className="flex items-center gap-3">
              <span className="text-xs font-mono text-gray-500 w-36 flex-shrink-0">{label}</span>
              <div className={`h-2 flex-1 rounded-full ${color} opacity-70`} />
              <span className="text-xs font-mono text-gray-400 w-20 text-right">{status}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom CTA */}
      <div className="max-w-2xl mx-auto px-4 pb-20 text-center">
        <button
          onClick={() => navigate('/devcred/new')}
          className="px-8 py-3.5 rounded-xl bg-gray-800 hover:bg-gray-700 border border-gray-700/60 text-white font-semibold transition-colors"
        >
          Enter repos manually →
        </button>
      </div>

    </div>
  )
}
