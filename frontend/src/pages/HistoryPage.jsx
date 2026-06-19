import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRoomStatus } from '../api/roomApi.js'

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

const STATUS_COLORS = {
  waiting:     'text-dp-muted   border-dp-border',
  ready:       'text-dp-teal    border-dp-teal/40',
  configuring: 'text-dp-amber   border-dp-amber/40',
  confirmed:   'text-dp-amber   border-dp-amber/40',
  running:     'text-dp-teal    border-dp-teal/40',
  complete:    'text-dp-teal    border-dp-teal/40',
  failed:      'text-dp-red     border-dp-red/40',
}

function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || 'text-dp-muted border-dp-border'
  return (
    <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${color} uppercase`}>
      {status}
    </span>
  )
}

// ── RoomCard ───────────────────────────────────────────────────────────────

function RoomCard({ room_id, room, role, navigate }) {
  const statusText = room?.status ?? 'loading'
  const sellerName = room?.seller_name || '—'
  const buyerName  = room?.buyer_name  || 'Awaiting buyer'
  const createdAt  = room?.created_at
  const dealId     = room?.deal_id
  const isComplete = statusText === 'complete'
  const isRunning  = statusText === 'running' || statusText === 'confirmed'

  return (
    <div className="bg-dp-surface border border-dp-border rounded-lg p-5 hover:border-dp-teal/40 transition-colors">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusBadge status={statusText} />
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded border uppercase ${
            role === 'seller'
              ? 'text-dp-teal border-dp-teal/30 bg-dp-teal/5'
              : 'text-dp-amber border-dp-amber/30 bg-dp-amber/5'
          }`}>
            {role}
          </span>
        </div>
        <span className="text-xs font-mono text-dp-muted/60 shrink-0">{fmtDate(createdAt)}</span>
      </div>

      <div className="mb-4 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-dp-muted w-14">SELLER</span>
          <span className="text-sm text-dp-text">{sellerName}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-dp-muted w-14">BUYER</span>
          <span className={`text-sm ${buyerName === 'Awaiting buyer' ? 'text-dp-muted italic' : 'text-dp-text'}`}>
            {buyerName}
          </span>
        </div>
        {dealId && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-dp-muted w-14">DEAL</span>
            <span className="text-xs font-mono text-dp-muted/70 truncate">{dealId.slice(0, 20)}…</span>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        {isComplete && dealId && (
          <button
            onClick={() => navigate(`/verify/${dealId}`)}
            className="flex-1 text-xs font-mono py-2 rounded border border-dp-teal/50
                       text-dp-teal hover:bg-dp-teal/10 transition-colors"
          >
            View Credential →
          </button>
        )}
        {isRunning && (
          <button
            onClick={() => navigate(`/room/${room_id}/negotiate`)}
            className="flex-1 text-xs font-mono py-2 rounded border border-dp-amber/50
                       text-dp-amber hover:bg-dp-amber/10 transition-colors"
          >
            Rejoin Negotiation →
          </button>
        )}
        {!isComplete && !isRunning && (
          <button
            onClick={() => navigate(`/room/${room_id}`)}
            className="flex-1 text-xs font-mono py-2 rounded border border-dp-border
                       text-dp-muted hover:border-dp-text hover:text-dp-text transition-colors"
          >
            Open Room →
          </button>
        )}
      </div>
    </div>
  )
}

// ── Main HistoryPage ────────────────────────────────────────────────────────

export default function HistoryPage() {
  const navigate = useNavigate()
  const [rooms, setRooms] = useState([])    // [{room_id, role, status, ...}]
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadHistory() {
      // Collect all room tokens from localStorage
      const entries = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (!key?.startsWith('dp_auth_')) continue
        const room_id = key.replace('dp_auth_', '')
        try {
          const stored = JSON.parse(localStorage.getItem(key))
          if (!stored?.token) continue
          // Skip expired tokens
          if (stored.expires_at && stored.expires_at * 1000 < Date.now()) continue
          entries.push({ room_id, token: stored.token, role: stored.role || 'seller' })
        } catch {
          // ignore malformed entries
        }
      }

      if (entries.length === 0) {
        setLoading(false)
        return
      }

      // Fetch status for each room in parallel
      const results = await Promise.allSettled(
        entries.map(async ({ room_id, role }) => {
          const status = await getRoomStatus(room_id)
          return { room_id, role, ...status }
        })
      )

      const loaded = results
        .filter(r => r.status === 'fulfilled')
        .map(r => r.value)
        .sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0
          return tb - ta  // newest first
        })

      setRooms(loaded)
      setLoading(false)
    }

    loadHistory()
  }, [])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-dp-bg text-dp-text flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-dp-border shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="text-xs font-mono text-dp-muted hover:text-dp-teal transition-colors"
          >
            ← Back
          </button>
          <div className="h-4 w-px bg-dp-border" />
          <span className="text-sm font-mono text-dp-muted tracking-widest uppercase">Deal History</span>
        </div>
        <button
          onClick={() => navigate('/')}
          className="text-xs font-mono text-dp-teal hover:underline"
        >
          New Deal →
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        {loading ? (
          <div className="flex items-center gap-3 text-dp-muted font-mono text-sm">
            <span className="w-2 h-2 rounded-full bg-dp-teal animate-pulse" />
            Loading history…
          </div>
        ) : rooms.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center py-24 text-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-dp-surface border border-dp-border flex items-center justify-center">
              <svg className="w-6 h-6 text-dp-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-dp-muted font-mono text-sm">No deals yet.</p>
            <button
              onClick={() => navigate('/')}
              className="text-xs font-mono text-dp-teal hover:underline"
            >
              Start one →
            </button>
          </div>
        ) : (
          <>
            <p className="text-xs font-mono text-dp-muted mb-5">
              {rooms.length} room{rooms.length !== 1 ? 's' : ''} found on this device
            </p>
            <div className="space-y-3">
              {rooms.map(r => (
                <RoomCard
                  key={r.room_id}
                  room_id={r.room_id}
                  room={r}
                  role={r.role}
                  navigate={navigate}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
