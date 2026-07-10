import React, { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { createAgentRailDeal, getAgentRailAttestation, getAgentRailDeal } from '../../api.js'
import StatusBadge from '../../components/StatusBadge.jsx'

const DEFAULT_BUYER = {
  product: 'industrial sensors',
  quantity: 500,
  budget_ceiling: 45,
  min_spec: 'IP67 rating, 12-month warranty',
  urgency: 'moderate — can wait 2 weeks for delivery',
}

const DEFAULT_SUPPLIER = {
  product: 'industrial sensors',
  floor_price_bulk: 38,
  floor_price_standard: 42,
  bulk_threshold: 200,
  available_inventory: 800,
  lead_time_days: 5,
}

const POLL_INTERVAL_MS = 1200

function inputClass(extra = '') {
  return `w-full px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition-all ${extra}`.trim()
}

function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-gray-400">{label}</span>
      {children}
    </label>
  )
}

function SealedPanel({ title, accent, icon, children }) {
  return (
    <div className={`rounded-xl border ${accent.border} ${accent.bg} overflow-hidden`}>
      <div className={`px-4 py-3 border-b ${accent.border} flex items-center gap-2`}>
        <svg className={`w-4 h-4 ${accent.text}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={icon} />
        </svg>
        <span className={`text-sm font-semibold ${accent.text}`}>{title}</span>
        <span className="ml-auto text-[10px] uppercase tracking-widest text-gray-500 font-mono">Sealed</span>
      </div>
      <div className="px-4 py-4 space-y-3">{children}</div>
    </div>
  )
}

const LOCK_ICON = 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z'

const BUYER_ACCENT = { border: 'border-amber-800/40', bg: 'bg-amber-950/10', text: 'text-amber-400' }
const SUPPLIER_ACCENT = { border: 'border-cyan-800/40', bg: 'bg-cyan-950/10', text: 'text-cyan-400' }

function RoundBubble({ round }) {
  const isBuyer = round.role === 'buyer'
  const accent = isBuyer ? BUYER_ACCENT : SUPPLIER_ACCENT
  const action = (round.action || '').toUpperCase()
  const actionColor =
    action === 'ACCEPT' ? 'text-emerald-400 border-emerald-700/50 bg-emerald-950/40' :
    action === 'REJECT' ? 'text-red-400 border-red-700/50 bg-red-950/40' :
    `${accent.text} ${accent.border} ${accent.bg}`

  return (
    <div className={`flex ${isBuyer ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[88%] sm:max-w-[70%] rounded-2xl px-4 py-3 border shadow-lg ${accent.border} ${accent.bg} ${isBuyer ? 'rounded-tl-sm' : 'rounded-tr-sm'}`}>
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <span className={`text-xs font-semibold uppercase tracking-widest ${accent.text}`}>
            {round.role}
          </span>
          <span className="text-gray-600 text-xs">·</span>
          <span className="text-gray-500 text-xs font-mono">Round {round.round}</span>
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${actionColor}`}>{action}</span>
        </div>
        <div className="text-xl font-bold font-mono text-gray-100 mb-1">
          ${Number(round.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/u
          <span className="text-sm text-gray-500 font-normal ml-2">× {round.quantity}</span>
        </div>
        {round.reasoning && (
          <p className="text-sm text-gray-300 leading-relaxed italic">&ldquo;{round.reasoning}&rdquo;</p>
        )}
      </div>
    </div>
  )
}

function AttestationReceipt({ attest }) {
  if (!attest) return null
  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <span className="text-sm font-semibold text-gray-200">DCAP Attestation Receipt</span>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${
            attest.valid
              ? 'bg-emerald-900/40 text-emerald-300 border-emerald-700/50'
              : 'bg-red-900/40 text-red-300 border-red-700/50'
          }`}
        >
          {attest.valid ? 'Verifiable' : 'Malformed'}
        </span>
      </div>
      <div className="px-4 py-3 space-y-2">
        <code className="block text-xs font-mono text-gray-300 bg-gray-950/60 rounded-lg px-3 py-2 border border-gray-800/60 break-all leading-relaxed">
          {attest.attestation}
        </code>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 font-mono">
          <span>mode={attest.mode}</span>
          <span>{attest.byte_length} bytes</span>
          {attest.mrenclave && <span>mrenclave={attest.mrenclave.slice(0, 16)}…</span>}
        </div>
      </div>
    </div>
  )
}

export default function AgentRailDemo() {
  const [searchParams] = useSearchParams()
  // Read once from the URL and keep in component memory only — never localStorage,
  // per the magic-link design: these links are short-lived and single-use.
  const [demoToken] = useState(() => searchParams.get('token') || '')

  const [stage, setStage] = useState('setup') // setup | negotiating | result
  const [buyer, setBuyer] = useState(DEFAULT_BUYER)
  const [supplier, setSupplier] = useState(DEFAULT_SUPPLIER)
  const [maxRounds, setMaxRounds] = useState(5)
  const [dealId, setDealId] = useState(null)
  const [deal, setDeal] = useState(null)
  const [attest, setAttest] = useState(null)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const timeoutRef = useRef(null)

  function setBuyerField(key, value) {
    setBuyer((prev) => ({ ...prev, [key]: value }))
  }

  function setSupplierField(key, value) {
    setSupplier((prev) => ({ ...prev, [key]: value }))
  }

  async function handleStart(e) {
    e.preventDefault()
    setError(null)
    setStarting(true)
    try {
      const body = {
        buyer: {
          ...buyer,
          quantity: Number(buyer.quantity),
          budget_ceiling: Number(buyer.budget_ceiling),
        },
        supplier: {
          ...supplier,
          floor_price_bulk: Number(supplier.floor_price_bulk),
          floor_price_standard: Number(supplier.floor_price_standard),
          bulk_threshold: Number(supplier.bulk_threshold),
          available_inventory: Number(supplier.available_inventory),
          lead_time_days: Number(supplier.lead_time_days),
        },
        max_rounds: Number(maxRounds),
      }
      const res = await createAgentRailDeal(body, demoToken)
      setDealId(res.deal_id)
      setDeal(null)
      setAttest(null)
      setStage('negotiating')
    } catch (err) {
      setError(err.message || 'Failed to start negotiation. Is the backend running?')
    } finally {
      setStarting(false)
    }
  }

  useEffect(() => {
    if (stage !== 'negotiating' || !dealId) return
    let cancelled = false

    async function poll() {
      try {
        const res = await getAgentRailDeal(dealId)
        if (cancelled) return
        setDeal(res)

        if (res.status !== 'negotiating') {
          if (res.status === 'agreed') {
            try {
              const a = await getAgentRailAttestation(dealId)
              if (!cancelled) setAttest(a)
            } catch {
              // attestation fetch failing shouldn't block showing the result
            }
          }
          if (!cancelled) setStage('result')
          return
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Lost connection to backend while negotiating.')
          setStage('result')
        }
        return
      }
      if (!cancelled) timeoutRef.current = setTimeout(poll, POLL_INTERVAL_MS)
    }

    poll()
    return () => {
      cancelled = true
      clearTimeout(timeoutRef.current)
    }
  }, [stage, dealId])

  function handleReset() {
    setStage('setup')
    setDealId(null)
    setDeal(null)
    setAttest(null)
    setError(null)
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span>dealproof</span>
            <span>/</span>
            <span className="text-gray-400">agent-rail</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            B2B Agent × Agent Deal Room
          </h1>
          <p className="text-sm text-gray-500 max-w-xl">
            Two Claude agents negotiate on your behalf inside an Intel TDX enclave. Each side's
            private parameters are sealed — the opposing agent and the platform operator never
            see them. Only the attested outcome exits.
          </p>
        </div>

        {stage === 'setup' && !demoToken && (
          <div className="px-5 py-5 rounded-xl bg-gray-900/40 border border-gray-800/60">
            <p className="text-sm font-semibold text-gray-200 mb-1">Demo access required</p>
            <p className="text-sm text-gray-500">
              This demo needs a magic link. Request one from the DealProof team, or use the
              link you were sent — it should end in <code className="text-gray-400">?token=...</code>.
            </p>
          </div>
        )}

        {stage === 'setup' && demoToken && (
          <form onSubmit={handleStart} className="space-y-6">
            <div className="grid md:grid-cols-2 gap-5">
              <SealedPanel title="Buyer" accent={BUYER_ACCENT} icon={LOCK_ICON}>
                <Field label="Product">
                  <input className={inputClass()} value={buyer.product} disabled={starting}
                    onChange={(e) => setBuyerField('product', e.target.value)} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Quantity">
                    <input type="number" min="1" className={inputClass()} value={buyer.quantity} disabled={starting}
                      onChange={(e) => setBuyerField('quantity', e.target.value)} />
                  </Field>
                  <Field label="Budget ceiling ($/unit)">
                    <input type="number" min="0" step="0.01" className={inputClass()} value={buyer.budget_ceiling} disabled={starting}
                      onChange={(e) => setBuyerField('budget_ceiling', e.target.value)} />
                  </Field>
                </div>
                <Field label="Minimum spec">
                  <input className={inputClass()} value={buyer.min_spec} disabled={starting}
                    onChange={(e) => setBuyerField('min_spec', e.target.value)} />
                </Field>
                <Field label="Urgency">
                  <input className={inputClass()} value={buyer.urgency} disabled={starting}
                    onChange={(e) => setBuyerField('urgency', e.target.value)} />
                </Field>
              </SealedPanel>

              <SealedPanel title="Supplier" accent={SUPPLIER_ACCENT} icon={LOCK_ICON}>
                <Field label="Product">
                  <input className={inputClass()} value={supplier.product} disabled={starting}
                    onChange={(e) => setSupplierField('product', e.target.value)} />
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Floor, bulk ($/unit)">
                    <input type="number" min="0" step="0.01" className={inputClass()} value={supplier.floor_price_bulk} disabled={starting}
                      onChange={(e) => setSupplierField('floor_price_bulk', e.target.value)} />
                  </Field>
                  <Field label="Floor, standard ($/unit)">
                    <input type="number" min="0" step="0.01" className={inputClass()} value={supplier.floor_price_standard} disabled={starting}
                      onChange={(e) => setSupplierField('floor_price_standard', e.target.value)} />
                  </Field>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Bulk threshold (units)">
                    <input type="number" min="1" className={inputClass()} value={supplier.bulk_threshold} disabled={starting}
                      onChange={(e) => setSupplierField('bulk_threshold', e.target.value)} />
                  </Field>
                  <Field label="Inventory (units)">
                    <input type="number" min="1" className={inputClass()} value={supplier.available_inventory} disabled={starting}
                      onChange={(e) => setSupplierField('available_inventory', e.target.value)} />
                  </Field>
                </div>
                <Field label="Lead time (business days)">
                  <input type="number" min="1" className={inputClass()} value={supplier.lead_time_days} disabled={starting}
                    onChange={(e) => setSupplierField('lead_time_days', e.target.value)} />
                </Field>
              </SealedPanel>
            </div>

            <div className="flex items-center gap-4 flex-wrap">
              <Field label="Max rounds">
                <select className={inputClass('w-24')} value={maxRounds} disabled={starting}
                  onChange={(e) => setMaxRounds(e.target.value)}>
                  {[3, 5, 7, 10].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </Field>
            </div>

            {error && (
              <div className="px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={starting}
              className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40"
            >
              {starting ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Sealing parameters…
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={LOCK_ICON} />
                  </svg>
                  Seal Parameters &amp; Start Negotiation
                </>
              )}
            </button>
          </form>
        )}

        {stage === 'negotiating' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <StatusBadge status="negotiating" />
              <span className="text-xs text-gray-500 font-mono">
                Round {deal?.transcript?.length ? Math.max(...deal.transcript.map((r) => r.round)) : 0} / {maxRounds}
              </span>
            </div>
            <p className="text-xs text-gray-500">
              Neither agent's sealed parameters are visible to the other or to the platform operator —
              only the proposals below are exchanged.
            </p>
            <div className="space-y-3">
              {(deal?.transcript || []).map((round, idx) => (
                <RoundBubble key={`${round.round}-${round.role}-${idx}`} round={round} />
              ))}
              {(!deal || deal.transcript.length === 0) && (
                <div className="flex items-center justify-center py-12 text-gray-500">
                  <div className="text-center">
                    <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                    <p className="text-sm">Buyer agent is preparing its opening proposal…</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {stage === 'result' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <StatusBadge status={deal?.status || 'failed'} />
              <button
                onClick={handleReset}
                className="text-xs text-gray-400 hover:text-gray-200 font-medium px-3 py-1.5 rounded-lg border border-gray-700/50 hover:border-gray-600 transition-colors"
              >
                Start another negotiation
              </button>
            </div>

            {error && (
              <div className="px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
                {error}
              </div>
            )}

            {deal?.status === 'failed' && deal?.error && (
              <div className="px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
                Negotiation failed: {deal.error}
              </div>
            )}

            {deal?.status === 'agreed' && (
              <>
                <div className="rounded-xl border border-emerald-800/40 bg-emerald-950/10 px-5 py-5">
                  <div className="flex items-center gap-2 text-emerald-400 mb-1">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                    <span className="font-semibold">Deal agreed</span>
                  </div>
                  <div className="text-3xl font-bold font-mono text-gray-100">
                    ${Number(deal.final_price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/unit
                    <span className="text-lg text-gray-400 font-normal ml-2">× {deal.final_quantity} units</span>
                  </div>
                  {deal.terms && Object.keys(deal.terms).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {Object.entries(deal.terms).map(([k, v]) => (
                        <span key={k} className="text-xs px-2 py-0.5 rounded bg-gray-800/60 border border-gray-700/40 text-gray-300 font-mono">
                          {k}: <span className="text-gray-100">{String(v)}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <AttestationReceipt attest={attest} />

                <p className="text-sm text-gray-400 leading-relaxed border-t border-gray-800/60 pt-4">
                  Neither party's private parameters were observable by the platform operator or the
                  opposing agent. This negotiation ran inside a TDX enclave on Phala Cloud.
                </p>
              </>
            )}

            {deal?.status === 'no_deal' && (
              <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 px-5 py-5 text-gray-300 text-sm">
                No deal reached after {deal.transcript.length} negotiation turns.
              </div>
            )}

            <div className="space-y-3">
              {(deal?.transcript || []).map((round, idx) => (
                <RoundBubble key={`${round.round}-${round.role}-${idx}`} round={round} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
