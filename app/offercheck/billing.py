"""
Billing — Phase 3 (see build_spec_offer_check.md pricing model).

Pricing tiers:
  individual   $25 per verification, no subscription
  team         $500/mo — companies under 100 hires/year
  growth       $2,000/mo — companies 100-500 hires/year
  enterprise   custom — contact sales

record_verification_usage() is gated behind STRIPE_API_KEY exactly like
app/contract/escrow.py is gated behind CONTRACT_ADDRESS: unset => raises
StripeNotConfigured, which routes.py catches and logs a warning rather than
failing the request. No Stripe test credentials exist in this environment, so
the real API call path is untested against a live Stripe account — only the
NotConfigured fallback and the pure pricing-tier logic are exercised by tests.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_STRIPE_API_BASE = "https://api.stripe.com/v1"

PRICING = {
    "individual": {"price_usd": 25, "billing_period": "per_verification"},
    "team": {"price_usd": 500, "billing_period": "monthly", "hires_per_year_max": 100},
    "growth": {"price_usd": 2000, "billing_period": "monthly", "hires_per_year_max": 500},
    "enterprise": {"price_usd": None, "billing_period": "custom"},
}

VALID_PLANS = set(PRICING)


class StripeNotConfigured(Exception):
    """Raised when STRIPE_API_KEY is not set."""


class UnknownPlan(Exception):
    pass


def pricing_for_plan(plan: str) -> dict:
    if plan not in PRICING:
        raise UnknownPlan(f"unknown plan {plan!r} — valid plans: {sorted(VALID_PLANS)}")
    return {"plan": plan, **PRICING[plan]}


def recommend_plan(hires_per_year: int) -> str:
    """Pure recommendation helper for the company registration form."""
    if hires_per_year < 20:
        return "individual"
    if hires_per_year < 100:
        return "team"
    if hires_per_year <= 500:
        return "growth"
    return "enterprise"


async def record_verification_usage(company_id: str, plan: str) -> str:
    """
    Record one verification against a company's plan for billing purposes.

    Returns a provider-assigned usage record id. Only "individual" plan usage
    is metered per-verification (team/growth/enterprise are flat monthly —
    usage is tracked for analytics but doesn't drive a per-use Stripe charge).

    Uses the Stripe REST API directly via httpx (same pattern as this repo's
    other external HTTP calls — DoH, tappd) rather than the stripe SDK, so no
    new dependency is added for a path that's untestable without a real
    Stripe account. The request shape below (POST /v1/invoiceitems, Basic
    auth with the secret key) matches Stripe's documented API as of this
    writing — confirm against current Stripe docs before relying on it in
    production, since it has not been exercised against a live account here.
    """
    if not settings.stripe_api_key:
        raise StripeNotConfigured("STRIPE_API_KEY is not set — billing is disabled")

    if plan != "individual":
        logger.info(f"company {company_id}: verification recorded under flat-rate plan {plan!r} (no per-use charge)")
        return "flat_rate_no_charge"

    async with httpx.AsyncClient(base_url=_STRIPE_API_BASE, auth=(settings.stripe_api_key, "")) as client:
        response = await client.post(
            "/invoiceitems",
            data={
                "customer": company_id,
                "amount": PRICING["individual"]["price_usd"] * 100,
                "currency": "usd",
                "description": "Offer Check verification",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["id"]
