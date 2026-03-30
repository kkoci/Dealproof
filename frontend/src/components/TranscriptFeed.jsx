import React, { useEffect, useRef } from 'react'

const ACTION_COLORS = {
  offer: 'bg-indigo-700/60 text-indigo-300 border-indigo-600/40',
  counter: 'bg-violet-700/60 text-violet-300 border-violet-600/40',
  accept: 'bg-emerald-700/60 text-emerald-300 border-emerald-600/40',
  reject: 'bg-red-700/60 text-red-300 border-red-600/40',
  counteroffer: 'bg-violet-700/60 text-violet-300 border-violet-600/40',
}

function ActionBadge({ action }) {
  const normalized = action?.toLowerCase() || 'offer'
  const colorClass = ACTION_COLORS[normalized] || 'bg-gray-700/60 text-gray-300 border-gray-600/40'
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-md text-xs font-mono font-medium border uppercase tracking-wider ${colorClass}`}
    >
      {action}
    </span>
  )
}

function TranscriptRound({ round }) {
  const isSeller = round.role === 'seller'

  return (
    <div className={`flex ${isSeller ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 border shadow-lg ${
          isSeller
            ? 'bg-blue-950/70 border-blue-800/40 rounded-tr-sm'
            : 'bg-emerald-950/70 border-emerald-800/40 rounded-tl-sm'
        }`}
      >
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span
            className={`text-xs font-semibold uppercase tracking-widest ${
              isSeller ? 'text-blue-400' : 'text-emerald-400'
            }`}
          >
            {round.role}
          </span>
          <span className="text-gray-600 text-xs">·</span>
          <span className="text-gray-500 text-xs font-mono">Round {round.round}</span>
          <ActionBadge action={round.action} />
        </div>

        {round.price != null && (
          <div className="mb-2">
            <span
              className={`text-2xl font-bold font-mono ${
                isSeller ? 'text-blue-200' : 'text-emerald-200'
              }`}
            >
              ${Number(round.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        )}

        {round.terms && Object.keys(round.terms).length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {Object.entries(round.terms).map(([k, v]) => (
              <span
                key={k}
                className="text-xs px-2 py-0.5 rounded bg-gray-800/60 border border-gray-700/40 text-gray-300 font-mono"
              >
                {k}: <span className="text-gray-100">{String(v)}</span>
              </span>
            ))}
          </div>
        )}

        {round.reasoning && (
          <p className="text-sm text-gray-300 leading-relaxed mt-1 italic">
            &ldquo;{round.reasoning}&rdquo;
          </p>
        )}
      </div>
    </div>
  )
}

export default function TranscriptFeed({ transcript = [], isLive = false }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [transcript.length])

  if (!transcript || transcript.length === 0) {
    if (!isLive) return null
    return (
      <div className="flex items-center justify-center py-12 text-gray-500">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm">Waiting for negotiation to begin...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-3 mb-4 pb-3 border-b border-gray-800/60">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">
          Negotiation Transcript
        </h3>
        <span className="text-xs text-gray-500 font-mono bg-gray-800/50 px-2 py-0.5 rounded border border-gray-700/50">
          {transcript.length} round{transcript.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div className="space-y-1">
        {transcript.map((round, idx) => (
          <TranscriptRound key={`${round.round}-${idx}`} round={round} />
        ))}
      </div>

      {isLive && (
        <div className="flex items-center gap-2 mt-4 pl-2">
          <span className="inline-flex gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '300ms' }} />
          </span>
          <span className="text-xs text-indigo-400 font-mono animate-pulse">Negotiating inside TEE...</span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
