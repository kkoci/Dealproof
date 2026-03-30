import React, { useEffect, useState, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { getHealth } from '../api.js'

function HealthIndicator({ health, loading, error }) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <div className="w-2 h-2 rounded-full bg-gray-600 animate-pulse" />
        <span className="font-mono">Connecting to backend...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-red-400">
        <div className="w-2 h-2 rounded-full bg-red-500" />
        <span className="font-mono">Backend offline</span>
      </div>
    )
  }

  if (!health) return null

  const isProduction = health.tee_mode === 'production'
  return (
    <div
      className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-full border ${
        isProduction
          ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-400'
          : 'bg-yellow-950/40 border-yellow-800/50 text-yellow-400'
      }`}
    >
      <span className="relative flex h-2 w-2">
        <span
          className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
            isProduction ? 'bg-emerald-400' : 'bg-yellow-400'
          }`}
        />
        <span
          className={`relative inline-flex rounded-full h-2 w-2 ${
            isProduction ? 'bg-emerald-400' : 'bg-yellow-400'
          }`}
        />
      </span>
      <span className="font-mono font-medium">
        TEE: {health.tee_mode}
      </span>
    </div>
  )
}

function ViewDealForm() {
  const [dealId, setDealId] = useState('')
  const navigate = useNavigate()

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = dealId.trim()
    if (!trimmed) return
    navigate(`/deal/${trimmed}`)
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={dealId}
        onChange={(e) => setDealId(e.target.value)}
        placeholder="Deal UUID..."
        className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all"
      />
      <button
        type="submit"
        disabled={!dealId.trim()}
        className="px-4 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-sm font-medium transition-all border border-gray-600/40 hover:border-gray-500/60 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        View
      </button>
    </form>
  )
}

export default function Home() {
  const [health, setHealth] = useState(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false

    async function fetchHealth() {
      try {
        setHealthLoading(true)
        setHealthError(false)
        const data = await getHealth()
        if (!cancelled) {
          setHealth(data)
          setHealthLoading(false)
        }
      } catch {
        if (!cancelled) {
          setHealthError(true)
          setHealthLoading(false)
        }
      }
    }

    fetchHealth()
    const interval = setInterval(fetchHealth, 10000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">
      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 sm:py-24">
        <div className="w-full max-w-3xl mx-auto text-center">

          {/* Health badge */}
          <div className="flex justify-center mb-8">
            <HealthIndicator health={health} loading={healthLoading} error={healthError} />
          </div>

          {/* Logo mark */}
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-2xl shadow-indigo-900/60">
              <svg
                className="w-8 h-8 sm:w-10 sm:h-10 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
            </div>
          </div>

          {/* Title */}
          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold text-white mb-4 tracking-tight">
            DealProof
          </h1>

          {/* Subtitle */}
          <p className="text-base sm:text-lg text-gray-400 font-medium mb-6">
            Verifiable AI Negotiation &nbsp;·&nbsp; TEE-Attested &nbsp;·&nbsp; On-chain Escrow
          </p>

          {/* Description */}
          <p className="text-sm sm:text-base text-gray-500 max-w-xl mx-auto leading-relaxed mb-12">
            Two AI agents negotiate data access terms inside an Intel TDX Trusted Execution Environment.
            Every deal is cryptographically signed by the TEE — tamper-proof, transparent, and auditable.
            Optional DKIM email verification and on-chain escrow via Ethereum smart contracts.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-4 items-center justify-center mb-12">
            <Link
              to="/create"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Start a Deal
            </Link>

            <div className="w-full sm:w-72">
              <ViewDealForm />
            </div>
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mb-16">
            {[
              { icon: '🔒', label: 'Intel TDX Enclave' },
              { icon: '🤖', label: 'LLM Negotiation' },
              { icon: '✉️', label: 'DKIM Identity Proof' },
              { icon: '⛓️', label: 'On-chain Escrow' },
              { icon: '📜', label: 'DCAP Attestation' },
            ].map((f) => (
              <span
                key={f.label}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-800/60 border border-gray-700/40 text-gray-400 text-xs font-medium"
              >
                <span>{f.icon}</span>
                {f.label}
              </span>
            ))}
          </div>

          {/* How it works */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-16 text-left">
            {[
              {
                step: '01',
                title: 'Submit Deal Parameters',
                desc: 'Define budget, requirements, data description and floor price. Optionally attach email proof for seller identity verification.',
              },
              {
                step: '02',
                title: 'Agents Negotiate in TEE',
                desc: 'Buyer and seller AI agents exchange offers inside an Intel TDX enclave. Every message is private and tamper-proof.',
              },
              {
                step: '03',
                title: 'Cryptographic Attestation',
                desc: 'The agreed terms are hashed and signed by the TEE. The DCAP quote can be verified on-chain or by any third party.',
              },
            ].map((item) => (
              <div
                key={item.step}
                className="p-4 rounded-xl bg-gray-900/40 border border-gray-800/40"
              >
                <div className="text-xs font-mono text-indigo-500 mb-2">{item.step}</div>
                <h3 className="text-sm font-semibold text-gray-200 mb-1.5">{item.title}</h3>
                <p className="text-xs text-gray-500 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-800/60 px-4 py-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-xs text-gray-600">
            DealProof &copy; {new Date().getFullYear()} — MIT License
          </span>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
              </svg>
              GitHub
            </a>
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              API Docs
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
