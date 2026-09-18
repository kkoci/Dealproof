import React, { useState } from 'react'

/**
 * Route D (the honest dead end) — see app/devcred/routes.py's module docstring.
 * Used when neither direct GitHub access (Route A) nor the events-timeline fallback
 * (Route B) found anything, and the candidate has no local .git copy to fall back to
 * (Route C). Produces a credential with verified: false, provenance_method:
 * "self_reported" — never a fabricated score. Rendered distinctly wherever a
 * credential's status is shown (see Results.jsx).
 */
export default function SelfReportForm({ credentialId, developerHandle, onComplete, onError }) {
  const [roleTitle, setRoleTitle] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [employmentStart, setEmploymentStart] = useState('')
  const [employmentEnd, setEmploymentEnd] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const canSubmit = roleTitle.trim() && companyName.trim() && employmentStart && confirmed && !submitting

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError('')
    try {
      const { selfReportCredential } = await import('../../api.js')
      await selfReportCredential({
        credential_id: credentialId,
        developer_handle: developerHandle || undefined,
        role_title: roleTitle.trim(),
        company_name: companyName.trim(),
        employment_start: employmentStart,
        employment_end: employmentEnd || undefined,
      })
      onComplete?.()
    } catch (err) {
      setError(err.message || 'Submission failed')
      onError?.(err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-gray-700/50 bg-gray-900/30 p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-gray-300">Submit unverified employment details</h3>
        <p className="mt-1 text-xs text-gray-500 leading-relaxed">
          No verifiable git signal could be found for this repository. You can still record what
          you worked on as plain, self-reported context — it will always be clearly labeled
          <span className="text-yellow-400 font-semibold"> unverified</span> and will never be
          shown or scored as a real credential.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Role title</label>
          <input
            type="text"
            value={roleTitle}
            onChange={(e) => setRoleTitle(e.target.value)}
            placeholder="Senior Backend Engineer"
            className="w-full px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-gray-500/50"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Company name</label>
          <input
            type="text"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="Acme Inc"
            className="w-full px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 placeholder-gray-600 text-sm focus:outline-none focus:ring-2 focus:ring-gray-500/50"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Start date</label>
          <input
            type="date"
            value={employmentStart}
            onChange={(e) => setEmploymentStart(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-gray-500/50"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            End date <span className="normal-case font-normal text-gray-600">(blank = current)</span>
          </label>
          <input
            type="date"
            value={employmentEnd}
            onChange={(e) => setEmploymentEnd(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-gray-950/60 border border-gray-700/60 text-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-gray-500/50"
          />
        </div>
      </div>

      <label className="flex items-start gap-2 text-xs text-gray-500">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          className="mt-0.5"
        />
        I understand this will be recorded as an unverified, self-reported claim — not a
        cryptographically or platform-verified credential.
      </label>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={!canSubmit}
        className="px-4 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? 'Submitting…' : 'Submit as unverified'}
      </button>
    </form>
  )
}
