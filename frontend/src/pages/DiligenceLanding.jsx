import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ingestDiligence, evaluateDiligence } from '../api.js'

// ---------------------------------------------------------------------------
// Embedded demo payloads (no JSON pasting required)
// ---------------------------------------------------------------------------

const DEMO_SCENARIOS = {
  clean: {
    label: 'Healthy Series A',
    tag: 'All metrics favorable',
    tagColor: 'emerald',
    description: 'Six metrics verified across revenue growth, margin, runway, concentration, churn, and ARR. A textbook clean round.',
    pill: '✓ Clean',
    company_name: 'Acme Software Inc',
    round_label: 'Series A',
    metrics_records: [
      {
        source: 'monthly_revenue', format: 'revenue_timeseries_json',
        content: { months: [
          { month: '2025-10', revenue: 78000, cogs: 19000 },
          { month: '2025-11', revenue: 84000, cogs: 20500 },
          { month: '2025-12', revenue: 92000, cogs: 22000 },
        ]},
      },
      {
        source: 'customer_revenue_breakdown', format: 'customer_breakdown_json',
        content: { customers: [
          { customer_id: 'cust_001', revenue: 11000 },
          { customer_id: 'cust_002', revenue: 9500 },
          { customer_id: 'cust_003', revenue: 8000 },
          { customer_id: 'cust_004', revenue: 7000 },
          { customer_id: 'cust_005', revenue: 6500 },
          { customer_id: 'cust_006', revenue: 5000 },
        ]},
      },
      { source: 'expenses_and_cash', format: 'expense_cash_json', content: { monthly_burn: 85000, cash_balance: 1200000 } },
      { source: 'cohort_retention', format: 'cohort_json', content: { cohorts: [{ cohort_month: '2025-09', starting_customers: 40, active_after_3mo: 37 }] } },
      { source: 'reported_arr', format: 'arr_claim_json', content: { reported_arr: 1100000 } },
    ],
  },
  scae: {
    label: 'SCAE: ARR Inflation',
    tag: 'Fraud detection demo',
    tagColor: 'amber',
    description: 'Founder reports $1.5M ARR. Subscription records compute $960k. The TEE catches the 56% discrepancy — no human review required.',
    pill: '⚠ SCAE',
    company_name: 'ARRInfl Corp',
    round_label: 'Series B',
    metrics_records: [
      {
        source: 'monthly_revenue', format: 'revenue_timeseries_json',
        content: { months: [
          { month: '2025-10', revenue: 72000, cogs: 17000 },
          { month: '2025-11', revenue: 76000, cogs: 18000 },
          { month: '2025-12', revenue: 80000, cogs: 19000 },
        ]},
      },
      {
        source: 'customer_revenue_breakdown', format: 'customer_breakdown_json',
        content: { customers: [
          { customer_id: 'cust_001', revenue: 25000 },
          { customer_id: 'cust_002', revenue: 20000 },
          { customer_id: 'cust_003', revenue: 18000 },
        ]},
      },
      { source: 'expenses_and_cash', format: 'expense_cash_json', content: { monthly_burn: 90000, cash_balance: 1350000 } },
      { source: 'cohort_retention', format: 'cohort_json', content: { cohorts: [{ cohort_month: '2025-09', starting_customers: 60, active_after_3mo: 57 }] } },
      { source: 'reported_arr', format: 'arr_claim_json', content: { reported_arr: 1500000 } },
    ],
  },
}

// ---------------------------------------------------------------------------
// Demo card
// ---------------------------------------------------------------------------

const TAG_STYLES = {
  emerald: {
    card: 'border-emerald-800/30 hover:border-emerald-700/50',
    tag: 'bg-emerald-950/50 text-emerald-300 border-emerald-800/50',
    pill: 'bg-emerald-950/40 text-emerald-400 border-emerald-800/40',
    btn: 'bg-emerald-700 hover:bg-emerald-600 shadow-emerald-900/40',
  },
  amber: {
    card: 'border-amber-800/30 hover:border-amber-700/50',
    tag: 'bg-amber-950/50 text-amber-300 border-amber-800/50',
    pill: 'bg-amber-950/40 text-amber-400 border-amber-800/40',
    btn: 'bg-amber-700 hover:bg-amber-600 shadow-amber-900/40',
  },
}

function DemoCard({ scenarioKey, scenario, onRun, running }) {
  const s = TAG_STYLES[scenario.tagColor]
  const isRunning = running === scenarioKey

  return (
    <div className={`rounded-xl border bg-gray-900/40 p-6 flex flex-col gap-4 transition-all ${s.card} ${isRunning ? 'ring-1 ring-indigo-500/30' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className={`text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border ${s.tag}`}>
            {scenario.tag}
          </span>
          <h3 className="text-lg font-bold text-gray-100 mt-2">{scenario.label}</h3>
        </div>
        <span className={`text-xs font-mono px-2 py-1 rounded border flex-shrink-0 ${s.pill}`}>
          {scenario.pill}
        </span>
      </div>

      <p className="text-sm text-gray-400 leading-relaxed flex-1">{scenario.description}</p>

      <div className="space-y-1.5 text-xs font-mono text-gray-600">
        <div>{scenario.company_name} · {scenario.round_label}</div>
        <div>{scenario.metrics_records.length} metric sources · TEE-attested</div>
      </div>

      <button
        onClick={() => onRun(scenarioKey, scenario)}
        disabled={!!running}
        className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-white font-semibold text-sm transition-all shadow-lg disabled:opacity-60 disabled:cursor-not-allowed ${s.btn}`}
      >
        {isRunning ? (
          <>
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            <span>Running inside TEE…</span>
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Run demo
          </>
        )}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Static trust stack illustration
// ---------------------------------------------------------------------------

function TrustStackIllustration() {
  const layers = [
    { label: 'TDX ENCLAVE', sub: 'Intel hardware root of trust', color: 'indigo' },
    { label: 'DCAP ATTESTATION', sub: 'Cryptographic code measurement', color: 'indigo' },
    { label: 'METRICS CORPUS', sub: 'Merkle root over financial records', color: 'indigo' },
    { label: 'DILIGENCE CREDENTIAL', sub: 'Attested metric findings + hash', color: 'indigo' },
  ]

  return (
    <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-800/40 bg-gray-900/50">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Trust Stack</p>
      </div>
      <div className="divide-y divide-gray-800/30">
        {layers.map(({ label, sub }, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3">
            <div className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-mono text-gray-300">{label}</p>
              <p className="text-[10px] text-gray-600 mt-0.5">{sub}</p>
            </div>
            <span className="text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border bg-emerald-950/40 text-emerald-400 border-emerald-800/40 flex-shrink-0">
              ACTIVE
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main landing page
// ---------------------------------------------------------------------------

export default function DiligenceLanding() {
  const navigate = useNavigate()
  const [running, setRunning] = useState(null)
  const [runError, setRunError] = useState(null)

  async function handleRun(key, scenario) {
    setRunning(key)
    setRunError(null)
    try {
      const ingest = await ingestDiligence({
        company_name: scenario.company_name,
        round_label: scenario.round_label,
        metrics_records: scenario.metrics_records,
      })
      const result = await evaluateDiligence(ingest.diligence_id, {})
      navigate(`/fundraising/diligence/${ingest.diligence_id}`, { state: { result } })
    } catch (err) {
      setRunError(err.message || 'Demo failed — is the backend running?')
      setRunning(null)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex flex-col">

      {/* Hero */}
      <div className="flex flex-col items-center justify-center px-4 py-16 sm:py-20 text-center">
        <div className="max-w-2xl mx-auto">

          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-950/50 border border-indigo-800/50 text-indigo-300 text-xs font-medium mb-6">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-indigo-400" />
            </span>
            Powered by Intel TDX · Phala Cloud
          </div>

          <h1 className="text-4xl sm:text-5xl font-bold text-white mb-4 tracking-tight leading-tight">
            Verifiable fundraising<br />due diligence
          </h1>

          <p className="text-base sm:text-lg text-gray-400 mb-4 leading-relaxed">
            Founders prove their metrics. Investors verify them.
            Nobody hands over a spreadsheet.
          </p>

          <p className="text-sm text-gray-500 max-w-lg mx-auto mb-10 leading-relaxed">
            Financial metrics are computed inside an Intel TDX enclave and signed with a
            hardware attestation. Investors receive a cryptographic credential — not a
            spreadsheet they have to trust.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/fundraising/new"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-900/40 hover:-translate-y-0.5"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Enter your own metrics
            </Link>
            <a
              href="#demos"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl border border-gray-700/60 text-gray-300 hover:text-white hover:border-gray-600 font-medium text-sm transition-all"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
              See a live demo
            </a>
          </div>
        </div>
      </div>

      {/* SCAE callout */}
      <div className="px-4 pb-12">
        <div className="max-w-3xl mx-auto">
          <div className="rounded-xl border border-amber-800/30 bg-amber-950/10 px-6 py-5 flex gap-4">
            <div className="w-8 h-8 rounded-lg bg-amber-950/50 border border-amber-800/50 flex items-center justify-center flex-shrink-0 mt-0.5">
              <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold text-amber-300 mb-1">SCAE resistance — the math is the trust</p>
              <p className="text-sm text-gray-400 leading-relaxed">
                If a founder's ARR claim doesn't match what their subscription records actually support,
                the enclave catches it before the investor ever has to find out the hard way.
                The deterministic inspector recomputes every metric from raw records — it never reads the claim.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* One-click demos */}
      <div id="demos" className="px-4 pb-16">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-8">
            <h2 className="text-xl font-bold text-gray-100 mb-2">Live demos</h2>
            <p className="text-sm text-gray-500">
              One click — real pipeline, real TEE attestation, real results.
            </p>
          </div>

          {runError && (
            <div className="mb-6 flex items-start gap-3 px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="font-medium">Demo failed</p>
                <p className="text-red-400/80 text-xs mt-0.5">{runError}</p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {Object.entries(DEMO_SCENARIOS).map(([key, scenario]) => (
              <DemoCard
                key={key}
                scenarioKey={key}
                scenario={scenario}
                onRun={handleRun}
                running={running}
              />
            ))}
          </div>
        </div>
      </div>

      {/* How it works */}
      <div className="px-4 pb-16 border-t border-gray-800/40 pt-14">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-xl font-bold text-gray-100 mb-8 text-center">How it works</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              {
                step: '01',
                title: 'Upload financial records',
                desc: 'Monthly revenue, customer breakdown, burn rate, retention cohorts, and reported ARR are submitted to the TEE. Raw figures never leave the enclave.',
              },
              {
                step: '02',
                title: 'Enclave computes and verifies',
                desc: 'Six metrics are deterministically computed from source records and cross-checked against claimed values. If a claim doesn\'t match the data, it\'s flagged.',
              },
              {
                step: '03',
                title: 'Credential issued and attested',
                desc: 'A diligence credential is hashed and signed by the Intel TDX enclave. Investors receive verified rates and ratios — not the underlying spreadsheet.',
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

      {/* Trust stack + bottom CTA */}
      <div className="px-4 pb-16">
        <div className="max-w-3xl mx-auto grid grid-cols-1 sm:grid-cols-2 gap-6 items-start">
          <TrustStackIllustration />
          <div className="flex flex-col gap-4 justify-center py-2">
            <h3 className="text-lg font-bold text-gray-100">Bring your own metrics</h3>
            <p className="text-sm text-gray-400 leading-relaxed">
              Paste your company's financial records as JSON — monthly revenue, customer breakdown,
              burn rate, retention, and ARR. The enclave computes and attests your results in seconds.
            </p>
            <Link
              to="/fundraising/new"
              className="self-start inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-900/40 hover:-translate-y-0.5"
            >
              Start diligence
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </Link>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-800/60 px-4 py-6 mt-auto">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-xs text-gray-600">Fundraising Credential</span>
        </div>
      </footer>
    </div>
  )
}
