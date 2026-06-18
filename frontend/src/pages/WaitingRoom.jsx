import React, { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { registerBuyer, getRoomStatus } from '../api/roomApi.js'
import { useAuth } from '../hooks/useAuth.js'

// ── Helpers ────────────────────────────────────────────────────────────────

function truncate(str, n = 10) {
  if (!str) return '—'
  return str.length > n ? `${str.slice(0, 6)}…${str.slice(-4)}` : str
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).catch(() => {})
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const cfg = {
    waiting: { label: 'WAITING FOR BUYER', color: 'text-dp-amber', border: 'border-dp-amber/40', bg: 'bg-dp-amber/10' },
    ready:   { label: 'READY',             color: 'text-dp-teal',  border: 'border-dp-teal/40',  bg: 'bg-dp-teal/10'  },
    running: { label: 'NEGOTIATING',       color: 'text-dp-teal',  border: 'border-dp-teal/40',  bg: 'bg-dp-teal/10'  },
    complete:{ label: 'COMPLETE',          color: 'text-dp-teal',  border: 'border-dp-teal/40',  bg: 'bg-dp-teal/10'  },
    failed:  { label: 'FAILED',            color: 'text-dp-red',   border: 'border-dp-red/40',   bg: 'bg-dp-red/10'   },
  }
  const c = cfg[status] || cfg.waiting
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded font-mono text-xs tracking-widest border ${c.color} ${c.border} ${c.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${status === 'waiting' ? 'bg-dp-amber animate-pulse' : 'bg-dp-teal'}`} />
      {c.label}
    </span>
  )
}

function ParticipantPanel({ role, name, eth, isSelf, empty }) {
  const label = role === 'seller' ? 'SELLER' : 'BUYER'
  const accent = isSelf ? 'border-dp-teal/50' : 'border-dp-border'
  return (
    <div className={`bg-dp-surface border ${accent} rounded-lg p-5 flex flex-col gap-3 min-w-0`}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono tracking-widest text-dp-muted">{label}</span>
        {isSelf && (
          <span className="text-xs font-mono text-dp-teal border border-dp-teal/40 bg-dp-teal/10 px-2 py-0.5 rounded">
            YOU
          </span>
        )}
      </div>
      {empty ? (
        <div className="flex flex-col gap-1.5">
          <div className="h-4 w-24 bg-dp-border/40 rounded animate-pulse" />
          <div className="h-3 w-32 bg-dp-border/30 rounded animate-pulse" />
        </div>
      ) : (
        <>
          <p className="text-dp-text font-semibold text-lg truncate">{name || '—'}</p>
          <p className="text-xs font-mono text-dp-muted truncate">{eth ? truncate(eth, 18) : 'No ETH address'}</p>
        </>
      )}
    </div>
  )
}

function BuyerJoinForm({ sellerName, roomId, onJoined }) {
  const [form, setForm] = useState({ name: '', eth_address: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await registerBuyer({
        room_id: roomId,
        name: form.name.trim(),
        eth_address: form.eth_address.trim() || undefined,
      })
      onJoined({
        token: res.buyer_token,
        role: 'buyer',
        name: form.name.trim(),
        expires_at: res.expires_at,
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-dp-bg text-dp-text flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-xs font-mono text-dp-muted tracking-widest uppercase mb-2">Deal Room Invitation</p>
          <h2 className="text-xl font-semibold text-dp-text mb-1">
            {sellerName ? `${sellerName} invited you` : 'Join Deal Room'}
          </h2>
          <p className="text-sm text-dp-muted">Register as the buyer to join this negotiation.</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-dp-surface border border-dp-border rounded-lg p-6 space-y-4"
        >
          <div>
            <label className="block text-xs font-mono text-dp-muted tracking-wider mb-1.5 uppercase">
              Your Name <span className="text-dp-teal">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={set('name')}
              placeholder="Bob"
              required
              className="w-full bg-dp-bg border border-dp-border text-dp-text rounded px-3 py-2 text-sm
                         placeholder-dp-muted focus:outline-none focus:border-dp-teal transition-colors font-mono"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-dp-muted tracking-wider mb-1.5 uppercase">
              ETH Address
            </label>
            <input
              type="text"
              value={form.eth_address}
              onChange={set('eth_address')}
              placeholder="0x... (optional)"
              className="w-full bg-dp-bg border border-dp-border text-dp-text rounded px-3 py-2 text-sm
                         placeholder-dp-muted focus:outline-none focus:border-dp-teal transition-colors font-mono"
            />
          </div>

          {error && (
            <div className="bg-dp-red/10 border border-dp-red/40 text-dp-red text-xs font-mono rounded px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !form.name.trim()}
            className="w-full px-4 py-2.5 bg-dp-teal text-dp-bg font-mono font-semibold text-sm
                       rounded disabled:opacity-40 disabled:cursor-not-allowed hover:bg-opacity-90 transition-all"
          >
            {loading ? 'Joining…' : 'Join as Buyer →'}
          </button>
        </form>

        <p className="text-center text-xs text-dp-muted font-mono mt-4">
          Room ID: <span className="text-dp-text">{truncate(roomId, 20)}</span>
        </p>
      </div>
    </div>
  )
}

// ── Main WaitingRoom ────────────────────────────────────────────────────────

export default function WaitingRoom() {
  const { room_id } = useParams()
  const navigate = useNavigate()
  const { auth, saveAuth } = useAuth(room_id)

  const [status, setStatus] = useState(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [roomError, setRoomError] = useState(null)
  const [copied, setCopied] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getRoomStatus(room_id)
      setStatus(data)
      setRoomError(null)
    } catch (err) {
      setRoomError(err.message)
    } finally {
      setLoadingStatus(false)
    }
  }, [room_id])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 3000)
    return () => clearInterval(interval)
  }, [fetchStatus])

  // Auto-redirect both parties once seller has saved config
  useEffect(() => {
    if (auth && status && ['configuring', 'confirmed', 'running', 'complete'].includes(status.status)) {
      navigate(`/room/${room_id}/config`, { replace: true })
    }
  }, [status, auth, room_id, navigate])

  const handleCopyLink = () => {
    copyToClipboard(window.location.href)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleStartNegotiation = () => {
    navigate(`/room/${room_id}/config`)
  }

  // ── Loading ───────────────────────────────────────────────────────────────
  if (loadingStatus) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center">
        <div className="flex items-center gap-3 text-dp-muted font-mono text-sm">
          <div className="w-2 h-2 rounded-full bg-dp-teal animate-pulse" />
          Connecting…
        </div>
      </div>
    )
  }

  // ── Room not found ────────────────────────────────────────────────────────
  if (roomError || !status) {
    return (
      <div className="min-h-screen bg-dp-bg flex items-center justify-center px-4">
        <div className="text-center">
          <p className="text-dp-red font-mono text-sm mb-2">Room not found</p>
          <p className="text-dp-muted text-xs font-mono mb-6">{roomError}</p>
          <button
            onClick={() => navigate('/')}
            className="text-xs font-mono text-dp-teal hover:underline"
          >
            ← Back to home
          </button>
        </div>
      </div>
    )
  }

  // ── Not authenticated → buyer join form ───────────────────────────────────
  if (!auth) {
    if (status.status !== 'waiting') {
      return (
        <div className="min-h-screen bg-dp-bg flex items-center justify-center px-4">
          <div className="text-center">
            <p className="text-dp-muted font-mono text-sm mb-1">This room is no longer accepting participants.</p>
            <p className="text-xs text-dp-muted/60 font-mono">Status: {status.status}</p>
          </div>
        </div>
      )
    }
    return (
      <BuyerJoinForm
        sellerName={status.seller_name}
        roomId={room_id}
        onJoined={saveAuth}
      />
    )
  }

  // ── Authenticated waiting room ────────────────────────────────────────────
  const isSeller = auth.role === 'seller'
  const isReady  = status.status === 'ready'

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
        <span className="text-xs font-mono text-dp-muted">
          Room <span className="text-dp-text">{truncate(room_id, 20)}</span>
        </span>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-12 gap-8">

        {/* Status badge */}
        <StatusBadge status={status.status} />

        {/* Three-panel layout */}
        <div className="w-full max-w-3xl grid grid-cols-[1fr_auto_1fr] gap-4 items-center">

          {/* Seller panel */}
          <ParticipantPanel
            role="seller"
            name={status.seller_name}
            eth={status.seller_eth}
            isSelf={isSeller}
          />

          {/* Center divider */}
          <div className="flex flex-col items-center gap-2 px-2">
            <div className="w-px h-12 bg-dp-border" />
            <div className="w-2 h-2 rounded-full border border-dp-border bg-dp-surface" />
            <div className="w-px h-12 bg-dp-border" />
          </div>

          {/* Buyer panel */}
          <ParticipantPanel
            role="buyer"
            name={status.buyer_name}
            eth={status.buyer_eth}
            isSelf={!isSeller}
            empty={!status.buyer_name}
          />
        </div>

        {/* Actions */}
        <div className="flex flex-col items-center gap-3">
          {isSeller && (
            <button
              onClick={handleStartNegotiation}
              disabled={!isReady}
              className="px-8 py-3 bg-dp-teal text-dp-bg font-mono font-semibold text-sm rounded
                         disabled:opacity-30 disabled:cursor-not-allowed hover:bg-opacity-90
                         transition-all tracking-wide"
            >
              {isReady ? 'Start Negotiation →' : 'Waiting for Buyer…'}
            </button>
          )}

          {!isSeller && (
            <p className="text-sm text-dp-muted font-mono">
              {isReady ? 'Waiting for seller to start the negotiation…' : 'You have joined. Waiting for the seller…'}
            </p>
          )}

          <button
            onClick={handleCopyLink}
            className="flex items-center gap-2 text-xs font-mono text-dp-muted hover:text-dp-text transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            {copied ? 'Copied!' : 'Copy room link'}
          </button>
        </div>

        {/* Polling indicator */}
        <p className="text-xs font-mono text-dp-muted/50">Polling every 3s</p>
      </div>
    </div>
  )
}
