import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { offercheckStartAgentic, offercheckVerifyDemoToken } from '../../api.js'

export default function Demo() {
  const [searchParams] = useSearchParams()
  // Read once from the URL and keep in component memory only — never localStorage,
  // per the magic-link design: these links are short-lived and single-use.
  const [token] = useState(() => searchParams.get('token') || '')
  const [sessionId] = useState(() => searchParams.get('session') || '')

  const [checking, setChecking] = useState(true)
  const [valid, setValid] = useState(false)
  const [checkError, setCheckError] = useState('')

  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [runError, setRunError] = useState('')

  useEffect(() => {
    if (!token || !sessionId) {
      setChecking(false)
      setCheckError('This link is missing its token or session — ask for a new one.')
      return
    }
    let cancelled = false
    offercheckVerifyDemoToken(token, sessionId)
      .then((data) => { if (!cancelled) setValid(Boolean(data.valid)) })
      .catch((e) => { if (!cancelled) setCheckError(e.message || 'Demo link expired — request a new one') })
      .finally(() => { if (!cancelled) setChecking(false) })
    return () => { cancelled = true }
  }, [token, sessionId])

  const run = async () => {
    setRunning(true)
    setRunError('')
    try {
      const data = await offercheckStartAgentic(sessionId, { demoToken: token })
      setResult(data)
    } catch (e) {
      setRunError(e.message || 'Agentic negotiation failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-lg mx-auto">
        <h1 className="text-2xl sm:text-3xl font-bold text-white mb-2">Offer Check — live demo</h1>
        <p className="text-sm text-gray-500 mb-8">
          Two Claude agents negotiate a salary inside a TEE-attested revision loop. No login, no account.
        </p>

        {checking && <p className="text-sm text-gray-500 italic">Checking your link…</p>}

        {!checking && !valid && (
          <div className="p-5 rounded-xl bg-red-950/40 border border-red-800/50">
            <p className="text-sm font-semibold text-red-300 mb-1">Demo link expired — request a new one</p>
            <p className="text-xs text-red-400/80">{checkError}</p>
          </div>
        )}

        {!checking && valid && !result && (
          <div className="p-5 rounded-xl bg-gray-900/40 border border-emerald-800/30">
            <p className="text-sm font-medium text-gray-200 mb-1">Ready to negotiate</p>
            <p className="text-xs text-gray-500 mb-4">
              This link is valid and single-use. Clicking below runs the full negotiation —
              sealed floor and band never cross between agents, only offer amounts and moves do.
            </p>
            <button
              onClick={run}
              disabled={running}
              className="w-full px-4 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition-all disabled:opacity-50"
            >
              {running ? 'Agents negotiating…' : 'Let agents negotiate'}
            </button>
            {runError && <p className="text-xs text-red-400 mt-2">{runError}</p>}
          </div>
        )}

        {result && (
          <div className="p-5 rounded-xl bg-gray-900/40 border border-emerald-800/30">
            <p className="text-sm font-semibold text-gray-200 mb-3">
              {result.state === 'AGREED'
                ? `Agreed at $${result.agreed_price?.toLocaleString()}`
                : result.state === 'WALKAWAY'
                  ? 'Agents walked away'
                  : 'Agents ran out of rounds'}
            </p>
            <div className="space-y-1.5 mb-4">
              {result.transcript.map((r) => (
                <div key={r.round} className="flex items-center justify-between text-xs text-gray-500">
                  <span>Round {r.round} — {r.actor}</span>
                  <span className="font-mono text-gray-400">
                    {r.move.toUpperCase()}{r.value != null ? ` $${r.value.toLocaleString()}` : ''}
                  </span>
                </div>
              ))}
            </div>
            {result.credential && (
              <div className="pt-3 border-t border-gray-800/60 mb-3">
                <span className={`text-xs font-semibold ${result.credential.genuine_negotiation ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {result.credential.genuine_negotiation ? 'Genuine negotiation verified' : 'Conduct issues detected'}
                </span>
                <p className="text-xs text-gray-500 mt-1">{result.credential.summary}</p>
              </div>
            )}
            <p className="text-[11px] font-mono text-gray-600 break-all">{result.attestation}</p>
          </div>
        )}
      </div>
    </div>
  )
}
