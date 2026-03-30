import React, { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { runDeal } from '../api.js'

const DEFAULT_DATA_HASH = '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08'
const HEX_64_REGEX = /^[0-9a-f]{64}$/i

function FormField({ label, hint, error, children, required }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-gray-300 flex items-center gap-1.5">
        {label}
        {required && <span className="text-indigo-400 text-xs">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="text-xs text-gray-600">{hint}</p>
      )}
      {error && (
        <p className="text-xs text-red-400 flex items-center gap-1">
          <svg className="w-3 h-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          {error}
        </p>
      )}
    </div>
  )
}

const inputClass = `
  w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-gray-700/60 text-gray-200
  placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50
  focus:border-indigo-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed
`.trim()

const inputErrorClass = `
  w-full px-3 py-2.5 rounded-lg bg-gray-900/60 border border-red-700/60 text-gray-200
  placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-red-500/50
  focus:border-red-500/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed
`.trim()

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const arrayBuffer = e.target.result
      const uint8 = new Uint8Array(arrayBuffer)
      let binary = ''
      for (let i = 0; i < uint8.length; i++) {
        binary += String.fromCharCode(uint8[i])
      }
      resolve(btoa(binary))
    }
    reader.onerror = reject
    reader.readAsArrayBuffer(file)
  })
}

export default function CreateDeal() {
  const navigate = useNavigate()
  const fileInputRef = useRef(null)

  const [form, setForm] = useState({
    buyer_budget: '',
    buyer_requirements: '',
    data_description: '',
    data_hash: DEFAULT_DATA_HASH,
    floor_price: '',
    seller_email_eml: null,
    seller_address: '',
    escrow_amount_eth: '',
  })

  const [errors, setErrors] = useState({})
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [emlFileName, setEmlFileName] = useState(null)

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
    if (errors[key]) {
      setErrors((prev) => ({ ...prev, [key]: null }))
    }
  }

  async function handleEmlUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const b64 = await fileToBase64(file)
      setField('seller_email_eml', b64)
      setEmlFileName(file.name)
    } catch {
      setErrors((prev) => ({ ...prev, seller_email_eml: 'Failed to read file' }))
    }
  }

  function validate() {
    const newErrors = {}

    if (!form.buyer_budget || isNaN(Number(form.buyer_budget)) || Number(form.buyer_budget) <= 0) {
      newErrors.buyer_budget = 'Enter a valid positive budget'
    }

    if (!form.buyer_requirements.trim()) {
      newErrors.buyer_requirements = 'Buyer requirements are required'
    }

    if (!form.data_description.trim()) {
      newErrors.data_description = 'Data description is required'
    }

    if (!form.data_hash.trim()) {
      newErrors.data_hash = 'Data hash is required'
    } else if (!HEX_64_REGEX.test(form.data_hash.trim())) {
      newErrors.data_hash = 'Must be exactly 64 lowercase hex characters (SHA-256)'
    }

    if (!form.floor_price || isNaN(Number(form.floor_price)) || Number(form.floor_price) < 0) {
      newErrors.floor_price = 'Enter a valid floor price'
    }

    if (
      form.buyer_budget &&
      form.floor_price &&
      !isNaN(Number(form.buyer_budget)) &&
      !isNaN(Number(form.floor_price)) &&
      Number(form.buyer_budget) < Number(form.floor_price)
    ) {
      newErrors.buyer_budget = `Budget ($${form.buyer_budget}) must be ≥ floor price ($${form.floor_price})`
    }

    if (form.seller_address && !/^0x[0-9a-fA-F]{40}$/.test(form.seller_address.trim())) {
      newErrors.seller_address = 'Must be a valid Ethereum address (0x...)'
    }

    if (form.escrow_amount_eth && (isNaN(Number(form.escrow_amount_eth)) || Number(form.escrow_amount_eth) < 0)) {
      newErrors.escrow_amount_eth = 'Enter a valid ETH amount'
    }

    return newErrors
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitError(null)

    const validationErrors = validate()
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors)
      const firstErrorKey = Object.keys(validationErrors)[0]
      document.querySelector(`[name="${firstErrorKey}"]`)?.focus()
      return
    }

    setSubmitting(true)

    const body = {
      buyer_budget: Number(form.buyer_budget),
      buyer_requirements: form.buyer_requirements.trim(),
      data_description: form.data_description.trim(),
      data_hash: form.data_hash.trim().toLowerCase(),
      floor_price: Number(form.floor_price),
      seller_proof: null,
      seller_email_eml: form.seller_email_eml || null,
      seller_address: form.seller_address.trim() || null,
      escrow_amount_eth: form.escrow_amount_eth ? Number(form.escrow_amount_eth) : null,
    }

    try {
      const result = await runDeal(body)
      navigate(`/deal/${result.deal_id}`, { state: { result } })
    } catch (err) {
      setSubmitError(err.message || 'Failed to run negotiation. Is the backend running?')
      setSubmitting(false)
    }
  }

  const hashIsValid = HEX_64_REGEX.test(form.data_hash.trim())

  return (
    <div className="min-h-[calc(100vh-3.5rem)] py-10 px-4">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-xs text-gray-500 font-mono mb-3">
            <span>dealproof</span>
            <span>/</span>
            <span className="text-gray-400">new-deal</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-100 mb-2">
            Create a Deal
          </h1>
          <p className="text-sm text-gray-500">
            Configure deal parameters. Two AI agents will negotiate inside an Intel TDX TEE.
            This may take 20–60 seconds.
          </p>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-6">

          {/* Required fields card */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <div className="px-5 py-3.5 border-b border-gray-800/40 bg-gray-900/40">
              <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
                <svg className="w-4 h-4 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                Deal Parameters
              </h2>
            </div>

            <div className="px-5 py-5 space-y-5">
              {/* Budget + Floor Price row */}
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  label="Buyer Budget"
                  hint="Maximum price buyer will pay (USD)"
                  error={errors.buyer_budget}
                  required
                >
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm pointer-events-none">$</span>
                    <input
                      name="buyer_budget"
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.buyer_budget}
                      onChange={(e) => setField('buyer_budget', e.target.value)}
                      disabled={submitting}
                      placeholder="1000"
                      className={`${errors.buyer_budget ? inputErrorClass : inputClass} pl-7`}
                    />
                  </div>
                </FormField>

                <FormField
                  label="Floor Price"
                  hint="Minimum seller will accept (USD)"
                  error={errors.floor_price}
                  required
                >
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm pointer-events-none">$</span>
                    <input
                      name="floor_price"
                      type="number"
                      min="0"
                      step="0.01"
                      value={form.floor_price}
                      onChange={(e) => setField('floor_price', e.target.value)}
                      disabled={submitting}
                      placeholder="500"
                      className={`${errors.floor_price ? inputErrorClass : inputClass} pl-7`}
                    />
                  </div>
                </FormField>
              </div>

              {/* Buyer Requirements */}
              <FormField
                label="Buyer Requirements"
                hint="Describe the data access scope you need"
                error={errors.buyer_requirements}
                required
              >
                <textarea
                  name="buyer_requirements"
                  rows={3}
                  value={form.buyer_requirements}
                  onChange={(e) => setField('buyer_requirements', e.target.value)}
                  disabled={submitting}
                  placeholder="Full read access for 30 days, GDPR-compliant anonymised data, no PII..."
                  className={`${errors.buyer_requirements ? inputErrorClass : inputClass} resize-y min-h-[80px]`}
                />
              </FormField>

              {/* Data Description */}
              <FormField
                label="Data Description"
                hint="Brief description of what data is being sold"
                error={errors.data_description}
                required
              >
                <textarea
                  name="data_description"
                  rows={2}
                  value={form.data_description}
                  onChange={(e) => setField('data_description', e.target.value)}
                  disabled={submitting}
                  placeholder="10GB anonymised user behaviour logs from Q1 2024..."
                  className={`${errors.data_description ? inputErrorClass : inputClass} resize-y min-h-[64px]`}
                />
              </FormField>

              {/* Data Hash */}
              <FormField
                label="Data Hash"
                hint="SHA-256 of the dataset (64 hex characters)"
                error={errors.data_hash}
                required
              >
                <div className="relative">
                  <input
                    name="data_hash"
                    type="text"
                    value={form.data_hash}
                    onChange={(e) => setField('data_hash', e.target.value)}
                    disabled={submitting}
                    placeholder="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
                    maxLength={64}
                    className={`${errors.data_hash ? inputErrorClass : inputClass} font-mono text-xs pr-10`}
                  />
                  {form.data_hash.trim() && (
                    <div className="absolute right-3 top-1/2 -translate-y-1/2">
                      {hashIsValid ? (
                        <svg className="w-4 h-4 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                      ) : (
                        <span className="text-xs font-mono text-red-400">{form.data_hash.trim().length}/64</span>
                      )}
                    </div>
                  )}
                </div>
              </FormField>
            </div>
          </div>

          {/* Advanced section */}
          <div className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
            <button
              type="button"
              onClick={() => setAdvancedOpen((o) => !o)}
              className="w-full px-5 py-3.5 flex items-center justify-between text-sm font-semibold text-gray-400 hover:text-gray-200 hover:bg-gray-800/20 transition-all"
            >
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                </svg>
                Advanced Options
                <span className="text-xs text-gray-600 font-normal">(optional)</span>
              </span>
              <svg
                className={`w-4 h-4 transition-transform duration-200 ${advancedOpen ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {advancedOpen && (
              <div className="px-5 pb-5 pt-1 space-y-5 border-t border-gray-800/40">

                {/* EML Upload */}
                <FormField
                  label="Seller Email Proof (.eml)"
                  hint="Upload a .eml file for DKIM-based seller identity verification"
                  error={errors.seller_email_eml}
                >
                  <div
                    onClick={() => !submitting && fileInputRef.current?.click()}
                    className={`
                      flex items-center gap-3 px-4 py-3 rounded-lg border-2 border-dashed cursor-pointer transition-all
                      ${submitting ? 'opacity-50 cursor-not-allowed' : 'hover:border-indigo-600/60 hover:bg-indigo-950/10'}
                      ${emlFileName ? 'border-emerald-700/50 bg-emerald-950/10' : 'border-gray-700/50'}
                    `}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".eml,message/rfc822"
                      onChange={handleEmlUpload}
                      disabled={submitting}
                      className="hidden"
                    />
                    {emlFileName ? (
                      <>
                        <svg className="w-5 h-5 text-emerald-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-emerald-400 font-medium truncate">{emlFileName}</p>
                          <p className="text-xs text-gray-600">Base64-encoded and ready</p>
                        </div>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            setEmlFileName(null)
                            setField('seller_email_eml', null)
                          }}
                          className="text-gray-500 hover:text-red-400 transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </>
                    ) : (
                      <>
                        <svg className="w-5 h-5 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                        </svg>
                        <div>
                          <p className="text-sm text-gray-400">Click to upload .eml file</p>
                          <p className="text-xs text-gray-600">Email file for DKIM verification</p>
                        </div>
                      </>
                    )}
                  </div>
                </FormField>

                {/* Seller ETH Address */}
                <FormField
                  label="Seller ETH Address"
                  hint="Ethereum address for on-chain escrow settlement"
                  error={errors.seller_address}
                >
                  <input
                    name="seller_address"
                    type="text"
                    value={form.seller_address}
                    onChange={(e) => setField('seller_address', e.target.value)}
                    disabled={submitting}
                    placeholder="0xabc123..."
                    className={`${errors.seller_address ? inputErrorClass : inputClass} font-mono`}
                  />
                </FormField>

                {/* Escrow Amount */}
                <FormField
                  label="Escrow Amount (ETH)"
                  hint="Amount of ETH to lock in escrow smart contract"
                  error={errors.escrow_amount_eth}
                >
                  <div className="relative">
                    <input
                      name="escrow_amount_eth"
                      type="number"
                      min="0"
                      step="0.0001"
                      value={form.escrow_amount_eth}
                      onChange={(e) => setField('escrow_amount_eth', e.target.value)}
                      disabled={submitting}
                      placeholder="0.05"
                      className={`${errors.escrow_amount_eth ? inputErrorClass : inputClass} pr-12`}
                    />
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 text-xs font-mono pointer-events-none">ETH</span>
                  </div>
                </FormField>
              </div>
            )}
          </div>

          {/* Submit error */}
          {submitError && (
            <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-950/30 border border-red-800/50 text-red-300 text-sm">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div>
                <p className="font-medium text-red-300">Negotiation failed</p>
                <p className="text-red-400/80 text-xs mt-0.5">{submitError}</p>
              </div>
            </div>
          )}

          {/* Submit button */}
          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-3 px-6 py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-800 disabled:cursor-not-allowed text-white font-semibold text-base transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60 hover:-translate-y-0.5 active:translate-y-0 disabled:translate-y-0 disabled:shadow-none"
          >
            {submitting ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Agents negotiating inside TEE...</span>
                <span className="text-indigo-300 text-sm font-normal">(20–60s)</span>
              </>
            ) : (
              <>
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Run Negotiation
              </>
            )}
          </button>

          {submitting && (
            <p className="text-center text-xs text-gray-500">
              LLM agents are exchanging offers. Do not close this tab.
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
