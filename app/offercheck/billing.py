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

Phase 4 (see app.offercheck.credits): create_credit_checkout_session() and
verify_stripe_webhook_signature() below are the real-money side of the
payment-gating design — a company buys a block of verification credits in one
Checkout Session rather than paying per negotiation, and credits.grant_credits()
is only ever called once the webhook handler (routes.py) verifies a real
checkout.session.completed event. Same "not exercised against a live account"
caveat as the rest of this module.
"""
import hashlib
import hmac
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_STRIPE_API_BASE = "https://api.stripe.com/v1"
_STRIPE_WEBHOOK_TOLERANCE_SECONDS = 300  # reject a signature whose timestamp is older than this — standard Stripe SDK default, guards against replay of a captured webhook payload

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


# ---------------------------------------------------------------------------
# Credit purchase (Phase 4 — see app.offercheck.credits) — real money in.
# ---------------------------------------------------------------------------


async def create_credit_checkout_session(
    company_id: str, credit_count: int, success_url: str, cancel_url: str
) -> str:
    """
    Creates a real Stripe Checkout Session for `credit_count` verification credits at
    PRICING["individual"]["price_usd"] each, and returns the hosted checkout URL the
    client should redirect the company's browser to. `client_reference_id` carries the
    company_id through so the webhook handler (routes.py) knows whose balance to
    credit once the checkout actually completes — grant_credits() is only ever called
    from that verified-webhook path, never from this function itself (creating a
    checkout session is not a payment; only the webhook confirms one happened).

    Raises StripeNotConfigured if STRIPE_API_KEY is unset — routes.py surfaces this as
    a clear error rather than the non-fatal degrade record_verification_usage() uses,
    since "buy credits" has no sensible free-degradation path.

    Same caveat as every other Stripe call in this module: this request shape matches
    Stripe's documented Checkout Sessions API as of this writing, not exercised
    against a live account in this environment — confirm against current Stripe docs
    (docs.stripe.com/api/checkout/sessions/create) before relying on this in production.
    """
    if not settings.stripe_api_key:
        raise StripeNotConfigured("STRIPE_API_KEY is not set — credit purchase is disabled")
    if credit_count <= 0:
        raise ValueError("credit_count must be positive")

    unit_amount_cents = round(PRICING["individual"]["price_usd"] * 100)
    async with httpx.AsyncClient(base_url=_STRIPE_API_BASE, auth=(settings.stripe_api_key, "")) as client:
        response = await client.post(
            "/checkout/sessions",
            data={
                "mode": "payment",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": company_id,
                "line_items[0][quantity]": credit_count,
                "line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][unit_amount]": unit_amount_cents,
                "line_items[0][price_data][product_data][name]": "Offer Check verification credit",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["url"]


def verify_stripe_webhook_signature(raw_body: bytes, signature_header: str, webhook_secret: str) -> bool:
    """
    Stripe's own webhook scheme — deliberately NOT the generic
    integrations._shared.verify_hmac_signature (that's a plain hmac-of-body check most
    ATS vendors use; Stripe's is a different shape: the header is
    "t=<unix ts>,v1=<hex hmac>[,v0=...]" and the signed payload is
    "<ts>.<raw body>", not the raw body alone). Also rejects a timestamp outside
    _STRIPE_WEBHOOK_TOLERANCE_SECONDS of now, per Stripe's own documented replay-
    protection guidance.

    Caveat: matches Stripe's documented scheme (docs.stripe.com/webhooks/signatures)
    as of this writing, not exercised against a real Stripe-signed webhook in this
    environment — same convention as every other external call in this module.
    """
    if not signature_header:
        return False
    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    timestamp, v1_signature = parts.get("t"), parts.get("v1")
    if not timestamp or not v1_signature:
        return False
    try:
        if abs(time.time() - int(timestamp)) > _STRIPE_WEBHOOK_TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False

    signed_payload = f"{timestamp}.".encode() + raw_body
    expected = hmac.new(webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1_signature.strip().lower())
