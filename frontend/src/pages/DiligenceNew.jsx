import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestDiligence, evaluateDiligence } from '../api.js'

// ---------------------------------------------------------------------------
// Example data (clean_series_a)
// ---------------------------------------------------------------------------

const EXAMPLE = {
  companyName: 'Acme Software Inc',
  roundLabel: 'Series A',
  revenueRows: [
    { month: '2025-10', revenue: '78000', cogs: '19000' },
    { month: '2025-11', revenue: '84000', cogs: '20500' },
    { month: '2025-12', revenue: '92000', cogs: '22000' },
  ],
  customerRows: [
    { id: 'cust_001', revenue: '11000' },
    { id: 'cust_002', revenue: '9500' },
    { id: 'cust_003', revenue: '8000' },
    { id: 'cust_004', revenue: '7000' },
    { id: 'cust_005', revenue: '6500' },
    { id: 'cust_006', revenue: '5000' },
  ],
  burn: '85000',
  cash: '1200000',
  cohortRows: [{ month: '2025-09', starting: '40', active: '37' }],
  reportedArr: '1100000',
}

// ---------------------------------------------------------------------------
// Live computation helpers (mirror Python inspector logic)
// ---------------------------------------------------------------------------

function computeMomGrowth(rows) {
  const valid = rows.filter(r => r.month && r.revenue).sort((a, b) => a.month.localeCompare(b.month))
  if (valid.length < 2) return null
  const revs = valid.map(r => Number(r.revenue))
  const rates = []
  for (let i = 1; i < revs.length; i++) {
    if (revs[i - 1] > 0) rates.push((revs[i] - revs[i - 1]) / revs[i - 1])
  }
  return rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null
}

function computeGrossMargin(rows) {
  const valid = rows.filter(r => r.revenue)
  const rev = valid.reduce((s, r) => s + Number(r.revenue), 0)
  const cogs = valid.reduce((s, r) => s + (Number(r.cogs) || 0), 0)
  return rev > 0 ? (rev - cogs) / rev : null
}

function computeTopCustomer(rows) {
  const valid = rows.filter(r => r.id && r.revenue)
  if (!valid.length) return null
  const total = valid.reduce((s, r) => s + Number(r.revenue), 0)
  const max = Math.max(...valid.map(r => Number(r.revenue)))
  return total > 0 ? max / total : null
}

function computeRunway(burn, cash) {
  const b = Number(burn), c = Number(cash)
  return b > 0 && c >= 0 ? c / b : null
}

function computeMonthlyChurn(cohorts) {
  const valid = cohorts.filter(r => r.month && r.starting && r.active)
  if (!valid.length) return null
  const churns = valid.map(r => {
    const s = Number(r.starting), a = Number(r.active)
    if (s <= 0) return null
    return 1 - Math.pow(a / s, 1 / 3)
  }).filter(v => v !== null)
  return churns.length ? churns.reduce((a, b) => a + b, 0) / churns.length : null
}

function computeArrDelta(revenueRows, reportedArr) {
  const valid = revenueRows.filter(r => r.month && r.revenue).sort((a, b) => a.month.localeCompare(b.month))
  if (!valid.length || !reportedArr) return null
  const lastRev = Number(valid[valid.length - 1].revenue)
  const computed = lastRev * 12
  const reported = Number(reportedArr)
  return computed > 0 ? { computed, reported, delta: (reported - computed) / computed } : null
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const inputCls = `w-full px-3 py-2 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200
  placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50
  focus:border-indigo-500/50 transition-all disabled:opacity-50`.replace(/\s+/g, ' ').trim()

const errInputCls = inputCls.replace('border-gray-700/60', 'border-red-700/60')

function FieldErr({ msg }) {
  return msg ? (
    <p className="text-xs text-red-400 flex items-center gap-1 mt-1">
      <svg className="w-3 h-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
      </svg>
      {msg}
    </p>
  ) : null
}

function PreviewBadge({ label, value, flagged }) {
  return (
    <div className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs ${flagged ? 'border-amber-800/40 bg-amber-950/20' : 'border-gray-800/40 bg-gray-900/20'}`}>
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono font-medium ${flagged ? 'text-amber-300' : 'text-emerald-300'}`}>{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step indicator
// ---------------------------------------------------------------------------

const STEPS = ['Company', 'Revenue', 'Customers', 'Cash & Burn', 'Retention & ARR']

function StepIndicator({ current }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map((label, i) => {
        const n = i + 1
        const done = n < current
        const active = n === current
        return (
          <React.Fragment key={n}>
            <div className="flex flex-col items-center gap-1 flex-shrink-0">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                done ? 'bg-indigo-600 border-indigo-600 text-white' :
                active ? 'bg-gray-900 border-indigo-500 text-indigo-400' :
                'bg-gray-900 border-gray-700 text-gray-600'
              }`}>
                {done ? (
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                ) : n}
              </div>
              <span className={`text-[10px] font-medium hidden sm:block ${active ? 'text-indigo-400' : done ? 'text-gray-500' : 'text-gray-700'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mx-1 mb-4 ${done ? 'bg-indigo-600' : 'bg-gray-800'}`} />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 1 — Company
// ---------------------------------------------------------------------------

function Step1({ data, onChange, errors }) {
  return (
    <div className="space-y-5">
      <div>
        <label className="text-sm font-medium text-gray-300 mb-1.5 flex items-center gap-1">
          Company Name <span className="text-indigo-400 text-xs">*</span>
        </label>
        <input
          type="text"
          value={data.companyName}
          onChange={e => onChange('companyName', e.target.value)}
          placeholder="Acme Software Inc"
          className={errors.companyName ? errInputCls : inputCls}
        />
        <FieldErr msg={errors.companyName} />
      </div>
      <div>
        <label className="text-sm font-medium text-gray-300 mb-1.5 block">
          Round Label <span className="text-gray-600 text-xs font-normal">(optional)</span>
        </label>
        <input
          type="text"
          value={data.roundLabel}
          onChange={e => onChange('roundLabel', e.target.value)}
          placeholder="Series A"
          className={inputCls}
        />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 2 — Monthly Revenue
// ---------------------------------------------------------------------------

function Step2({ rows, setRows, errors }) {
  const mom = computeMomGrowth(rows)
  const gm = computeGrossMargin(rows)

  function addRow() { setRows(r => [...r, { month: '', revenue: '', cogs: '' }]) }
  function removeRow(i) { setRows(r => r.filter((_, idx) => idx !== i)) }
  function updateRow(i, key, val) { setRows(r => r.map((row, idx) => idx === i ? { ...row, [key]: val } : row)) }

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">Enter at least one month of revenue data. COGS is required for gross margin.</p>

      <div className="rounded-lg border border-gray-800/60 overflow-hidden">
        <div className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-0 bg-gray-900/50 px-3 py-2 border-b border-gray-800/60">
          {['Month', 'Revenue ($)', 'COGS ($)', '', ''].map((h, i) => (
            <span key={i} className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{h}</span>
          ))}
        </div>
        {rows.map((row, i) => (
          <div key={i} className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 px-3 py-2 border-b border-gray-800/30 last:border-b-0 items-center">
            <span className="text-xs text-gray-600 font-mono w-5">{i + 1}</span>
            <input
              type="month"
              value={row.month}
              onChange={e => updateRow(i, 'month', e.target.value)}
              className={`${inputCls} text-xs`}
            />
            <input
              type="number"
              min="0"
              value={row.revenue}
              onChange={e => updateRow(i, 'revenue', e.target.value)}
              placeholder="0"
              className={`${inputCls} text-xs`}
            />
            <input
              type="number"
              min="0"
              value={row.cogs}
              onChange={e => updateRow(i, 'cogs', e.target.value)}
              placeholder="0"
              className={`${inputCls} text-xs`}
            />
            <button onClick={() => removeRow(i)} disabled={rows.length === 1} className="text-gray-700 hover:text-red-400 disabled:opacity-30 transition-colors">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <button onClick={addRow} className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add month
      </button>

      <FieldErr msg={errors.revenueRows} />

      {(mom !== null || gm !== null) && (
        <div className="grid grid-cols-2 gap-2 pt-1">
          {mom !== null && <PreviewBadge label="MoM growth" value={`${(mom * 100).toFixed(1)}%`} flagged={false} />}
          {gm !== null && <PreviewBadge label="Gross margin" value={`${(gm * 100).toFixed(1)}%`} flagged={false} />}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 3 — Customers
// ---------------------------------------------------------------------------

function Step3({ rows, setRows, errors }) {
  const top = computeTopCustomer(rows)
  const flagged = top !== null && top >= 0.30

  function addRow() { setRows(r => [...r, { id: '', revenue: '' }]) }
  function removeRow(i) { setRows(r => r.filter((_, idx) => idx !== i)) }
  function updateRow(i, key, val) { setRows(r => r.map((row, idx) => idx === i ? { ...row, [key]: val } : row)) }

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">Revenue by customer. Customer names / IDs stay inside the TEE — only the concentration ratio appears in the credential.</p>

      <div className="rounded-lg border border-gray-800/60 overflow-hidden">
        <div className="grid grid-cols-[auto_1fr_1fr_auto] gap-0 bg-gray-900/50 px-3 py-2 border-b border-gray-800/60">
          {['', 'Customer ID', 'Revenue ($)', ''].map((h, i) => (
            <span key={i} className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{h}</span>
          ))}
        </div>
        {rows.map((row, i) => (
          <div key={i} className="grid grid-cols-[auto_1fr_1fr_auto] gap-2 px-3 py-2 border-b border-gray-800/30 last:border-b-0 items-center">
            <span className="text-xs text-gray-600 font-mono w-5">{i + 1}</span>
            <input
              type="text"
              value={row.id}
              onChange={e => updateRow(i, 'id', e.target.value)}
              placeholder="cust_001"
              className={`${inputCls} text-xs font-mono`}
            />
            <input
              type="number"
              min="0"
              value={row.revenue}
              onChange={e => updateRow(i, 'revenue', e.target.value)}
              placeholder="0"
              className={`${inputCls} text-xs`}
            />
            <button onClick={() => removeRow(i)} disabled={rows.length === 1} className="text-gray-700 hover:text-red-400 disabled:opacity-30 transition-colors">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <button onClick={addRow} className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        Add customer
      </button>

      <FieldErr msg={errors.customerRows} />

      {top !== null && (
        <div className="space-y-2 pt-1">
          <PreviewBadge label="Top customer share" value={`${(top * 100).toFixed(1)}%`} flagged={flagged} />
          {flagged && (
            <p className="text-xs text-amber-400 flex items-center gap-1">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              Concentration ≥ 30% — inspector will flag this
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 4 — Cash & Burn
// ---------------------------------------------------------------------------

function Step4({ burn, setBurn, cash, setCash, errors }) {
  const runway = computeRunway(burn, cash)
  const runwayColor = runway === null ? '' : runway >= 12 ? 'text-emerald-300' : runway >= 6 ? 'text-amber-300' : 'text-red-300'
  const runwayFlagged = runway !== null && runway < 6

  return (
    <div className="space-y-5">
      <p className="text-xs text-gray-500">Monthly burn rate and current cash balance. Runway is computed automatically.</p>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-sm font-medium text-gray-300 mb-1.5 flex items-center gap-1">
            Monthly Burn <span className="text-indigo-400 text-xs">*</span>
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm pointer-events-none">$</span>
            <input
              type="number" min="0" value={burn}
              onChange={e => setBurn(e.target.value)}
              placeholder="85000"
              className={`${errors.burn ? errInputCls : inputCls} pl-7`}
            />
          </div>
          <FieldErr msg={errors.burn} />
        </div>
        <div>
          <label className="text-sm font-medium text-gray-300 mb-1.5 flex items-center gap-1">
            Cash Balance <span className="text-indigo-400 text-xs">*</span>
          </label>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm pointer-events-none">$</span>
            <input
              type="number" min="0" value={cash}
              onChange={e => setCash(e.target.value)}
              placeholder="1200000"
              className={`${errors.cash ? errInputCls : inputCls} pl-7`}
            />
          </div>
          <FieldErr msg={errors.cash} />
        </div>
      </div>

      {runway !== null && (
        <div className={`flex items-center justify-between px-3 py-3 rounded-lg border text-sm ${runwayFlagged ? 'border-red-800/40 bg-red-950/20' : runway < 12 ? 'border-amber-800/40 bg-amber-950/20' : 'border-emerald-800/40 bg-emerald-950/20'}`}>
          <span className="text-gray-400">Runway</span>
          <div className="flex items-center gap-2">
            <span className={`font-mono font-bold text-base ${runwayColor}`}>{runway.toFixed(1)} months</span>
            {runwayFlagged && <span className="text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border bg-red-950/50 text-red-300 border-red-800/50">WILL FLAG</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Step 5 — Retention & ARR
// ---------------------------------------------------------------------------

function Step5({ cohortRows, setCohortRows, reportedArr, setReportedArr, revenueRows, errors }) {
  const churn = computeMonthlyChurn(cohortRows)
  const arrData = computeArrDelta(revenueRows, reportedArr)
  const churnFlagged = churn !== null && churn > 0.05
  const arrFlagged = arrData !== null && Math.abs(arrData.delta) > 0.10

  function addRow() { setCohortRows(r => [...r, { month: '', starting: '', active: '' }]) }
  function removeRow(i) { setCohortRows(r => r.filter((_, idx) => idx !== i)) }
  function updateRow(i, key, val) { setCohortRows(r => r.map((row, idx) => idx === i ? { ...row, [key]: val } : row)) }

  return (
    <div className="space-y-5">
      <div>
        <label className="text-sm font-medium text-gray-300 mb-2 block">Customer Retention Cohorts</label>
        <p className="text-xs text-gray-500 mb-3">How many customers from each cohort were still active after 3 months?</p>

        <div className="rounded-lg border border-gray-800/60 overflow-hidden">
          <div className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-0 bg-gray-900/50 px-3 py-2 border-b border-gray-800/60">
            {['', 'Cohort Month', 'Starting', 'Active (3mo)', ''].map((h, i) => (
              <span key={i} className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{h}</span>
            ))}
          </div>
          {cohortRows.map((row, i) => (
            <div key={i} className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 px-3 py-2 border-b border-gray-800/30 last:border-b-0 items-center">
              <span className="text-xs text-gray-600 font-mono w-5">{i + 1}</span>
              <input type="month" value={row.month} onChange={e => updateRow(i, 'month', e.target.value)} className={`${inputCls} text-xs`} />
              <input type="number" min="0" value={row.starting} onChange={e => updateRow(i, 'starting', e.target.value)} placeholder="0" className={`${inputCls} text-xs`} />
              <input type="number" min="0" value={row.active} onChange={e => updateRow(i, 'active', e.target.value)} placeholder="0" className={`${inputCls} text-xs`} />
              <button onClick={() => removeRow(i)} disabled={cohortRows.length === 1} className="text-gray-700 hover:text-red-400 disabled:opacity-30 transition-colors">
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          ))}
        </div>
        <button onClick={addRow} className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors mt-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add cohort
        </button>

        {churn !== null && (
          <div className="mt-3">
            <PreviewBadge label="Est. monthly churn" value={`${(churn * 100).toFixed(1)}%`} flagged={churnFlagged} />
            {churnFlagged && <p className="text-xs text-amber-400 mt-1">Monthly churn &gt; 5% — inspector will flag this</p>}
          </div>
        )}
      </div>

      <div>
        <label className="text-sm font-medium text-gray-300 mb-1.5 flex items-center gap-1">
          Reported ARR <span className="text-indigo-400 text-xs">*</span>
        </label>
        <p className="text-xs text-gray-500 mb-2">The ARR figure you report to investors. The TEE will recompute it from your revenue data and flag any discrepancy &gt; 10%.</p>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm pointer-events-none">$</span>
          <input
            type="number" min="0" value={reportedArr}
            onChange={e => setReportedArr(e.target.value)}
            placeholder="1100000"
            className={`${errors.reportedArr ? errInputCls : inputCls} pl-7`}
          />
        </div>
        <FieldErr msg={errors.reportedArr} />

        {arrData && (
          <div className={`mt-3 px-3 py-2.5 rounded-lg border text-xs ${arrFlagged ? 'border-red-800/40 bg-red-950/20' : 'border-emerald-800/40 bg-emerald-950/20'}`}>
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Computed ARR (last month × 12)</span>
              <span className="font-mono text-gray-300">${arrData.computed.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between mt-1">
              <span className="text-gray-500">Reported ARR</span>
              <span className="font-mono text-gray-300">${arrData.reported.toLocaleString()}</span>
            </div>
            <div className="flex items-center justify-between mt-1 pt-1 border-t border-gray-800/40">
              <span className={arrFlagged ? 'text-red-400' : 'text-gray-500'}>Delta</span>
              <span className={`font-mono font-medium ${arrFlagged ? 'text-red-300' : 'text-emerald-300'}`}>
                {arrData.delta >= 0 ? '+' : ''}{(arrData.delta * 100).toFixed(1)}%
                {arrFlagged ? ' — WILL FLAG' : ' — within tolerance'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main wizard
// ---------------------------------------------------------------------------

export default function DiligenceNew() {
  const navigate = useNavigate()

  const [step, setStep] = useState(1)
  const [companyName, setCompanyName] = useState('')
  const [roundLabel, setRoundLabel] = useState('')
  const [revenueRows, setRevenueRows] = useState([{ month: '', revenue: '', cogs: '' }])
  const [customerRows, setCustomerRows] = useState([{ id: '', revenue: '' }])
  const [burn, setBurn] = useState('')
  const [cash, setCash] = useState('')
  const [cohortRows, setCohortRows] = useState([{ month: '', starting: '', active: '' }])
  const [reportedArr, setReportedArr] = useState('')
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [submitPhase, setSubmitPhase] = useState(null)
  const [submitError, setSubmitError] = useState(null)

  function loadExample() {
    setCompanyName(EXAMPLE.companyName)
    setRoundLabel(EXAMPLE.roundLabel)
    setRevenueRows(EXAMPLE.revenueRows)
    setCustomerRows(EXAMPLE.customerRows)
    setBurn(EXAMPLE.burn)
    setCash(EXAMPLE.cash)
    setCohortRows(EXAMPLE.cohortRows)
    setReportedArr(EXAMPLE.reportedArr)
    setErrors({})
  }

  function validateStep() {
    const errs = {}
    if (step === 1) {
      if (!companyName.trim()) errs.companyName = 'Company name is required'
    }
    if (step === 2) {
      const valid = revenueRows.filter(r => r.month && r.revenue)
      if (!valid.length) errs.revenueRows = 'Add at least one complete revenue row'
    }
    if (step === 3) {
      const valid = customerRows.filter(r => r.id && r.revenue)
      if (!valid.length) errs.customerRows = 'Add at least one complete customer row'
    }
    if (step === 4) {
      if (!burn || isNaN(Number(burn)) || Number(burn) <= 0) errs.burn = 'Enter a valid monthly burn'
      if (!cash || isNaN(Number(cash)) || Number(cash) < 0) errs.cash = 'Enter a valid cash balance'
    }
    if (step === 5) {
      if (!reportedArr || isNaN(Number(reportedArr)) || Number(reportedArr) <= 0) errs.reportedArr = 'Enter a valid ARR figure'
    }
    return errs
  }

  function handleNext() {
    const errs = validateStep()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setStep(s => s + 1)
  }

  function buildMetricsRecords() {
    const records = []
    const validRevenue = revenueRows.filter(r => r.month && r.revenue)
    if (validRevenue.length) {
      records.push({
        source: 'monthly_revenue', format: 'revenue_timeseries_json',
        content: { months: validRevenue.map(r => ({ month: r.month, revenue: Number(r.revenue), cogs: Number(r.cogs) || 0 })) },
      })
    }
    const validCustomers = customerRows.filter(r => r.id && r.revenue)
    if (validCustomers.length) {
      records.push({
        source: 'customer_revenue_breakdown', format: 'customer_breakdown_json',
        content: { customers: validCustomers.map(r => ({ customer_id: r.id, revenue: Number(r.revenue) })) },
      })
    }
    if (burn && cash) {
      records.push({
        source: 'expenses_and_cash', format: 'expense_cash_json',
        content: { monthly_burn: Number(burn), cash_balance: Number(cash) },
      })
    }
    const validCohorts = cohortRows.filter(r => r.month && r.starting)
    if (validCohorts.length) {
      records.push({
        source: 'cohort_retention', format: 'cohort_json',
        content: { cohorts: validCohorts.map(r => ({ cohort_month: r.month, starting_customers: Number(r.starting), active_after_3mo: Number(r.active) || 0 })) },
      })
    }
    if (reportedArr) {
      records.push({ source: 'reported_arr', format: 'arr_claim_json', content: { reported_arr: Number(reportedArr) } })
    }
    return records
  }

  async function handleSubmit() {
    const errs = validateStep()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setSubmitError(null)
    setSubmitting(true)
    setSubmitPhase('ingesting')
    try {
      const records = buildMetricsRecords()
      const ingest = await ingestDiligence({ company_name: companyName.trim(), round_label: roundLabel.trim() || null, metrics_records: records })
      setSubmitPhase('evaluating')
      const result = await evaluateDiligence(ingest.diligence_id, {})
      navigate(`/fundraising/diligence/${ingest.diligence_id}`, { state: { result } })
    } catch (err) {
      setSubmitError(err.message || 'Something went wrong. Is the backend running?')
      setSubmitting(false)
      setSubmitPhase(null)
    }
  }

  const stepProps = {
    1: <Step1 data={{ companyName, roundLabel }} onChange={(k, v) => { if (k === 'companyName') setCompanyName(v); else setRoundLabel(v) }} errors={errors} />,
    2: <Step2 rows={revenueRows} setRows={setRevenueRows} errors={errors} />,
    3: <Step3 rows={customerRows} setRows={setCustomerRows} errors={errors} />,
    4: <Step4 burn={burn} setBurn={setBurn} cash={cash} setCash={setCash} errors={errors} />,
    5: <Step5 cohortRows={cohortRows} setCohortRows={setCohortRows} reportedArr={reportedArr} setReportedArr={setReportedArr} revenueRows={revenueRows} errors={errors} />,
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
              <span className="text-indigo-400">Fundraising Credential</span><span>/</span>
              <span className="text-gray-400">new-diligence</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-1">Fundraising Diligence</h1>
            <p className="text-sm text-gray-500">Step {step} of {STEPS.length} — {STEPS[step - 1]}</p>
          </div>
          <button
            onClick={loadExample}
            disabled={submitting}
            className="flex-shrink-0 text-xs px-3 py-1.5 rounded-md bg-indigo-900/30 text-indigo-400 hover:bg-indigo-900/50 hover:text-indigo-300 border border-indigo-800/40 transition-all disabled:opacity-40 mt-1"
          >
            Load example
          </button>
        </div>

        <StepIndicator current={step} />

        {/* Step card */}
        <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden mb-6">
          <div className="px-5 py-3.5 border-b border-gray-800/40 bg-gray-900/40">
            <h2 className="text-sm font-semibold text-gray-300">{STEPS[step - 1]}</h2>
          </div>
          <div className="px-5 py-5">{stepProps[step]}</div>
        </div>

        {/* Submit error */}
        {submitError && (
          <div className="mb-4 flex items-start gap-3 px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
            <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div>
              <p className="font-medium text-red-300">Diligence failed</p>
              <p className="text-red-400/80 text-xs mt-0.5">{submitError}</p>
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center gap-3">
          {step > 1 && (
            <button
              onClick={() => { setErrors({}); setStep(s => s - 1) }}
              disabled={submitting}
              className="flex items-center gap-2 px-5 py-3 rounded-xl border border-gray-700/60 text-gray-300 hover:text-white hover:border-gray-600 font-medium text-sm transition-all disabled:opacity-40"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
              Back
            </button>
          )}

          {step < STEPS.length ? (
            <button
              onClick={handleNext}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-900/40 hover:-translate-y-0.5 disabled:opacity-50 disabled:translate-y-0"
            >
              Next
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-3 px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-900/40 hover:-translate-y-0.5 disabled:translate-y-0"
            >
              {submitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  {submitPhase === 'ingesting' ? 'Hashing metrics into TEE…' : 'Evaluating inside enclave…'}
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  Run Diligence
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
