import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { offercheckConnectAts, offercheckListCompanySessions } from '../../api.js'

const STATE_LABEL = {
  PENDING_EMPLOYER: 'Awaiting band',
  EMPLOYER_RESPONDED: 'In progress',
  CANDIDATE_COUNTERED: 'In progress',
  AGREED: 'Agreed',
  WALKAWAY: 'Walked away',
  EXPIRED: 'Expired',
}

const STATE_COLOR = {
  AGREED: 'text-emerald-400',
  WALKAWAY: 'text-red-400',
  EXPIRED: 'text-gray-500',
}

export default function Dashboard() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('offercheck_api_key') || '')
  const [keyInput, setKeyInput] = useState('')
  const [sessions, setSessions] = useState(null)
  const [error, setError] = useState('')
  const [atsProvider, setAtsProvider] = useState('greenhouse')
  const [atsKey, setAtsKey] = useState('')
  const [atsStatus, setAtsStatus] = useState('')

  const refresh = async (key) => {
    try {
      const data = await offercheckListCompanySessions(key)
      setSessions(data.sessions)
      setError('')
    } catch (err) {
      setError(err.message || 'Could not load sessions')
      setSessions(null)
    }
  }

  useEffect(() => {
    if (apiKey) refresh(apiKey)
  }, [apiKey])

  const handleUseKey = (e) => {
    e.preventDefault()
    if (!keyInput.trim()) return
    localStorage.setItem('offercheck_api_key', keyInput.trim())
    setApiKey(keyInput.trim())
  }

  const handleConnectAts = async (e) => {
    e.preventDefault()
    setAtsStatus('')
    try {
      await offercheckConnectAts(apiKey, { provider: atsProvider, api_key: atsKey })
      setAtsStatus(`Connected to ${atsProvider}.`)
      setAtsKey('')
    } catch (err) {
      setAtsStatus(err.message || 'Could not connect')
    }
  }

  if (!apiKey) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
        <div className="w-full max-w-md mx-auto">
          <h1 className="text-2xl font-bold text-white mb-2">Company dashboard</h1>
          <p className="text-sm text-gray-500 mb-6">Paste your API key to view your verifications.</p>
          <form onSubmit={handleUseKey} className="flex gap-2 mb-4">
            <input
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="oc_..."
              className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm font-mono"
            />
            <button type="submit" className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium">
              Go
            </button>
          </form>
          <Link to="/offercheck/company/register" className="text-sm text-gray-500 hover:text-gray-300 underline">
            Don't have a key? Register your company
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-3.5rem)] px-4 py-10 sm:py-16">
      <div className="w-full max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-white">Company dashboard</h1>
          <button
            onClick={() => { localStorage.removeItem('offercheck_api_key'); setApiKey(''); setSessions(null) }}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Use a different key
          </button>
        </div>

        <div className="mb-6 p-4 rounded-xl bg-gray-900/40 border border-gray-800/40">
          <p className="text-sm font-medium text-gray-200 mb-3">Connect an ATS</p>
          <form onSubmit={handleConnectAts} className="flex flex-col sm:flex-row gap-2">
            <select
              value={atsProvider}
              onChange={(e) => setAtsProvider(e.target.value)}
              className="px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 text-sm"
            >
              <option value="greenhouse">Greenhouse</option>
              <option value="lever">Lever</option>
              <option value="workday">Workday</option>
            </select>
            <input
              value={atsKey}
              onChange={(e) => setAtsKey(e.target.value)}
              placeholder="ATS API key"
              className="flex-1 min-w-0 px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm"
            />
            <button type="submit" className="px-4 py-2 rounded-lg bg-gray-700/60 hover:bg-gray-600/60 text-gray-200 text-sm font-medium">
              Connect
            </button>
          </form>
          {atsStatus && <p className="text-xs text-gray-500 mt-2">{atsStatus}</p>}
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-red-950/40 border border-red-800/50 text-red-400 text-sm">{error}</div>
        )}

        <div className="rounded-xl bg-gray-900/40 border border-gray-800/40 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800/60 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-200">Verifications ({sessions?.length ?? 0})</span>
            <button onClick={() => refresh(apiKey)} className="text-xs text-gray-500 hover:text-gray-300">Refresh</button>
          </div>
          {sessions && sessions.length === 0 && (
            <p className="px-4 py-6 text-sm text-gray-500 italic">No verifications yet.</p>
          )}
          {sessions?.map((s) => (
            <div key={s.session_id} className="px-4 py-3 border-b border-gray-800/40 last:border-b-0 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className={`text-sm font-medium ${STATE_COLOR[s.state] || 'text-gray-300'}`}>
                  {STATE_LABEL[s.state] || s.state}
                </p>
                <p className="text-xs text-gray-600 font-mono truncate">{s.session_id}</p>
              </div>
              <div className="flex items-center gap-4 shrink-0">
                {s.gap_pct != null && (
                  <span className="text-xs font-mono text-gray-400">{s.gap_pct > 0 ? '+' : ''}{s.gap_pct.toFixed(1)}%</span>
                )}
                <span className="text-xs text-gray-600">round {s.round_number}</span>
                <a
                  href={s.employer_link}
                  className="text-xs text-emerald-400 hover:text-emerald-300 underline"
                >
                  Open
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
