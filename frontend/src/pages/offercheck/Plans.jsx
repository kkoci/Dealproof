import React from 'react'
import { Link } from 'react-router-dom'
import Card from '../../components/offercheck/Card.jsx'
import Button from '../../components/offercheck/Button.jsx'

// Sourced from app/offercheck/billing.py — PRICING dict + recommend_plan()'s hires/year
// thresholds. No backend endpoint currently returns all four tiers at once (only
// GET-a-single-plan's-pricing, via pricing_for_plan(), consumed from CompanyRegister's
// registration response for the one recommended plan) — so these are hardcoded here rather
// than fetched. THIS WILL DRIFT if billing.py's PRICING or recommend_plan() ever change
// without a matching edit here. Worth a small backend addition later (e.g. a
// GET /api/offercheck/company/plans returning billing.PRICING verbatim) — not built in this
// pass, since it's a backend change and this pass is frontend-only.
const TIERS = [
  {
    key: 'individual',
    name: 'Individual',
    price: '$25',
    period: 'per verification',
    bestFor: 'Under ~20 hires/year',
    description: 'Pay per use, no subscription. Verify a single competing offer whenever you need to.',
  },
  {
    key: 'team',
    name: 'Team',
    price: '$500',
    period: '/month',
    bestFor: 'Up to 100 hires/year',
    description: 'Flat monthly rate for teams running verifications regularly.',
  },
  {
    key: 'growth',
    name: 'Growth',
    price: '$2,000',
    period: '/month',
    bestFor: 'Up to 500 hires/year',
    description: 'Higher-volume flat rate for growing hiring teams.',
  },
  {
    key: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    period: 'contact sales',
    bestFor: '500+ hires/year',
    description: 'Custom pricing for large-scale hiring — get in touch to talk through your volume.',
  },
]

export default function Plans() {
  return (
    <div className="px-4 sm:px-6 lg:px-8">
      <div className="max-w-5xl mx-auto py-16">
        <h1 className="font-display text-hero-sm text-ink-primary mb-2">Plans &amp; pricing</h1>
        <p className="text-sm text-ink-muted mb-10 max-w-lg">
          Every tier gets the same verification: TEE-attested, hardware-signed, no raw numbers
          ever cross between candidate and employer. Pricing scales with hiring volume.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {TIERS.map((t) => (
            <Card key={t.key} padding="lg" className="flex flex-col">
              <p className="text-data-label uppercase text-teal-text mb-3">{t.name}</p>
              <div className="mb-1">
                <span className="font-display text-hero-sm text-ink-primary">{t.price}</span>
              </div>
              <p className="text-xs text-ink-muted mb-4">{t.period}</p>
              <p className="text-xs text-ink-secondary leading-relaxed mb-4 flex-1">{t.description}</p>
              <p className="text-data-label uppercase text-ink-muted mb-4">{t.bestFor}</p>
              <Button as={Link} to="/offercheck/company/register" variant={t.key === 'enterprise' ? 'secondary' : 'primary'} fullWidth>
                {t.key === 'enterprise' ? 'Get in touch' : 'Register your company'}
              </Button>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
