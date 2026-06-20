import React, { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { runFundraisingNegotiation } from '../api.js'

// ---------------------------------------------------------------------------
// Field definitions
// ---------------------------------------------------------------------------

const INVESTOR_FIELDS = [
  {
    key: 'investor_id',
    label: 'Investor ID',
    type: 'text',
    placeholder: 'e.g. sequoia-fund-iv',
    hint: 'Opaque identifier — no PII required.',
    scale: null,
  },
  {
    key: 'investor_max_valuation',
    label: 'Max Pre-money Valuation',
    unit: '$M',
    type: 'number',
    placeholder: '12',
    hint: 'Hard cap — InvestorAgent will never offer above this.',
    scale: 1_000_000,
  },
  {
    key: 'investor_investment_amount',
    label: 'Investment Amount',
    unit: '$M',
    type: 'number',
    placeholder: '2',
    hint: 'Capital to deploy in this round.',
    scale: 1_000_000,
  },
  {
    key: 'investor_target_ownership_pct',
    label: 'Target Ownership',
    unit: '%',
    type: 'number',
    placeholder: '15',
    hint: 'Desired equity stake.',
    scale: null,
  },
  {
    key: 'investor_requirements',
    label: 'Investment Thesis',
    type: 'textarea',
    placeholder: 'Strong metrics, experienced team, large market.',
    hint: 'Optional — injected into InvestorAgent system prompt.',
    scale: null,
  },
]

const FOUNDER_FIELDS = [
  {
    key: 'founder_valuation_ask',
    label: 'Opening Valuation Ask',
    unit: '$M',
    type: 'number',
    placeholder: '15',
    hint: 'FounderAgent opens at this pre-money valuation.',
    scale: 1_000_000,
  },
  {
    key: 'founder_floor_valuation',
    label: 'Floor Valuation',
    unit: '$M',
    type: 'number',
    placeholder: '8',
    hint: 'Hard minimum — FounderAgent will never accept below this.',
    scale: 1_000_000,
  },
]

const ROUND_FIELD = {
  key: 'max_rounds',
  label: 'Max Rounds',
  type: 'number',
  placeholder: '8',
  hint: 'Maximum back-and-forth rounds before deadlock.',
  scale: null,
}

// ---------------------------------------------------------------------------
// Field components
// ---------------------------------------------------------------------------

function FieldRow({ def, value, onChange }) {
  const inputClass =
    'w-full bg-gray-900/60 border border-gray-700/60 rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-colors font-mono'

  return (
    <div>
      <label className="block text-xs font-medium text-gray-400 mb-1.5">
        {def.label}
        {def.unit && <span className="ml-1 text-gray-600">({def.unit})</span>}
      </label>
      {def.type === 'textarea' ? (
        <textarea
          rows={2}
          value={value}
          onChange={(e) => onChange(def.key, e.target.value)}
          placeholder={def.placeholder}
          className={inputClass + ' resize-none'}
        />
      ) : (
        <input
          type={def.type}
          value={value}
          onChange={(e) => onChange(def.key, e.target.value)}
          placeholder={def.placeholder}
          min={def.type === 'number' ? '0' : undefined}
          step={def.type === 'number' ? 'any' : undefined}
          className={inputClass}
        />
      )}
      {def.hint && <p className="text-[10px] text-gray-600 mt-1">{def.hint}</p>}
    </div>
  )
}

function SectionHeader({ label, color = 'indigo' }) {
  const colors = {
    indigo: 'bg-indigo-950/40 border-indigo-800/30 text-indigo-400',
    emerald: 'bg-emerald-950/40 border-emerald-800/30 text-emerald-400',
  }
  return (
    <div className={`px-4 py-2.5 rounded-lg border ${colors[color]} text-xs font-semibold uppercase tracking-wider mb-4`}>
      {label}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main form
// ---------------------------------------------------------------------------

const INITIAL = {
  investor_id: '',
  investor_max_valuation: '',
  investor_investment_amount: '',
  investor_target_ownership_pct: '',
  investor_requirements: '',
  founder_valuation_ask: '',
  founder_floor_valuation: '',
  max_rounds: '8',
}

export default function NegotiationForm() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const diligenceId = searchParams.get('diligence_id') || ''

  const [fields, setFields] = useState(INITIAL)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function handleChange(key, val) {
    setFields((prev) => ({ ...prev, [key]: val }))
  }

  function buildPayload() {
    const num = (k, scale = null) => {
      const v = parseFloat(fields[k])
      if (isNaN(v)) throw new Error(`${k} must be a number`)
      return scale ? v * scale : v
    }

    return {
      diligence_id: diligenceId,
      investor_id: fields.investor_id.trim() || 'anonymous-investor',
      investor_max_valuation: num('investor_max_valuation', 1_000_000),
      investor_investment_amount: num('investor_investment_amount', 1_000_000),
      investor_target_ownership_pct: num('investor_target_ownership_pct'),
      investor_requirements: fields.investor_requirements.trim() || undefined,
      founder_floor_valuation: num('founder_floor_valuation', 1_000_000),
      founder_valuation_ask: num('founder_valuation_ask', 1_000_000),
      max_rounds: parseInt(fields.max_rounds, 10) || 8,
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)

    let payload
    try {
      payload = buildPayload()
    } catch (err) {
      setError(err.message)
      return
    }

    if (payload.founder_floor_valuation >= payload.founder_valuation_ask) {
      setError('Founder floor valuation must be below the opening ask.')
      return
    }
    if (payload.investor_max_valuation < payload.founder_floor_valuation) {
      setError('Investor max valuation is below the founder floor — a deal is impossible.')
      return
    }

    setLoading(true)
    try {
      const result = await runFundraisingNegotiation(payload)
      navigate(`/fundraising/negotiation/${result.negotiation_id}`, { state: { result } })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span className="text-indigo-400">Fundraising</span>
            <span>/</span>
            <span className="text-gray-400 truncate max-w-[220px]">{diligenceId || '…'}</span>
            <span>/</span>
            <span className="text-gray-400">negotiate</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            Run Valuation Negotiation
          </h1>
          <p className="text-sm text-gray-500 leading-relaxed max-w-lg">
            Two AI agents negotiate pre-money valuation inside the TEE.
            The FounderAgent's arguments are grounded in the attested diligence findings.
            A πCreds conduct audit runs post-deal — including SCAE claim consistency checking.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-8">

          {/* Investor section */}
          <div>
            <SectionHeader label="Investor Agent" color="indigo" />
            <div className="space-y-4">
              {INVESTOR_FIELDS.map((def) => (
                <FieldRow key={def.key} def={def} value={fields[def.key]} onChange={handleChange} />
              ))}
            </div>
          </div>

          {/* Founder section */}
          <div>
            <SectionHeader label="Founder Agent" color="emerald" />
            <div className="space-y-4">
              {FOUNDER_FIELDS.map((def) => (
                <FieldRow key={def.key} def={def} value={fields[def.key]} onChange={handleChange} />
              ))}
            </div>
          </div>

          {/* Config section */}
          <div>
            <SectionHeader label="Negotiation Config" color="indigo" />
            <FieldRow def={ROUND_FIELD} value={fields.max_rounds} onChange={handleChange} />
          </div>

          {/* TEE note */}
          <div className="rounded-xl border border-indigo-800/30 bg-indigo-950/10 px-4 py-3 text-xs text-indigo-300 leading-relaxed">
            All negotiation rounds run inside Intel TDX. The final credential includes a TDX quote
            binding the diligence hash + πCreds conduct hash — a verifier can confirm which data
            was used and that neither agent fabricated metrics during negotiation.
          </div>

          {error && (
            <div className="rounded-lg bg-red-950/40 border border-red-800/50 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !diligenceId}
            className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Negotiating inside TEE…</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>Run Negotiation</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
