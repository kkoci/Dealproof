import React from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import TranscriptFeed from '../components/TranscriptFeed.jsx'
import TrustStackBar from '../components/TrustStackBar.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function short(h) {
  if (!h) return '—'
  return `${h.slice(0, 16)}…`
}

function valuation(v) {
  if (v == null) return '—'
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`
  return `$${Number(v).toLocaleString()}`
}

// Fundraising role labels for TranscriptFeed
const FUNDRAISING_ROLE_LABELS = { seller: 'Founder', buyer: 'Investor' }

// ---------------------------------------------------------------------------
// Outcome banner
// ---------------------------------------------------------------------------

function OutcomeBanner({ agreed, finalValuation }) {
  if (agreed) {
    return (
      <div className="rounded-xl border border-emerald-700/40 bg-emerald-950/20 px-6 py-5 flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-emerald-900/60 border border-emerald-700/50 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-emerald-300">Deal Agreed</p>
            <p className="text-xs text-gray-500 mt-0.5">
              Negotiated valuation credential — a verified starting point.
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">Pre-money Valuation</p>
          <p className="text-3xl font-bold font-mono text-emerald-300">{valuation(finalValuation)}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-red-700/40 bg-red-950/20 px-6 py-5 flex items-center gap-3">
      <div className="w-10 h-10 rounded-full bg-red-900/60 border border-red-700/50 flex items-center justify-center flex-shrink-0">
        <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </div>
      <div>
        <p className="text-sm font-semibold text-red-300">No Agreement Reached</p>
        <p className="text-xs text-gray-500 mt-0.5">
          The agents did not converge within the round limit. The TDX quote attests to the failed negotiation.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Conduct audit card
// ---------------------------------------------------------------------------

function ConductAuditCard({ conductAudit, picredsAttested }) {
  if (!picredsAttested || !conductAudit) {
    return (
      <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 px-4 py-4">
        <p className="text-xs text-gray-600 uppercase tracking-wider font-semibold mb-2">πCreds Conduct Audit</p>
        <p className="text-xs text-gray-600">Not available — audit ran post-deal but was skipped or failed.</p>
      </div>
    )
  }

  const checks = [
    { key: 'investor_cap_respected',      label: 'Investor Cap Respected' },
    { key: 'founder_floor_respected',     label: 'Founder Floor Respected' },
    { key: 'no_sudden_capitulation',      label: 'No Sudden Capitulation' },
    { key: 'convergence_pattern_valid',   label: 'Convergence Pattern Valid' },
    { key: 'founder_claim_consistency',   label: 'Founder Claim Consistency (SCAE)' },
    { key: 'genuine_negotiation',         label: 'Genuine Negotiation' },
    { key: 'no_collusion_detected',       label: 'No Collusion Detected' },
  ]

  const quality = conductAudit.metric_argument_quality
  const qualityColors = {
    strong: 'text-emerald-400 border-emerald-800/50 bg-emerald-950/30',
    adequate: 'text-yellow-400 border-yellow-800/50 bg-yellow-950/30',
    weak: 'text-red-400 border-red-800/50 bg-red-950/30',
  }

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          πCreds Conduct Audit
        </h3>
        {quality && (
          <span className={`text-[10px] font-semibold tracking-wider px-2.5 py-1 rounded-full border ${qualityColors[quality] || qualityColors.adequate}`}>
            {quality.toUpperCase()} ARGUMENTS
          </span>
        )}
      </div>

      <div className="divide-y divide-gray-800/30">
        {checks.map(({ key, label }) => {
          const passed = conductAudit[key]
          return (
            <div key={key} className={`px-4 py-2.5 flex items-center justify-between gap-3 ${!passed ? 'bg-red-950/10' : ''}`}>
              <span className="text-sm text-gray-400">{label}</span>
              <span className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border flex-shrink-0 ${passed ? 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50' : 'bg-red-950/50 text-red-300 border-red-800/50'}`}>
                {passed ? 'PASS' : 'FAIL'}
              </span>
            </div>
          )
        })}
      </div>

      {conductAudit.assessment && (
        <div className="px-4 py-3 border-t border-gray-800/40 bg-gray-900/20">
          <p className="text-xs text-gray-500 italic">&ldquo;{conductAudit.assessment}&rdquo;</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Credential card
// ---------------------------------------------------------------------------

function NegotiationCredentialCard({ cred }) {
  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/40">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Negotiation Credential
        </h3>
      </div>
      <div className="px-4 py-4 space-y-3">
        {[
          { label: 'Negotiation ID', value: cred.negotiation_id, mono: true, truncate: true },
          { label: 'Diligence ID', value: cred.diligence_id, mono: true, truncate: true },
          { label: 'Investor ID', value: cred.investor_id, mono: false },
          { label: 'Rounds', value: `${cred.round_count} round${cred.round_count !== 1 ? 's' : ''}`, mono: false },
          { label: 'Credential Hash', value: cred.credential_hash, mono: true, highlight: true },
          { label: 'Diligence Hash (linked)', value: short(cred.diligence_credential_hash), mono: true },
          { label: 'πCreds Hash', value: cred.negotiation_picreds_hash ? short(cred.negotiation_picreds_hash) : '—', mono: true },
          { label: 'TDX Quote', value: short(cred.tee_quote), mono: true },
          { label: 'Issued', value: cred.issued_at, mono: false },
        ].map(({ label, value, mono, highlight, truncate }) => (
          <div key={label}>
            <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-0.5">{label}</p>
            <p className={`text-xs ${mono ? 'font-mono' : ''} ${highlight ? 'text-indigo-400 break-all' : truncate ? 'text-gray-500 truncate' : 'text-gray-300'}`}>
              {value}
            </p>
          </div>
        ))}

        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(cred, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `negotiation-${cred.negotiation_id?.slice(0, 8)}.json`
            a.click()
            URL.revokeObjectURL(url)
          }}
          className="w-full mt-2 px-3 py-2 rounded-lg border border-gray-700/60 text-xs text-gray-400 hover:text-gray-200 hover:border-gray-600 hover:bg-gray-800/30 transition-all flex items-center justify-center gap-2"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download credential JSON
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function NegotiationResultView() {
  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()

  const cred = location.state?.result

  if (!cred) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
        <div className="max-w-md text-center space-y-4">
          <p className="text-gray-300">Negotiation credential not found in session.</p>
          <p className="text-sm text-gray-600">Negotiation ID: <span className="font-mono">{id}</span></p>
          <button
            onClick={() => navigate('/fundraising')}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm transition-colors"
          >
            Back to Fundraising
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span className="text-indigo-400">Fundraising</span>
            <span>/</span>
            <span className="text-gray-400 truncate max-w-[180px]">{cred.diligence_id}</span>
            <span>/</span>
            <span className="text-gray-400">negotiation</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-1">
            Negotiated Valuation Credential
          </h1>
          <p className="text-sm text-gray-500">
            A verified starting point — both agents ran inside the TEE, attested by Intel TDX.
          </p>
        </div>

        {/* Outcome banner */}
        <div className="mb-8">
          <OutcomeBanner agreed={cred.agreed} finalValuation={cred.final_valuation} />
        </div>

        {/* Three-panel layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          {/* Left — conduct audit */}
          <div className="lg:col-span-1">
            <ConductAuditCard conductAudit={cred.conduct_audit} picredsAttested={cred.picreds_attested} />
          </div>

          {/* Center — trust stack */}
          <div className="lg:col-span-1">
            <TrustStackBar
              corpusRoot={cred.diligence_credential_hash}
              credentialHash={cred.credential_hash}
              teeQuote={cred.tee_quote}
            />
          </div>

          {/* Right — credential card */}
          <div className="lg:col-span-1">
            <NegotiationCredentialCard cred={cred} />
          </div>
        </div>

        {/* Transcript */}
        {cred.transcript && cred.transcript.length > 0 && (
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 px-6 py-6">
            <TranscriptFeed
              transcript={cred.transcript}
              roleLabels={FUNDRAISING_ROLE_LABELS}
            />
          </div>
        )}

      </div>
    </div>
  )
}
