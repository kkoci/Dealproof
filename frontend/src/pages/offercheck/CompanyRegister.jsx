import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { offercheckRegisterCompany } from '../../api.js'
import PageShell from '../../components/offercheck/PageShell.jsx'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'
import { FieldLabel, Input } from '../../components/offercheck/Input.jsx'
import { LockIcon, CopyIcon, CheckIcon } from '../../components/offercheck/icons.jsx'

export default function CompanyRegister() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [hiresPerYear, setHiresPerYear] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const [copied, setCopied] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const data = await offercheckRegisterCompany({
        name: name.trim(),
        hires_per_year: Number(hiresPerYear || 0),
      })
      setResult(data)
    } catch (err) {
      setError(err.message || 'Could not register')
    } finally {
      setSubmitting(false)
    }
  }

  const goToDashboard = () => {
    if (result) localStorage.setItem('offercheck_api_key', result.api_key)
    navigate('/offercheck/dashboard')
  }

  if (result) {
    return (
      <PageShell width="lg">
        <h1 className="font-display text-hero-sm text-ink-primary mb-2">You're registered</h1>
        <p className="flex items-center gap-1.5 text-sm text-sealed-text mb-6">
          <LockIcon size={14} className="shrink-0" />
          Save this API key now — it's shown exactly once and cannot be recovered.
        </p>

        <Card padding="sm" className="!bg-sealed-subtle !border-dashed !border-sealed-border mb-4">
          <p className="text-xs text-sealed-text mb-2">Your API key</p>
          <div className="flex gap-2">
            <Input
              readOnly
              mono
              value={result.api_key}
              className="!bg-bg-elevated !border-sealed-border !text-sealed-text !text-xs"
              onFocus={(e) => e.target.select()}
            />
            <Button
              variant="subtle"
              size="sm"
              onClick={() => {
                navigator.clipboard?.writeText(result.api_key)
                setCopied(true)
              }}
            >
              {copied ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>
        </Card>

        <Card padding="sm" className="mb-6 text-sm text-ink-secondary">
          Recommended plan: <span className="text-ink-primary font-medium">{result.recommended_plan}</span>
          {' — '}
          {result.pricing.price_usd != null
            ? `$${result.pricing.price_usd} ${result.pricing.billing_period === 'monthly' ? '/month' : 'per verification'}`
            : 'custom pricing — contact sales'}
          {' · '}
          <Link to="/offercheck/plans" className="focus-ring rounded text-teal hover:text-teal-hover underline">
            see all plans
          </Link>
        </Card>

        <Button variant="primary" size="lg" fullWidth onClick={goToDashboard}>
          Go to dashboard
        </Button>
      </PageShell>
    )
  }

  return (
    <PageShell width="lg">
      <h1 className="font-display text-hero-sm text-ink-primary mb-2">Register your company</h1>
      <p className="text-sm text-ink-muted mb-8">
        Get an API key for bulk verification and the TA dashboard.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <FieldLabel>Company name</FieldLabel>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Corp" required />
        </div>
        <div>
          <FieldLabel>Hires per year (for a plan recommendation)</FieldLabel>
          <Input
            type="number"
            min="0"
            value={hiresPerYear}
            onChange={(e) => setHiresPerYear(e.target.value)}
            placeholder="50"
          />
        </div>

        {error && (
          <div className="px-3 py-2 rounded-lg bg-danger-subtle border border-danger/30 text-danger text-sm">{error}</div>
        )}

        <Button type="submit" variant="primary" size="lg" fullWidth loading={submitting}>
          {submitting ? 'Registering…' : 'Register'}
        </Button>
      </form>
    </PageShell>
  )
}
