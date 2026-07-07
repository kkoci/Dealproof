import React, { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { offercheckEmployerMove, offercheckGetAttestation, offercheckGetCredential, offercheckGetSession, offercheckSetEmployerBand } from '../../api.js'

const POLL_MS = 3000

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Your turn',
  EMPLOYER_RESPONDED: 'Waiting for the candidate',
  CANDIDATE_COUNTERED: 'Your turn',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired — no agreement reached',
}

const inputClass =
  'w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500/50 transition-all'
const labelClass = 'block text-xs font-medium text-gray-400 mb-1.5'

function GapMeter({ gapPct }) {
  if (gapPct === null || gapPct === undefined) return null
  const clamped = Math.max(-50, Math.min(50, gapPct))
  const pos = ((clamped + 50) / 100) * 100
  return (
    <div className="mb-6">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-xs text-gray-500">Gap: candidate's ask vs. your current position</span>
        <span className={`text-lg font-mono font-semibold ${gapPct > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
          {gapPct > 0 ? '+' : ''}{gapPct.toFixed(1)}%
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-gray-800/80">
        <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-600" />
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-emerald-400 shadow shadow-emerald-900/60"
          style={{ left: `calc(${pos}% - 6px)` }}
        />
      </div>
    </div>
  )
}

function AttestationPanel({ sessionId, token, visible }) {
  const [receipt, setReceipt] = useState(null)
  const [cred, setCred] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!visible) return
    let cancelled = false
    offercheckGetAttestation(sessionId, token)
      .then((data) => { if (!cancelled) setReceipt(data) })
      .catch((e) => { if (!cancelled) setErr(e.message || 'Attestation not available yet') })
    offercheckGetCredential(sessionId, { token }).then((data) => { if (!cancelled) setCred(data) }).catch(() => {})
    return () => { cancelled = true }
  }, [sessionId, token, visible])

  if (!visible) return null

  return (
    <div className="mt-4 p-4 rounded-xl bg-gray-900/40 border border-gray-800/40">
      {receipt ? (
        <>
          <div className="flex items-center gap-2 mb-2">
            <span className="relative flex h-2 w-2">
              <span className={`relative inline-flex rounded-full h-2 w-2 ${receipt.tee_attested ? 'bg-emerald-400' : 'bg-yellow-400'}`} />
            </span>
            <span className="text-xs font-semibold text-gray-200">
              {receipt.tee_attested
                ? 'Verified by hardware attestation'
                : 'Simulation mode — no real TEE hardware'}
            </span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed mb-2">
            This verification ran inside a TDX enclave. Neither party's raw data was observable by the platform.
          </p>
          <p className="text-[11px] font-mono text-gray-600 break-all mb-3">{receipt.attestation}</p>
          {cred && (
            <div className="pt-3 border-t border-gray-800/60">
              <span className={`text-xs font-semibold ${cred.genuine_negotiation ? 'text-emerald-400' : 'text-amber-400'}`}>
                {cred.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
              </span>
              <p className="text-xs text-gray-500 mt-1">{cred.summary}</p>
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-gray-500 italic">{err || 'Loading attestation receipt…'}</p>
      )}
    </div>
  )
}

export default function EmployerSession() {
  const { sessionId } = useParams()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [view, setView] = useState(null)
  const [error, setError] = useState('')
  const [band, setBand] = useState({ band_min: '', band_mid: '', band_max: '' })
  const [bandGap, setBandGap] = useState(null)
  const [counterValue, setCounterValue] = useState('')
  const [acting, setActing] = useState(false)
  const pollRef = useRef(null)

  const refresh = async () => {
    try {
      const data = await offercheckGetSession(sessionId, token)
      setView(data)
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load session')
    }
  }

  useEffect(() => {
    refresh()
    pollRef.current = setInterval(refresh, POLL_MS)
    return () => clearInterval(pollRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, token])

  const isTerminal = view && ['AGREED', 'WALKAWAY', 'EXPIRED'].includes(view.state)
  const myTurn = view && view.turn === 'employer'

  const submitBand = async (e) => {
    e.preventDefault()
    setError('')
    setActing(true)
    try {
      const result = await offercheckSetEmployerBand(sessionId, {
        employer_token: token,
        band_min: Number(band.band_min),
        band_mid: Number(band.band_mid),
        band_max: Number(band.band_max),
      })
      setBandGap(result.gap_pct)
      await refresh()
    } catch (err) {
      setError(err.message || 'Could not submit band')
    } finally {
      setActing(false)
    }
  }

  const act = async (move, value) => {
    setActing(true)
    setError('')
    try {
      const data = await offercheckEmployerMove(sessionId, { token, move, value: value ?? null })
      setView(data)
    } catch (err) {
      setError(err.message || 'Move failed')
    } finally {
      setActing(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-lg mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Competing offer verification</h1>
        <p className="text-sm text-gray-500 mb-8">
          Your band stays private. You'll only ever see the gap percentage.
        </p>

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-red-950/40 border border-red-800/50 text-red-400 text-sm">{error}</div>
        )}

        {view && !view.band_set && (
          <form onSubmit={submitBand} className="p-5 rounded-xl bg-gray-900/40 border border-gray-800/40 space-y-4">
            <div>
              <label className={labelClass}>Band minimum</label>
              <input className={inputClass} type="number" min="0" value={band.band_min} onChange={(e) => setBand((b) => ({ ...b, band_min: e.target.value }))} placeholder="155000" required />
            </div>
            <div>
              <label className={labelClass}>Band midpoint</label>
              <input className={inputClass} type="number" min="0" value={band.band_mid} onChange={(e) => setBand((b) => ({ ...b, band_mid: e.target.value }))} placeholder="175000" required />
            </div>
            <div>
              <label className={labelClass}>Band maximum</label>
              <input className={inputClass} type="number" min="0" value={band.band_max} onChange={(e) => setBand((b) => ({ ...b, band_max: e.target.value }))} placeholder="195000" required />
            </div>
            <button
              type="submit"
              disabled={acting}
              className="w-full px-6 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all disabled:opacity-50"
            >
              {acting ? 'Checking…' : 'See the gap'}
            </button>
          </form>
        )}

        {view && view.band_set && (
          <div className="p-5 rounded-xl bg-gray-900/40 border border-gray-800/40">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-semibold text-gray-200">{STATE_LABEL[view.state] || view.state}</span>
              <span className="text-xs font-mono text-gray-500">round {view.round_number} / {view.max_rounds}</span>
            </div>

            <GapMeter gapPct={bandGap ?? view.gap_pct} />

            {view.my_current_value != null && (
              <p className="text-xs text-gray-500 mb-4">
                Your current offer: <span className="font-mono text-gray-300">${view.my_current_value.toLocaleString()}</span>
              </p>
            )}

            {view.state === 'AGREED' && (
              <p className="text-sm text-emerald-400 font-medium mb-4">
                Agreed at ${view.agreed_price?.toLocaleString()}
              </p>
            )}

            {view.history.length > 0 && (
              <div className="mb-4 space-y-1.5">
                {view.history.map((h) => (
                  <div key={h.round_number} className="flex items-center justify-between text-xs text-gray-500">
                    <span>Round {h.round_number} — {h.actor}</span>
                    <span className="font-mono uppercase text-gray-400">{h.move}</span>
                  </div>
                ))}
              </div>
            )}

            {!isTerminal && !myTurn && (
              <p className="text-xs text-gray-500 italic">Waiting for the candidate to respond…</p>
            )}

            {!isTerminal && myTurn && (
              <div className="space-y-3 pt-3 border-t border-gray-800/60">
                <div className="flex gap-2">
                  <input
                    type="number"
                    min="0"
                    value={counterValue}
                    onChange={(e) => setCounterValue(e.target.value)}
                    placeholder="New offer"
                    className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm"
                  />
                  <button
                    disabled={acting || !counterValue}
                    onClick={() => act('counter', Number(counterValue))}
                    className="px-4 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-sm font-medium disabled:opacity-40"
                  >
                    Counter
                  </button>
                </div>
                <div className="flex gap-2">
                  <button
                    disabled={acting}
                    onClick={() => act('accept')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold disabled:opacity-40"
                  >
                    Meet the gap
                  </button>
                  <button
                    disabled={acting}
                    onClick={() => act('walk')}
                    className="flex-1 px-4 py-2.5 rounded-lg bg-red-950/60 hover:bg-red-900/60 border border-red-800/50 text-red-300 text-sm font-semibold disabled:opacity-40"
                  >
                    Decline
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        <AttestationPanel sessionId={sessionId} token={token} visible={Boolean(isTerminal)} />
      </div>
    </div>
  )
}
