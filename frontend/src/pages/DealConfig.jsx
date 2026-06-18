import React, { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRoomStatus, saveRoomConfig, confirmRoom } from '../api/roomApi.js'
import { useAuth } from '../hooks/useAuth.js'

// ── Helpers ────────────────────────────────────────────────────────────────

const DATASET_TYPES = [
  { value: 'ml_training',            label: 'ML Training' },
  { value: 'financial_transactions', label: 'Financial Transactions' },
  { value: 'iot_sensor',             label: 'IoT Sensor' },
  { value: 'transcripts',            label: 'Transcripts' },
  { value: 'custom',                 label: 'Custom' },
]

function fmt(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })
}

function pct(n) {
  return n != null ? `${(n * 100).toFixed(0)}%` : '—'
}

// ── Shared small components ────────────────────────────────────────────────

function SectionLabel({ children }) {
  return (
    <p className="text-xs font-mono tracking-widest text-dp-muted uppercase mb-3">
      {children}
    </p>
  )
}

function FieldLabel({ children, required }) {
  return (
    <label className="block text-xs font-mono text-dp-muted tracking-wider mb-1.5 uppercase">
      {children}{required && <span className="text-dp-teal ml-1">*</span>}
    </label>
  )
}

function TextInput({ label, value, onChange, placeholder, required, type = 'text', hint, prefix }) {
  return (
    <div>
      <FieldLabel required={required}>{label}</FieldLabel>
      <div className="relative">
        {prefix && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-dp-muted font-mono text-sm">{prefix}</span>
        )}
        <input
          type={type}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          required={required}
          className={`w-full bg-dp-bg border border-dp-border text-dp-text rounded px-3 py-2 text-sm
                     placeholder-dp-muted focus:outline-none focus:border-dp-teal transition-colors font-mono
                     ${prefix ? 'pl-7' : ''}`}
        />
      </div>
      {hint && <p className="text-xs text-dp-muted mt-1">{hint}</p>}
    </div>
  )
}

function Textarea({ label, value, onChange, placeholder, required, rows = 3 }) {
  return (
    <div>
      <FieldLabel required={required}>{label}</FieldLabel>
      <textarea
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        rows={rows}
        className="w-full bg-dp-bg border border-dp-border text-dp-text rounded px-3 py-2 text-sm
                   placeholder-dp-muted focus:outline-none focus:border-dp-teal transition-colors
                   resize-none"
      />
    </div>
  )
}

function SelectInput({ label, value, onChange, options }) {
  return (
    <div>
      <FieldLabel>{label}</FieldLabel>
      <select
        value={value}
        onChange={onChange}
        className="w-full bg-dp-bg border border-dp-border text-dp-text rounded px-3 py-2 text-sm
                   focus:outline-none focus:border-dp-teal transition-colors font-mono"
      >
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}

function ConfirmationRow({ sellerConfirmed, buyerConfirmed }) {
  const dot = (confirmed, label) => (
    <div className="flex items-center gap-2">
      <span className={`w-2 h-2 rounded-full ${confirmed ? 'bg-dp-teal' : 'bg-dp-border'}`} />
      <span className={`text-xs font-mono ${confirmed ? 'text-dp-teal' : 'text-dp-muted'}`}>
        {label}: {confirmed ? 'CONFIRMED' : 'PENDING'}
      </span>
    </div>
  )
  return (
    <div className="flex gap-6 py-3 px-4 bg-dp-bg border border-dp-border rounded">
      {dot(sellerConfirmed, 'SELLER')}
      {dot(buyerConfirmed, 'BUYER')}
    </div>
  )
}

// ── Read-only buyer summary ────────────────────────────────────────────────

function BuyerSummary({ config, status, onConfirm, confirming, confirmError, alreadyConfirmed }) {
  if (!config) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <div className="w-2 h-2 rounded-full bg-dp-amber animate-pulse" />
        <p className="text-dp-muted font-mono text-sm">Waiting for seller to configure the deal…</p>
      </div>
    )
  }

  const typeLabel = DATASET_TYPES.find(t => t.value === config.dataset_type)?.label || config.dataset_type

  return (
    <div className="space-y-6">
      <div className="bg-dp-surface border border-dp-border rounded-lg p-5 space-y-4">
        <SectionLabel>Dataset</SectionLabel>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs font-mono text-dp-teal border border-dp-teal/40 bg-dp-teal/10 px-2 py-0.5 rounded">
            {typeLabel}
          </span>
        </div>
        <p className="text-sm text-dp-text leading-relaxed">{config.data_description}</p>
      </div>

      <div className="bg-dp-surface border border-dp-border rounded-lg p-5 space-y-3">
        <SectionLabel>Pricing</SectionLabel>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-mono text-dp-muted mb-1">ASKING PRICE</p>
            <p className="text-xl font-mono text-dp-text font-semibold">${fmt(config.asking_price)}</p>
          </div>
          <div>
            <p className="text-xs font-mono text-dp-muted mb-1">YOUR BUDGET</p>
            <p className="text-xl font-mono text-dp-text font-semibold">${fmt(config.buyer_budget)}</p>
          </div>
        </div>
      </div>

      {config.buyer_requirements && (
        <div className="bg-dp-surface border border-dp-border rounded-lg p-5">
          <SectionLabel>Your Requirements</SectionLabel>
          <p className="text-sm text-dp-text leading-relaxed">{config.buyer_requirements}</p>
        </div>
      )}

      {config.quality_enabled && (
        <div className="bg-dp-surface border border-dp-border rounded-lg p-5 space-y-2">
          <SectionLabel>Quality Thresholds</SectionLabel>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-dp-bg border border-dp-border rounded p-3">
              <p className="text-xs font-mono text-dp-muted mb-1">NULL RATE MAX</p>
              <p className="font-mono text-dp-text">{pct(config.quality_null_rate_threshold)}</p>
            </div>
            <div className="bg-dp-bg border border-dp-border rounded p-3">
              <p className="text-xs font-mono text-dp-muted mb-1">COMPLETENESS MIN</p>
              <p className="font-mono text-dp-text">{pct(config.quality_completeness_min)}</p>
            </div>
            <div className="bg-dp-bg border border-dp-border rounded p-3">
              <p className="text-xs font-mono text-dp-muted mb-1">SCHEMA</p>
              <p className={`font-mono text-sm ${config.quality_schema_consistency ? 'text-dp-teal' : 'text-dp-amber'}`}>
                {config.quality_schema_consistency ? 'REQUIRED' : 'FLEXIBLE'}
              </p>
            </div>
          </div>
        </div>
      )}

      <ConfirmationRow sellerConfirmed={status.seller_confirmed} buyerConfirmed={status.buyer_confirmed} />

      {confirmError && (
        <div className="bg-dp-red/10 border border-dp-red/40 text-dp-red text-xs font-mono rounded px-3 py-2">
          {confirmError}
        </div>
      )}

      <button
        onClick={onConfirm}
        disabled={confirming || alreadyConfirmed}
        className={`w-full py-3 font-mono font-semibold text-sm rounded transition-all
          ${alreadyConfirmed
            ? 'bg-dp-teal/20 text-dp-teal border border-dp-teal/40 cursor-default'
            : 'bg-dp-teal text-dp-bg hover:bg-opacity-90 disabled:opacity-40 disabled:cursor-not-allowed'
          }`}
      >
        {alreadyConfirmed ? '✓ Confirmed' : confirming ? 'Confirming…' : 'Confirm & Start →'}
      </button>
    </div>
  )
}

// ── Seller config form ─────────────────────────────────────────────────────

const EMPTY_FORM = {
  data_description: '',
  dataset_type: 'ml_training',
  asking_price: '',
  floor_price: '',
  buyer_budget: '',
  buyer_requirements: '',
  quality_enabled: false,
  quality_null_rate_threshold: '0.10',
  quality_completeness_min: '0.90',
  quality_schema_consistency: true,
  escrow_enabled: false,
  escrow_eth_address: '',
}

function SellerConfigForm({ roomId, token, existingPayload, status, onSaved, onConfirm, confirming, confirmError, alreadyConfirmed }) {
  const [form, setForm] = useState(() => {
    if (!existingPayload) return EMPTY_FORM
    return {
      data_description:             existingPayload.data_description || '',
      dataset_type:                 existingPayload.dataset_type || 'ml_training',
      asking_price:                 existingPayload.asking_price?.toString() || '',
      floor_price:                  existingPayload.floor_price?.toString() || '',
      buyer_budget:                 existingPayload.buyer_budget?.toString() || '',
      buyer_requirements:           existingPayload.buyer_requirements || '',
      quality_enabled:              existingPayload.quality_enabled || false,
      quality_null_rate_threshold:  existingPayload.quality_null_rate_threshold?.toString() || '0.10',
      quality_completeness_min:     existingPayload.quality_completeness_min?.toString() || '0.90',
      quality_schema_consistency:   existingPayload.quality_schema_consistency ?? true,
      escrow_enabled:               existingPayload.escrow_enabled || false,
      escrow_eth_address:           existingPayload.escrow_eth_address || '',
    }
  })
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved] = useState(!!existingPayload)

  const set = (field) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm(f => ({ ...f, [field]: val }))
    setSaved(false)
  }

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    try {
      await saveRoomConfig(roomId, token, {
        data_description:             form.data_description.trim(),
        dataset_type:                 form.dataset_type,
        asking_price:                 parseFloat(form.asking_price),
        floor_price:                  parseFloat(form.floor_price),
        buyer_budget:                 parseFloat(form.buyer_budget),
        buyer_requirements:           form.buyer_requirements.trim(),
        quality_enabled:              form.quality_enabled,
        quality_null_rate_threshold:  parseFloat(form.quality_null_rate_threshold),
        quality_completeness_min:     parseFloat(form.quality_completeness_min),
        quality_schema_consistency:   form.quality_schema_consistency,
        escrow_enabled:               form.escrow_enabled,
        escrow_eth_address:           form.escrow_eth_address.trim() || null,
      })
      setSaved(true)
      onSaved()
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const canConfirm = saved && existingPayload

  return (
    <form onSubmit={handleSave} className="space-y-6">
      {/* Data details */}
      <div className="bg-dp-surface border border-dp-border rounded-lg p-5 space-y-4">
        <SectionLabel>Data Details</SectionLabel>
        <SelectInput
          label="Dataset Type"
          value={form.dataset_type}
          onChange={set('dataset_type')}
          options={DATASET_TYPES}
        />
        <Textarea
          label="Data Description"
          value={form.data_description}
          onChange={set('data_description')}
          placeholder="Describe your dataset: size, format, labels, timeframe, provenance…"
          required
          rows={4}
        />
      </div>

      {/* Pricing */}
      <div className="bg-dp-surface border border-dp-border rounded-lg p-5 space-y-4">
        <SectionLabel>Pricing</SectionLabel>
        <div className="grid grid-cols-2 gap-4">
          <TextInput
            label="Asking Price"
            type="number"
            value={form.asking_price}
            onChange={set('asking_price')}
            placeholder="1000"
            required
            prefix="$"
            hint="Shown to buyer"
          />
          <TextInput
            label="Floor Price"
            type="number"
            value={form.floor_price}
            onChange={set('floor_price')}
            placeholder="800"
            required
            prefix="$"
            hint="Never shown to buyer"
          />
        </div>
        <TextInput
          label="Buyer Budget"
          type="number"
          value={form.buyer_budget}
          onChange={set('buyer_budget')}
          placeholder="1200"
          required
          prefix="$"
          hint="Maximum the buyer will pay"
        />
      </div>

      {/* Requirements */}
      <div className="bg-dp-surface border border-dp-border rounded-lg p-5">
        <SectionLabel>Buyer Requirements</SectionLabel>
        <Textarea
          label="What should the buyer receive?"
          value={form.buyer_requirements}
          onChange={set('buyer_requirements')}
          placeholder="Specific columns, formats, licenses, or delivery method…"
          rows={3}
        />
      </div>

      {/* Quality metrics (expandable) */}
      <div className="bg-dp-surface border border-dp-border rounded-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setForm(f => ({ ...f, quality_enabled: !f.quality_enabled }))}
          className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-dp-border/20 transition-colors"
        >
          <span className="text-xs font-mono tracking-widest text-dp-muted uppercase">Quality Metrics</span>
          <span className={`text-xs font-mono ${form.quality_enabled ? 'text-dp-teal' : 'text-dp-muted'}`}>
            {form.quality_enabled ? '▼ ON' : '▶ OFF'}
          </span>
        </button>

        {form.quality_enabled && (
          <div className="px-5 pb-5 pt-2 space-y-3 border-t border-dp-border">
            <div className="grid grid-cols-2 gap-4">
              <TextInput
                label="Null Rate Threshold"
                type="number"
                value={form.quality_null_rate_threshold}
                onChange={set('quality_null_rate_threshold')}
                placeholder="0.10"
                hint="Max allowed null rate (0–1)"
              />
              <TextInput
                label="Completeness Min"
                type="number"
                value={form.quality_completeness_min}
                onChange={set('quality_completeness_min')}
                placeholder="0.90"
                hint="Min completeness (0–1)"
              />
            </div>
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="schema_consistency"
                checked={form.quality_schema_consistency}
                onChange={set('quality_schema_consistency')}
                className="accent-dp-teal"
              />
              <label htmlFor="schema_consistency" className="text-sm text-dp-text cursor-pointer">
                Require schema consistency
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Escrow toggle */}
      <div className="bg-dp-surface border border-dp-border rounded-lg overflow-hidden">
        <button
          type="button"
          onClick={() => setForm(f => ({ ...f, escrow_enabled: !f.escrow_enabled }))}
          className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-dp-border/20 transition-colors"
        >
          <span className="text-xs font-mono tracking-widest text-dp-muted uppercase">Escrow</span>
          <span className={`text-xs font-mono ${form.escrow_enabled ? 'text-dp-teal' : 'text-dp-muted'}`}>
            {form.escrow_enabled ? '▼ ON' : '▶ OFF'}
          </span>
        </button>

        {form.escrow_enabled && (
          <div className="px-5 pb-5 pt-2 border-t border-dp-border">
            <TextInput
              label="Escrow ETH Address"
              value={form.escrow_eth_address}
              onChange={set('escrow_eth_address')}
              placeholder="0x..."
            />
          </div>
        )}
      </div>

      {saveError && (
        <div className="bg-dp-red/10 border border-dp-red/40 text-dp-red text-xs font-mono rounded px-3 py-2">
          {saveError}
        </div>
      )}

      {/* Save button */}
      <button
        type="submit"
        disabled={saving}
        className="w-full py-2.5 border border-dp-teal text-dp-teal font-mono text-sm rounded
                   hover:bg-dp-teal/10 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
      >
        {saving ? 'Saving…' : saved ? '✓ Saved — Edit & Save Again' : 'Save Configuration'}
      </button>

      {/* Divider */}
      <div className="border-t border-dp-border pt-4 space-y-3">
        <SectionLabel>Confirmation</SectionLabel>
        <ConfirmationRow sellerConfirmed={status.seller_confirmed} buyerConfirmed={status.buyer_confirmed} />

        {confirmError && (
          <div className="bg-dp-red/10 border border-dp-red/40 text-dp-red text-xs font-mono rounded px-3 py-2">
            {confirmError}
          </div>
        )}

        {!canConfirm && (
          <p className="text-xs text-dp-muted font-mono">Save configuration first to unlock confirmation.</p>
        )}

        <button
          type="button"
          onClick={onConfirm}
          disabled={confirming || alreadyConfirmed || !canConfirm}
          className={`w-full py-3 font-mono font-semibold text-sm rounded transition-all
            ${alreadyConfirmed
              ? 'bg-dp-teal/20 text-dp-teal border border-dp-teal/40 cursor-default'
              : 'bg-dp-teal text-dp-bg hover:bg-opacity-90 disabled:opacity-30 disabled:cursor-not-allowed'
            }`}
        >
          {alreadyConfirmed ? '✓ Confirmed' : confirming ? 'Confirming…' : 'Confirm & Start →'}
        </button>
      </div>
    </form>
  )
}

// ── Main DealConfig page ───────────────────────────────────────────────────

export default function DealConfig() {
  const { room_id } = useParams()
  const navigate = useNavigate()
  const { auth } = useAuth(room_id)

  const [status, setStatus] = useState(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getRoomStatus(room_id)
      setStatus(data)
    } catch {}
    finally { setLoadingStatus(false) }
  }, [room_id])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 3000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const handleConfirm = async () => {
    if (!auth) return
    setConfirming(true)
    setConfirmError(null)
    try {
      await confirmRoom(room_id, auth.token)
      await fetchStatus()
    } catch (err) {
      setConfirmError(err.message)
    } finally {
      setConfirming(false)
    }
  }

  useEffect(() => {
    if (['confirmed', 'running', 'complete'].includes(status?.status)) {
      navigate(`/room/${room_id}/negotiate`, { replace: true })
    }
  }, [status, room_id, navigate])

  if (loadingStatus) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center">
        <div className="flex items-center gap-3 text-dp-muted font-mono text-sm">
          <div className="w-2 h-2 rounded-full bg-dp-teal animate-pulse" />
          Loading…
        </div>
      </div>
    )
  }

  if (!auth) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center px-4">
        <p className="text-dp-muted font-mono text-sm">Session expired. Please rejoin the room.</p>
      </div>
    )
  }

  const isSeller = auth.role === 'seller'
  const alreadyConfirmed = isSeller ? status?.seller_confirmed : status?.buyer_confirmed

  return (
    <div className="min-h-screen bg-dp-bg text-dp-text flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-dp-border">
        <div className="flex items-center gap-2.5">
          <button onClick={() => navigate(`/room/${room_id}`)} className="text-dp-muted hover:text-dp-text transition-colors">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <span className="font-semibold text-dp-text">DealProof</span>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-mono px-2 py-0.5 rounded border ${
            isSeller
              ? 'text-dp-teal border-dp-teal/40 bg-dp-teal/10'
              : 'text-dp-amber border-dp-amber/40 bg-dp-amber/10'
          }`}>
            {isSeller ? 'SELLER' : 'BUYER'}
          </span>
          <span className="text-xs font-mono text-dp-muted">
            {status?.status?.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 max-w-2xl mx-auto w-full px-4 py-8">
        <h1 className="text-lg font-semibold text-dp-text mb-1">
          {isSeller ? 'Configure Deal' : 'Deal Terms'}
        </h1>
        <p className="text-sm text-dp-muted mb-6">
          {isSeller
            ? 'Set pricing and requirements. Floor price is never visible to the buyer.'
            : 'Review the deal terms and confirm when ready.'}
        </p>

        {isSeller ? (
          <SellerConfigForm
            roomId={room_id}
            token={auth.token}
            existingPayload={status?.deal_payload}
            status={status || { seller_confirmed: false, buyer_confirmed: false }}
            onSaved={fetchStatus}
            onConfirm={handleConfirm}
            confirming={confirming}
            confirmError={confirmError}
            alreadyConfirmed={!!alreadyConfirmed}
          />
        ) : (
          <BuyerSummary
            config={status?.deal_payload}
            status={status || { seller_confirmed: false, buyer_confirmed: false }}
            onConfirm={handleConfirm}
            confirming={confirming}
            confirmError={confirmError}
            alreadyConfirmed={!!alreadyConfirmed}
          />
        )}
      </div>
    </div>
  )
}
