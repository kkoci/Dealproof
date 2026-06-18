import React, { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRoomStatus } from '../api/roomApi.js'
import { getDealStatus } from '../api.js'
import { useAuth } from '../hooks/useAuth.js'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return '—'
  return `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

function shortHash(h) {
  if (!h) return null
  return `${h.slice(0, 14)}…${h.slice(-8)}`
}

function CheckBadge({ value, label }) {
  const ok = value === true
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs font-mono text-dp-muted">{label}</span>
      <span className={`text-xs font-mono font-semibold ${ok ? 'text-dp-teal' : 'text-dp-red'}`}>
        {ok ? '✓ true' : '✗ false'}
      </span>
    </div>
  )
}

function HashRow({ label, value, verifyUrl }) {
  const [copied, setCopied] = useState(false)
  if (!value) return null

  function copy() {
    navigator.clipboard.writeText(value)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="flex items-center justify-between gap-2 py-2 border-b border-dp-border/40 last:border-0">
      <span className="text-xs font-mono text-dp-muted shrink-0 w-28">{label}</span>
      <span className="text-xs font-mono text-dp-text flex-1 truncate">{shortHash(value)}</span>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={copy}
          className="text-xs font-mono text-dp-muted hover:text-dp-teal transition-colors"
        >
          {copied ? 'COPIED' : 'COPY'}
        </button>
        {verifyUrl && (
          <a
            href={verifyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-mono text-dp-teal hover:underline"
          >
            VERIFY
          </a>
        )}
      </div>
    </div>
  )
}

// ── Main CredentialView ────────────────────────────────────────────────────

export default function CredentialView() {
  const { room_id } = useParams()
  const navigate = useNavigate()
  const { auth } = useAuth(room_id)

  const [result, setResult] = useState(null)
  const [dealId, setDealId] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [permalinkCopied, setPermalinkCopied] = useState(false)

  useEffect(() => {
    if (!auth) return
    async function load() {
      try {
        const room = await getRoomStatus(room_id)
        if (!room.deal_id) {
          navigate(`/room/${room_id}/negotiate`, { replace: true })
          return
        }
        setDealId(room.deal_id)
        const status = await getDealStatus(room.deal_id)
        if (status.result) {
          setResult(status.result)
        } else {
          setError('Deal result not available yet.')
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [room_id, auth])

  // ── Derived credential data ─────────────────────────────────────────────

  const conductCred = result?.picreds?.find(c => c.credential_type === 'conduct')
  const ar = conductCred?.audit_result || {}
  const rounds = result?.transcript?.length ?? 0
  const quality = result?.data_quality_report

  // ── Actions ─────────────────────────────────────────────────────────────

  function downloadJSON() {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `dealproof-${dealId?.slice(0, 8) ?? 'credential'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function copyPermalink() {
    navigator.clipboard.writeText(window.location.href)
    setPermalinkCopied(true)
    setTimeout(() => setPermalinkCopied(false), 1500)
  }

  // ── Loading / error states ───────────────────────────────────────────────

  if (!auth) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center">
        <p className="text-dp-muted font-mono text-sm">Session expired. Please rejoin the room.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center">
        <div className="flex items-center gap-3 text-dp-muted font-mono text-sm">
          <span className="w-2 h-2 rounded-full bg-dp-teal animate-pulse" />
          Loading credential…
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-dp-bg flex flex-col items-center justify-center gap-3 px-4">
        <p className="text-dp-red font-mono text-sm">{error}</p>
        <button
          onClick={() => navigate(`/room/${room_id}/negotiate`)}
          className="text-xs font-mono text-dp-teal hover:underline"
        >
          ← Back to negotiation
        </button>
      </div>
    )
  }

  if (!result?.agreed) {
    return (
      <div className="min-h-screen bg-dp-bg flex flex-col items-center justify-center gap-3 px-4">
        <p className="text-dp-muted font-mono text-sm">No deal was agreed in this room.</p>
        <button
          onClick={() => navigate('/')}
          className="text-xs font-mono text-dp-teal hover:underline"
        >
          Start a new deal →
        </button>
      </div>
    )
  }

  // ── Credential card ──────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-dp-bg text-dp-text flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-dp-border shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-dp-surface border border-dp-border flex items-center justify-center">
            <svg className="w-4 h-4 text-dp-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <span className="font-semibold text-dp-text">DealProof</span>
        </div>
        <span className="text-xs font-mono text-dp-muted tracking-widest">ATTESTED CREDENTIAL</span>
      </div>

      {/* Body */}
      <div className="flex-1 px-4 py-8 flex justify-center overflow-y-auto">
        <div className="w-full max-w-2xl space-y-4">

          {/* ── Credential card ── */}
          <div className="bg-dp-surface border-t-2 border-dp-teal rounded-lg border-x border-b border-dp-border overflow-hidden">

            {/* Card header row */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-dp-border">
              <div className="flex items-center gap-2">
                <span className="text-dp-teal font-mono font-semibold text-sm">✓ DEAL ATTESTED</span>
                {result.arbitrated && (
                  <span className="text-xs font-mono text-dp-amber px-1.5 py-0.5 rounded border border-dp-amber/40 bg-dp-amber/10">
                    ARBITRATED
                  </span>
                )}
                {result.picreds_attested && (
                  <span className="text-xs font-mono text-dp-teal px-1.5 py-0.5 rounded border border-dp-teal/40 bg-dp-teal/10">
                    πCREDS
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={copyPermalink}
                  className="text-xs font-mono text-dp-muted hover:text-dp-teal transition-colors px-2 py-1 rounded border border-dp-border hover:border-dp-teal/40"
                >
                  {permalinkCopied ? 'COPIED' : 'SHARE'}
                </button>
                <button
                  onClick={downloadJSON}
                  className="text-xs font-mono text-dp-teal px-2 py-1 rounded border border-dp-teal/40 bg-dp-teal/10 hover:bg-dp-teal/20 transition-colors"
                >
                  DOWNLOAD JSON
                </button>
              </div>
            </div>

            {/* Deal ID */}
            <div className="px-5 py-2 border-b border-dp-border/50 bg-dp-bg/30">
              <span className="text-xs font-mono text-dp-muted">deal_id: </span>
              <span className="text-xs font-mono text-dp-text break-all">{dealId}</span>
            </div>

            {/* Key metrics */}
            <div className="px-5 py-5 border-b border-dp-border grid grid-cols-3 gap-6">
              <div>
                <p className="text-xs font-mono text-dp-muted mb-1.5">AGREED PRICE</p>
                <p className="text-3xl font-mono font-bold text-dp-teal">{fmt(result.final_price)}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-dp-muted mb-1.5">ROUNDS</p>
                <p className="text-3xl font-mono font-bold text-dp-text">{rounds}</p>
              </div>
              <div>
                <p className="text-xs font-mono text-dp-muted mb-1.5">GENUINE NEGOTIATION</p>
                <p className={`text-sm font-mono font-semibold mt-2 ${
                  result.audit_report?.genuine_negotiation !== false ? 'text-dp-teal' : 'text-dp-red'
                }`}>
                  {result.audit_report?.genuine_negotiation !== false ? '✓ true' : '✗ false'}
                </p>
              </div>
            </div>

            {/* Auditor summary */}
            {result.audit_report?.summary && (
              <div className="px-5 py-3 border-b border-dp-border bg-dp-bg/20">
                <p className="text-xs font-mono text-dp-muted mb-1 uppercase tracking-wider">Auditor Summary</p>
                <p className="text-xs text-dp-text leading-relaxed">{result.audit_report.summary}</p>
              </div>
            )}

            {/* πCREDS conduct credential */}
            {conductCred && (
              <div className="px-5 py-4 border-b border-dp-border">
                <p className="text-xs font-mono tracking-widest text-dp-muted uppercase mb-2">πCreds Conduct Credential</p>
                <div className="divide-y divide-dp-border/30">
                  <CheckBadge value={ar.buyer_budget_respected}     label="buyer_budget_respected" />
                  <CheckBadge value={ar.seller_floor_respected}     label="seller_floor_respected" />
                  <CheckBadge value={ar.no_sudden_capitulation}     label="no_sudden_capitulation" />
                  <CheckBadge value={ar.convergence_pattern_valid}  label="convergence_pattern_valid" />
                </div>
                {ar.assessment && (
                  <p className="text-xs text-dp-muted mt-3 leading-relaxed pt-3 border-t border-dp-border/40">
                    {ar.assessment}
                  </p>
                )}
              </div>
            )}

            {/* Data quality */}
            {quality && (
              <div className="px-5 py-4 border-b border-dp-border">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-xs font-mono tracking-widest text-dp-muted uppercase">Data Quality</p>
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${
                    result.quality_attested
                      ? 'text-dp-teal border-dp-teal/40 bg-dp-teal/10'
                      : 'text-dp-amber border-dp-amber/40 bg-dp-amber/10'
                  }`}>
                    {result.quality_attested ? 'ATTESTED' : 'UNATTESTED'}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4 mb-3">
                  <div>
                    <p className="text-xs font-mono text-dp-muted mb-0.5">COMPLETENESS</p>
                    <p className={`text-lg font-mono font-bold ${
                      quality.overall_quality === 'high' ? 'text-dp-teal'
                        : quality.overall_quality === 'medium' ? 'text-dp-amber'
                        : 'text-dp-red'
                    }`}>
                      {quality.completeness_score != null
                        ? `${(quality.completeness_score * 100).toFixed(1)}%`
                        : '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-mono text-dp-muted mb-0.5">VERDICT</p>
                    <p className={`text-lg font-mono font-bold uppercase ${
                      quality.overall_quality === 'high' ? 'text-dp-teal'
                        : quality.overall_quality === 'medium' ? 'text-dp-amber'
                        : 'text-dp-red'
                    }`}>
                      {quality.overall_quality || '—'}
                    </p>
                  </div>
                </div>

                {quality.quality_issues?.length > 0 && (
                  <div className="space-y-1 mb-3">
                    {quality.quality_issues.slice(0, 3).map((issue, i) => (
                      <p key={i} className="text-xs font-mono text-dp-amber">↳ {issue}</p>
                    ))}
                  </div>
                )}

                {quality.quality_hash && (
                  <div className="pt-2 border-t border-dp-border/40">
                    <span className="text-xs font-mono text-dp-muted">quality_hash: </span>
                    <span className="text-xs font-mono text-dp-text">{shortHash(quality.quality_hash)}</span>
                  </div>
                )}
              </div>
            )}

            {/* Attestation hashes */}
            <div className="px-5 py-4">
              <p className="text-xs font-mono tracking-widest text-dp-muted uppercase mb-3">Attestation Hashes</p>
              <HashRow
                label="TDX QUOTE"
                value={result.attestation}
                verifyUrl={`${BASE_URL}/api/deals/${dealId}/dcap-verify`}
              />
              <HashRow label="PICREDS HASH"  value={result.picreds_hash} />
              <HashRow label="MEMORY PRE"    value={result.memory_hash} />
              <HashRow label="MEMORY POST"   value={result.memory_hash_post} />
              <HashRow label="MEMORY CTX"    value={result.memory_context_hash} />
              <HashRow label="DATA VERIFY"   value={result.data_verification_attestation} />
            </div>

            {/* Arc / Hedera / escrow badges */}
            {(result.hedera_transaction_id || result.escrow_tx || result.completion_tx) && (
              <div className="px-5 pb-4 flex flex-wrap gap-2 border-t border-dp-border/40 pt-3">
                {result.hedera_transaction_id && (
                  <span className="text-xs font-mono text-dp-muted px-2 py-1 rounded border border-dp-border">
                    HEDERA · {result.hedera_transaction_id.slice(0, 20)}…
                  </span>
                )}
                {result.escrow_tx && (
                  <span className="text-xs font-mono text-dp-muted px-2 py-1 rounded border border-dp-border">
                    ESCROW DEPOSIT · {result.escrow_tx.slice(0, 12)}…
                  </span>
                )}
                {result.completion_tx && (
                  <span className="text-xs font-mono text-dp-teal px-2 py-1 rounded border border-dp-teal/40 bg-dp-teal/10">
                    ESCROW RELEASED · {result.completion_tx.slice(0, 12)}…
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Post-deal actions */}
          <div className="flex items-center justify-between pt-1">
            <button
              onClick={() => navigate('/')}
              className="text-xs font-mono text-dp-muted hover:text-dp-text transition-colors"
            >
              ← Start a new deal
            </button>
            <button
              onClick={downloadJSON}
              className="text-xs font-mono text-dp-muted hover:text-dp-teal transition-colors"
            >
              Export for audit →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
