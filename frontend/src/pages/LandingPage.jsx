import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { registerSeller } from '../api/roomApi.js'

function LockIcon() {
  return (
    <svg className="w-7 h-7 text-dp-teal" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
        d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
    </svg>
  )
}

function TrustFooter() {
  const layers = ['TDX ENCLAVE', 'DCAP ATTESTATION', 'CONTEXTO MEMORY', 'πCREDS CONDUCT']
  return (
    <div className="border-t border-dp-border py-4 px-6 flex items-center justify-center gap-2 flex-wrap">
      {layers.map((l, i) => (
        <React.Fragment key={l}>
          <span className="text-xs font-mono text-dp-muted tracking-widest">{l}</span>
          {i < layers.length - 1 && (
            <span className="text-dp-border text-xs">·</span>
          )}
        </React.Fragment>
      ))}
    </div>
  )
}

function InputField({ label, type = 'text', value, onChange, placeholder, required, hint }) {
  return (
    <div>
      <label className="block text-xs font-mono text-dp-muted tracking-wider mb-1.5 uppercase">
        {label}{required && <span className="text-dp-teal ml-1">*</span>}
      </label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        className="w-full bg-dp-bg border border-dp-border text-dp-text rounded px-3 py-2 text-sm
                   placeholder-dp-muted focus:outline-none focus:border-dp-teal transition-colors font-mono"
      />
      {hint && <p className="text-xs text-dp-muted mt-1">{hint}</p>}
    </div>
  )
}

export default function LandingPage() {
  const navigate = useNavigate()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', eth_address: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleCreate = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await registerSeller({
        name: form.name.trim(),
        email: form.email.trim(),
        eth_address: form.eth_address.trim() || undefined,
      })
      localStorage.setItem(`dp_auth_${res.room_id}`, JSON.stringify({
        token: res.seller_token,
        role: 'seller',
        name: form.name.trim(),
        expires_at: res.expires_at,
      }))
      navigate(`/room/${res.room_id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-dp-bg text-dp-text flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-dp-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-dp-surface border border-dp-border flex items-center justify-center">
            <LockIcon />
          </div>
          <span className="font-semibold tracking-tight text-dp-text">DealProof</span>
        </div>
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-mono text-dp-muted hover:text-dp-text transition-colors"
        >
          API DOCS ↗
        </a>
      </div>

      {/* Hero */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-16 text-center">
        <div className="w-14 h-14 rounded-2xl bg-dp-surface border border-dp-border flex items-center justify-center mb-8 shadow-lg">
          <LockIcon />
        </div>

        <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-dp-text mb-4 leading-tight">
          DealProof
        </h1>

        <p className="text-lg sm:text-xl font-mono text-dp-teal mb-5 tracking-wide">
          Two agents. One sealed enclave. Cryptographic proof.
        </p>

        <p className="text-sm text-dp-muted max-w-lg mb-10 leading-relaxed">
          A two-party AI negotiation protocol running inside an Intel TDX Trusted Execution
          Environment. When agents reach agreement, the CPU produces a hardware-signed attestation
          — proof the deal was fair, the data genuine, and neither side cheated.
        </p>

        {!showForm ? (
          <div className="flex flex-col items-center gap-3">
            <button
              onClick={() => setShowForm(true)}
              className="px-6 py-3 bg-dp-teal text-dp-bg font-mono font-semibold text-sm
                         rounded hover:bg-opacity-90 transition-all tracking-wide"
            >
              Create Deal Room →
            </button>
            <p className="text-xs text-dp-muted font-mono">Seller registers first · Share a link · Buyer joins</p>
          </div>
        ) : (
          <form
            onSubmit={handleCreate}
            className="w-full max-w-sm bg-dp-surface border border-dp-border rounded-lg p-6 text-left space-y-4"
          >
            <div className="mb-2">
              <p className="text-xs font-mono text-dp-muted tracking-widest uppercase mb-1">Register as Seller</p>
              <div className="h-px bg-dp-border" />
            </div>

            <InputField
              label="Your Name"
              value={form.name}
              onChange={set('name')}
              placeholder="Alice"
              required
            />
            <InputField
              label="Email"
              type="email"
              value={form.email}
              onChange={set('email')}
              placeholder="alice@company.com"
              required
            />
            <InputField
              label="ETH Address"
              value={form.eth_address}
              onChange={set('eth_address')}
              placeholder="0x... (optional)"
              hint="Used if escrow is enabled"
            />

            {error && (
              <div className="bg-dp-red/10 border border-dp-red/40 text-dp-red text-xs font-mono rounded px-3 py-2">
                {error}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => { setShowForm(false); setError(null) }}
                className="flex-1 px-4 py-2 border border-dp-border text-dp-muted text-sm font-mono
                           rounded hover:border-dp-text hover:text-dp-text transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !form.name.trim() || !form.email.trim()}
                className="flex-1 px-4 py-2 bg-dp-teal text-dp-bg font-mono font-semibold text-sm
                           rounded disabled:opacity-40 disabled:cursor-not-allowed
                           hover:bg-opacity-90 transition-all"
              >
                {loading ? 'Creating…' : 'Start →'}
              </button>
            </div>
          </form>
        )}
      </div>

      <TrustFooter />
    </div>
  )
}
