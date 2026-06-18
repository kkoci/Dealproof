import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRoomStatus, startRoomDeal } from '../api/roomApi.js'
import { getDealStatus } from '../api.js'
import { useAuth } from '../hooks/useAuth.js'
import TrustStackBar from '../components/TrustStackBar.jsx'
import QualityPanel from '../components/QualityPanel.jsx'

// ── Helpers ────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null) return '—'
  return `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

function elapsed(ms) {
  const s = Math.floor(ms / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

// ── Round row ──────────────────────────────────────────────────────────────

function RoundRow({ round, agreed, visible }) {
  const [open, setOpen] = useState(false)
  const isBuyer = round.role === 'buyer'
  const isAgreed = round.action === 'accept' && agreed

  const rowBg = isAgreed
    ? 'bg-dp-teal/5 border-dp-teal/30'
    : isBuyer
    ? 'bg-blue-500/5 border-blue-500/20'
    : 'bg-dp-amber/5 border-dp-amber/20'

  const roleColor = isBuyer ? 'text-blue-400' : 'text-dp-amber'

  return (
    <div
      className={`border rounded-md overflow-hidden transition-all duration-300 ${rowBg} ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
      }`}
      style={{ transition: 'opacity 350ms ease, transform 350ms ease' }}
    >
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <span className="text-xs font-mono text-dp-muted w-14 shrink-0">
          RND {round.round}
        </span>
        <span className={`text-xs font-mono font-semibold w-14 shrink-0 ${roleColor}`}>
          {round.role.toUpperCase()}
        </span>
        <span className="text-xs font-mono text-dp-muted w-16 shrink-0 uppercase">
          {round.action}
        </span>
        <span className={`text-sm font-mono font-semibold flex-1 ${isAgreed ? 'text-dp-teal' : 'text-dp-text'}`}>
          {fmt(round.price)}
          {isAgreed && <span className="ml-2 text-dp-teal">✓ AGREED</span>}
        </span>
        <span className="text-dp-muted/50 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && round.reasoning && (
        <div className="px-3 pb-3 pt-1 border-t border-dp-border/50">
          <p className="text-xs text-dp-muted leading-relaxed">{round.reasoning}</p>
        </div>
      )}
    </div>
  )
}

// ── Transcript panel ───────────────────────────────────────────────────────

function TranscriptPanel({ rounds, agreed, finalPrice, negotiating, startedAt }) {
  const [visibleCount, setVisibleCount] = useState(0)
  const prevRoundsLen = useRef(0)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (rounds.length > prevRoundsLen.current) {
      prevRoundsLen.current = rounds.length
      let i = visibleCount
      const reveal = () => {
        i++
        setVisibleCount(i)
        if (i < rounds.length) setTimeout(reveal, 380)
      }
      setTimeout(reveal, 100)
    }
  }, [rounds.length])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [visibleCount])

  return (
    <div className="bg-dp-surface border border-dp-border rounded-lg flex flex-col min-h-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dp-border">
        <p className="text-xs font-mono tracking-widest text-dp-muted uppercase">Negotiation Transcript</p>
        {negotiating && (
          <div className="flex items-center gap-1.5 text-xs font-mono text-dp-amber">
            <span className="w-1.5 h-1.5 rounded-full bg-dp-amber animate-pulse" />
            LIVE
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2 scrollbar-thin" style={{ maxHeight: '420px' }}>
        {negotiating && rounds.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <div className="flex gap-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-dp-teal animate-pulse"
                  style={{ animationDelay: `${i * 200}ms` }}
                />
              ))}
            </div>
            <p className="text-dp-muted font-mono text-sm">Agents negotiating…</p>
            {startedAt && (
              <p className="text-dp-muted/50 font-mono text-xs">
                {elapsed(Date.now() - startedAt)}
              </p>
            )}
          </div>
        )}

        {rounds.map((r, i) => (
          <RoundRow key={i} round={r} agreed={agreed} visible={i < visibleCount} />
        ))}

        {agreed && finalPrice != null && (
          <div className="mt-2 p-3 bg-dp-teal/10 border border-dp-teal/40 rounded-md text-center">
            <p className="text-dp-teal font-mono font-semibold">Deal Agreed</p>
            <p className="text-2xl font-mono font-bold text-dp-teal mt-1">{fmt(finalPrice)}</p>
          </div>
        )}

        {!negotiating && !agreed && rounds.length > 0 && (
          <div className="mt-2 p-3 bg-dp-red/10 border border-dp-red/40 rounded-md text-center">
            <p className="text-dp-red font-mono text-sm">Negotiation ended without agreement</p>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Main NegotiationView ───────────────────────────────────────────────────

export default function NegotiationView() {
  const { room_id } = useParams()
  const navigate = useNavigate()
  const { auth } = useAuth(room_id)

  const [dealId, setDealId] = useState(null)
  const [dealStatus, setDealStatus] = useState(null)
  const [startError, setStartError] = useState(null)
  const [startedAt] = useState(() => Date.now())
  const [, setTick] = useState(0)  // force re-render for elapsed timer

  // Tick every second while negotiating (updates elapsed timer display)
  useEffect(() => {
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [])

  // Step 1: get deal_id (start if needed)
  useEffect(() => {
    if (!auth) return

    async function init() {
      try {
        const room = await getRoomStatus(room_id)

        if (room.status === 'confirmed') {
          const res = await startRoomDeal(room_id, auth.token)
          setDealId(res.deal_id)
        } else if ((room.status === 'running' || room.status === 'complete') && room.deal_id) {
          setDealId(room.deal_id)
        } else {
          // Unexpected state — go back
          navigate(`/room/${room_id}`, { replace: true })
        }
      } catch (err) {
        setStartError(err.message)
      }
    }

    init()
  }, [room_id, auth])

  // Step 2: poll deal status every 2s once we have deal_id
  const pollDeal = useCallback(async () => {
    if (!dealId) return
    try {
      const status = await getDealStatus(dealId)
      setDealStatus(status)
    } catch {}
  }, [dealId])

  useEffect(() => {
    if (!dealId) return
    pollDeal()
    const done = dealStatus?.status === 'agreed' || dealStatus?.status === 'failed'
    if (done) return
    const interval = setInterval(pollDeal, 2000)
    return () => clearInterval(interval)
  }, [dealId, pollDeal, dealStatus?.status])

  const result = dealStatus?.result
  const negotiating = !result || dealStatus?.status === 'negotiating' || dealStatus?.status === 'pending'
  const agreed = result?.agreed === true
  const rounds = result?.transcript ?? []

  const trustActive = {
    tdx:     !negotiating,
    dcap:    !!(result?.attestation),
    memory:  !!(result?.memory_attested),
    picreds: !!(result?.picreds_attested),
  }

  // ── Loading / error ───────────────────────────────────────────────────────
  if (!auth) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center">
        <p className="text-dp-muted font-mono text-sm">Session expired. Please rejoin the room.</p>
      </div>
    )
  }

  if (startError) {
    return (
      <div className="min-h-screen bg-dp-bg flex flex-col items-center justify-center gap-3 px-4">
        <p className="text-dp-red font-mono text-sm">{startError}</p>
        <button onClick={() => navigate(`/room/${room_id}`)} className="text-xs font-mono text-dp-teal hover:underline">
          ← Back to room
        </button>
      </div>
    )
  }

  if (!dealId) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center">
        <div className="flex items-center gap-3 text-dp-muted font-mono text-sm">
          <div className="w-2 h-2 rounded-full bg-dp-teal animate-pulse" />
          Starting negotiation…
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-dp-bg text-dp-text flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-dp-border">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-dp-surface border border-dp-border flex items-center justify-center">
            <svg className="w-4 h-4 text-dp-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </div>
          <span className="font-semibold text-dp-text">DealProof</span>
        </div>
        <div className="flex items-center gap-3">
          {negotiating ? (
            <span className="flex items-center gap-1.5 text-xs font-mono text-dp-amber">
              <span className="w-1.5 h-1.5 rounded-full bg-dp-amber animate-pulse" />
              NEGOTIATING
            </span>
          ) : agreed ? (
            <span className="flex items-center gap-1.5 text-xs font-mono text-dp-teal">
              <span className="w-1.5 h-1.5 rounded-full bg-dp-teal" />
              AGREED
            </span>
          ) : (
            <span className="text-xs font-mono text-dp-red">FAILED</span>
          )}
          <span className="text-xs font-mono text-dp-muted hidden sm:block">
            {dealId.slice(0, 8)}…
          </span>
        </div>
      </div>

      {/* Three-panel body */}
      <div className="flex-1 p-4 flex flex-col lg:flex-row gap-4 min-h-0">

        {/* Left — Transcript */}
        <div className="flex-1 min-w-0">
          <TranscriptPanel
            rounds={rounds}
            agreed={agreed}
            finalPrice={result?.final_price}
            negotiating={negotiating}
            startedAt={startedAt}
          />
        </div>

        {/* Center — Trust Stack */}
        <div className="w-full lg:w-64 shrink-0">
          <TrustStackBar
            active={trustActive}
            hash={result?.attestation}
          />

          {/* Deal ID below trust stack */}
          {result && (
            <div className="mt-3 bg-dp-surface border border-dp-border rounded-lg p-3 space-y-2">
              {result.picreds_hash && (
                <div>
                  <p className="text-xs font-mono text-dp-muted mb-0.5">PICREDS HASH</p>
                  <p className="text-xs font-mono text-dp-text break-all">
                    {result.picreds_hash.slice(0, 16)}…
                  </p>
                </div>
              )}
              {result.memory_hash && (
                <div>
                  <p className="text-xs font-mono text-dp-muted mb-0.5">MEMORY HASH</p>
                  <p className="text-xs font-mono text-dp-text break-all">
                    {result.memory_hash.slice(0, 16)}…
                  </p>
                </div>
              )}
              {result.arbitrated && (
                <div className="text-xs font-mono text-dp-amber">⚡ Arbitrated</div>
              )}
            </div>
          )}

          {/* Phase 4 button */}
          {!negotiating && agreed && (
            <button
              onClick={() => navigate(`/room/${room_id}/credential`)}
              className="mt-3 w-full py-2.5 bg-dp-teal text-dp-bg font-mono font-semibold text-sm
                         rounded hover:bg-opacity-90 transition-all"
            >
              View Credential →
            </button>
          )}
        </div>

        {/* Right — Quality Panel */}
        {(result?.data_quality_report || result?.quality_attested) && (
          <div className="w-full lg:w-56 shrink-0">
            <QualityPanel
              report={result?.data_quality_report}
              attested={result?.quality_attested}
            />
          </div>
        )}
      </div>
    </div>
  )
}
