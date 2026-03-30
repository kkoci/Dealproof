import React, { useEffect, useState, useRef, useCallback } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import { getDealStatus, getDcapVerification, getDealVerification } from '../api.js'
import TranscriptFeed from '../components/TranscriptFeed.jsx'
import AttestationCard from '../components/AttestationCard.jsx'
import StatusBadge from '../components/StatusBadge.jsx'

const TERMINAL_STATUSES = new Set(['agreed', 'failed', 'verification_failed'])
const POLL_INTERVAL_MS = 2000

function DkimBadge({ dkim }) {
  if (!dkim || !dkim.domain) return null

  if (dkim.verified) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-emerald-950/40 border border-emerald-800/50">
        <svg className="w-5 h-5 text-emerald-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
        </svg>
        <div>
          <div className="text-sm font-semibold text-emerald-300">Seller Identity Verified</div>
          <div className="text-xs text-emerald-500 font-mono">✓ {dkim.domain} (DKIM)</div>
        </div>
      </div>
    )
  }

  if (dkim.dns_unavailable) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-yellow-950/40 border border-yellow-800/50">
        <svg className="w-5 h-5 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
        <div>
          <div className="text-sm font-semibold text-yellow-300">DNS Unavailable in TEE</div>
          <div className="text-xs text-yellow-500 font-mono">⚠ Domain: {dkim.domain} (DNS unavailable)</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-red-950/40 border border-red-800/50">
      <svg className="w-5 h-5 text-red-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
      <div>
        <div className="text-sm font-semibold text-red-300">DKIM Verification Failed</div>
        <div className="text-xs text-red-500 font-mono">✗ {dkim.domain}{dkim.error ? ` — ${dkim.error}` : ''}</div>
      </div>
    </div>
  )
}

function TermsTable({ terms }) {
  if (!terms || Object.keys(terms).length === 0) return null

  return (
    <div className="rounded-lg border border-gray-800/60 bg-gray-950/50 overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-800/40 bg-gray-900/40">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Agreed Terms</span>
      </div>
      <table className="w-full text-sm">
        <tbody>
          {Object.entries(terms).map(([key, value]) => (
            <tr key={key} className="border-b border-gray-800/30 last:border-0">
              <td className="px-3 py-2.5 text-gray-500 text-xs font-medium capitalize w-40">
                {key.replace(/_/g, ' ')}
              </td>
              <td className="px-3 py-2.5 text-gray-200 text-sm font-mono">
                {String(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PropsVerificationPanel({ dealId }) {
  const [propsData, setPropsData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getDealVerification(dealId)
      .then((d) => { if (!cancelled) setPropsData(d.verification) })
      .catch(() => { /* no seller_proof — silently skip */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [dealId])

  if (loading || !propsData) return null

  const verified = propsData.verified === true

  return (
    <div className={`rounded-xl border overflow-hidden ${verified ? 'border-emerald-800/50 bg-emerald-950/20' : 'border-red-800/50 bg-red-950/20'}`}>
      <div className={`px-4 py-3 border-b flex items-center gap-2 ${verified ? 'border-emerald-800/40 bg-emerald-950/30' : 'border-red-800/40 bg-red-950/30'}`}>
        <svg className={`w-4 h-4 ${verified ? 'text-emerald-400' : 'text-red-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
        <span className={`text-sm font-semibold ${verified ? 'text-emerald-300' : 'text-red-300'}`}>
          Props Data Verification
        </span>
        <span className={`ml-auto text-xs font-mono px-2 py-0.5 rounded-full border ${verified ? 'bg-emerald-900/40 border-emerald-700/50 text-emerald-300' : 'bg-red-900/40 border-red-700/50 text-red-300'}`}>
          {verified ? '✓ VERIFIED' : '✗ FAILED'}
        </span>
      </div>

      <div className="px-4 py-3 space-y-2 text-xs">
        {verified && (
          <p className="text-emerald-400 text-sm">
            Dataset cryptographically verified inside Intel TDX enclave using Merkle proof.
            The data hash is bound into the same attestation as the negotiation outcome.
          </p>
        )}
        {propsData.data_hash && (
          <div className="flex gap-2 items-center">
            <span className="text-gray-500 w-24 flex-shrink-0">Data Hash</span>
            <code className="font-mono text-gray-300 bg-gray-950/60 rounded px-2 py-1 border border-gray-800/60 break-all">{propsData.data_hash}</code>
          </div>
        )}
        {propsData.chunk_count != null && (
          <div className="flex gap-2 items-center">
            <span className="text-gray-500 w-24 flex-shrink-0">Chunks</span>
            <span className="text-gray-200">{propsData.chunk_count} verified</span>
          </div>
        )}
        {propsData.attestation && (
          <div className="flex gap-2 items-start">
            <span className="text-gray-500 w-24 flex-shrink-0 pt-1">Props Quote</span>
            <code className="font-mono text-gray-400 text-xs bg-gray-950/60 rounded px-2 py-1 border border-gray-800/60 break-all">{propsData.attestation.slice(0, 40)}...</code>
          </div>
        )}
        {propsData.error && (
          <p className="text-red-400">{propsData.error}</p>
        )}
      </div>
    </div>
  )
}

function ResultPanel({ result, dealId }) {
  const [dcapData, setDcapData] = useState(null)
  const [dcapLoading, setDcapLoading] = useState(false)
  const [dcapError, setDcapError] = useState(null)

  async function handleInspectDcap() {
    if (dcapLoading) return
    setDcapLoading(true)
    setDcapError(null)
    try {
      const data = await getDcapVerification(dealId)
      setDcapData(data)
    } catch (err) {
      setDcapError(err.message)
    } finally {
      setDcapLoading(false)
    }
  }

  if (!result) return null

  const agreed = result.agreed

  return (
    <div className="space-y-5">
      {/* Big outcome badge */}
      <div
        className={`flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-xl border ${
          agreed
            ? 'bg-emerald-950/30 border-emerald-800/50'
            : 'bg-red-950/30 border-red-800/50'
        }`}
      >
        <div className="flex items-center gap-3">
          {agreed ? (
            <div className="w-10 h-10 rounded-full bg-emerald-900/60 flex items-center justify-center">
              <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
          ) : (
            <div className="w-10 h-10 rounded-full bg-red-900/60 flex items-center justify-center">
              <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
          )}
          <div>
            <div
              className={`text-xl font-bold tracking-tight ${
                agreed ? 'text-emerald-300' : 'text-red-300'
              }`}
            >
              {agreed ? 'DEAL AGREED' : 'DEAL FAILED'}
            </div>
            <div className="text-xs text-gray-500 font-mono mt-0.5">
              ID: {result.deal_id}
            </div>
          </div>
        </div>

        {agreed && result.final_price != null && (
          <div className="text-right">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Final Price</div>
            <div className="text-3xl font-bold font-mono text-emerald-300">
              ${Number(result.final_price).toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </div>
          </div>
        )}
      </div>

      {/* Terms */}
      {agreed && result.terms && <TermsTable terms={result.terms} />}

      {/* Props data verification — DealProof's unique feature */}
      <PropsVerificationPanel dealId={dealId} />

      {/* DKIM seller identity */}
      {result.dkim_verification && (
        <DkimBadge dkim={result.dkim_verification} />
      )}

      {/* Attestation */}
      {result.attestation && (
        <AttestationCard
          attestation={result.attestation}
          dealId={dealId}
          onInspect={handleInspectDcap}
          dcapData={dcapData}
          dcapLoading={dcapLoading}
        />
      )}

      {/* DCAP error */}
      {dcapError && (
        <p className="text-xs text-red-400 font-mono bg-red-950/20 border border-red-800/40 rounded-lg px-3 py-2">
          DCAP error: {dcapError}
        </p>
      )}

      {/* Escrow info */}
      {(result.escrow_tx || result.completion_tx) && (
        <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 p-4 space-y-2">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">On-chain Escrow</h3>
          {result.escrow_tx && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-28">Escrow TX</span>
              <code className="text-xs font-mono text-indigo-400">{result.escrow_tx}</code>
            </div>
          )}
          {result.completion_tx && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 w-28">Completion TX</span>
              <code className="text-xs font-mono text-indigo-400">{result.completion_tx}</code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function DealView() {
  const { id } = useParams()
  const location = useLocation()

  const [status, setStatus] = useState(null)
  const [result, setResult] = useState(location.state?.result || null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isPolling, setIsPolling] = useState(false)

  const pollRef = useRef(null)
  const isMounted = useRef(true)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getDealStatus(id)
      if (!isMounted.current) return

      setStatus(data.status)
      if (data.result) {
        setResult(data.result)
      }
      setError(null)

      // Stop polling if terminal status
      if (TERMINAL_STATUSES.has(data.status)) {
        setIsPolling(false)
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
        }
      }
    } catch (err) {
      if (!isMounted.current) return
      setError(err.message || 'Failed to load deal status')
    } finally {
      if (isMounted.current) {
        setLoading(false)
      }
    }
  }, [id])

  useEffect(() => {
    isMounted.current = true

    // If we arrived here with a complete result (from CreateDeal navigation),
    // don't poll — just use what we have
    if (location.state?.result) {
      const r = location.state.result
      setResult(r)
      setStatus(r.agreed ? 'agreed' : 'failed')
      setLoading(false)
      return
    }

    fetchStatus()

    return () => {
      isMounted.current = false
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [id])

  // Start polling when status is negotiating/pending
  useEffect(() => {
    if (status && !TERMINAL_STATUSES.has(status) && !pollRef.current) {
      setIsPolling(true)
      pollRef.current = setInterval(fetchStatus, POLL_INTERVAL_MS)
    }
    return () => {
      // cleanup handled by mount/unmount effect
    }
  }, [status, fetchStatus])

  const transcript = result?.transcript || []
  const isLive = isPolling && !TERMINAL_STATUSES.has(status)

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <Link to="/" className="hover:text-gray-400 transition-colors">dealproof</Link>
            <span>/</span>
            <Link to="/" className="hover:text-gray-400 transition-colors">deals</Link>
            <span>/</span>
            <span className="text-gray-400 truncate max-w-[200px]">{id}</span>
          </div>

          <div className="flex items-center justify-between gap-4 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-100">Deal View</h1>
            {status && <StatusBadge status={status} />}
          </div>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-gray-500 text-sm">Loading deal...</p>
          </div>
        )}

        {/* Error state */}
        {!loading && error && (
          <div className="flex items-start gap-3 px-4 py-4 rounded-xl bg-red-950/30 border border-red-800/50">
            <svg className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div>
              <p className="text-sm font-medium text-red-300">Failed to load deal</p>
              <p className="text-xs text-red-400/80 mt-0.5">{error}</p>
              <button
                onClick={() => { setLoading(true); setError(null); fetchStatus() }}
                className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 underline"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {!loading && !error && (
          <div className="space-y-8">

            {/* Live negotiating banner */}
            {isLive && (
              <div className="flex items-center gap-3 px-4 py-3.5 rounded-xl bg-blue-950/30 border border-blue-800/50">
                <div className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-blue-300">Agents negotiating inside TEE</p>
                  <p className="text-xs text-blue-500 mt-0.5">
                    Polling for updates every 2 seconds. This may take 20–60 seconds total.
                  </p>
                </div>
              </div>
            )}

            {/* Final result panel */}
            {result && TERMINAL_STATUSES.has(status) && (
              <ResultPanel result={result} dealId={id} />
            )}

            {/* Transcript */}
            {(transcript.length > 0 || isLive) && (
              <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 p-5">
                <TranscriptFeed transcript={transcript} isLive={isLive} />
              </div>
            )}

            {/* Empty state for pending */}
            {!result && !isLive && status === 'pending' && (
              <div className="text-center py-16">
                <div className="w-12 h-12 rounded-xl bg-gray-800/60 flex items-center justify-center mx-auto mb-4">
                  <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="text-gray-500 text-sm">Deal is pending. Negotiation has not started yet.</p>
              </div>
            )}

            {/* No data at all */}
            {!result && !isLive && !status && !loading && !error && (
              <div className="text-center py-16">
                <p className="text-gray-500 text-sm">No data found for this deal ID.</p>
                <Link to="/" className="mt-3 inline-block text-indigo-400 hover:text-indigo-300 text-sm underline">
                  Go home
                </Link>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  )
}
