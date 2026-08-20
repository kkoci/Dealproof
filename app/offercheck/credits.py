"""
Payment gating (Phase 4) — see the payment-gating research report this implements
(confirmed design: negotiation stays free/unauthenticated; the paid "$25 per
verification" deliverable — TDX attestation + πCreds conduct credential + market
comparator — is gated at the point it would be produced, routes.py::_maybe_attest).

Nothing about how a session is created or negotiated changes: the per-session
employer_token model (routes.py) is untouched, and every existing free flow
(candidate-initiated POST /sessions with no X-API-Key, an employer responding via a
link) still reaches a real AGREED/WALKAWAY/etc. state exactly as before. This module
gates one thing only — whether _maybe_attest() actually produces the proof bundle —
and it's checked, not assumed, on every terminal transition, so a session that
couldn't be billed the first time (no company attached yet) can be unlocked later via
POST /sessions/{id}/claim without redoing the negotiation.

Credit unit price is billing.PRICING["individual"]["price_usd"] — this module doesn't
define its own price, it defers to the existing pricing tiers so the two can't drift
independently.

Three deliberately separate ways a Company's credit_balance can change, kept apart on
purpose:
  1. Real purchase — billing.create_credit_checkout_session() + the Stripe webhook
     handler (routes.py) call grant_credits() only after a verified
     checkout.session.completed event. This is the only path real money touches.
  2. Test-mode starter grant — auth.register_company(test_mode=True) mints an
     "oc_test_"-prefixed key and calls grant_credits() once, at registration, for
     TEST_STARTER_CREDITS. No payment code is touched at all for this path, so a
     test-mode company can never accidentally trigger or be confused with a real
     Stripe charge (Stripe's own test/live webhook secrets are already distinct,
     independent of this flag).
  3. Operator grant/unlimited — grant_credits()/grant_unlimited() called only from the
     POST /company/credits/grant route, gated by the same X-Internal-Key mechanism
     OFFERCHECK_INTERNAL_KEY already gates POST /auth/demo-link with (see routes.py).
     Deliberately NOT a runtime "if this is me, skip the check" branch inside
     debit_for_verification() below — the gate is the route's own auth check, before
     either of these functions is ever called, so there is no code path a normal
     user's request could reach.
"""
from dataclasses import dataclass

from app.offercheck import auth
from app.offercheck.store import Session

# Generous enough for real testing/demos without being unbounded ("unlimited" is its
# own separate, operator-only flag — see grant_unlimited below, and the module
# docstring's point 3).
TEST_STARTER_CREDITS = 100


@dataclass
class DebitResult:
    """What debit_for_verification actually did, for logging/response purposes —
    distinguishes "no company at all" from "company exists but is out of credit",
    since routes.py surfaces those differently (silent payment_required vs. a
    clearer 402 on the explicit claim endpoint)."""
    charged: bool
    reason: str  # "unlimited" | "debited" | "no_company" | "insufficient_credit"


def debit_for_verification(session: Session) -> DebitResult:
    """
    Attempts to charge one verification credit against session.company_id. Never
    raises. Called from exactly one place, routes.py::_maybe_attest, immediately
    before it would otherwise produce the paid proof bundle (attestation + credential
    + market comparator) — a session whose company isn't resolvable or has no credit
    reaches its terminal negotiation state exactly as normal; only the proof is
    withheld (session.payment_required is set by the caller based on this result).

    Only company.plan == "individual" actually draws down credit_balance — matches
    billing.record_verification_usage's own pre-existing plan semantics exactly
    ("only 'individual' plan usage is metered per-verification (team/growth/enterprise
    are flat monthly)"). A flat-monthly plan's negotiations are already paid for by
    the subscription; gating them behind a credit balance too would be double
    enforcement for money already collected outside this module. This is also what
    keeps _maybe_notify's existing record_verification_usage() call correct without
    changing it: that call already only fires a live per-use Stripe charge for
    "individual" plan — see routes.py's own comment at that call site for how the two
    are kept from double-charging an individual-plan company.
    """
    if session.company_id is None:
        return DebitResult(charged=False, reason="no_company")
    company = auth.get_company(session.company_id)
    if company is None:
        return DebitResult(charged=False, reason="no_company")
    if company.plan != "individual":
        return DebitResult(charged=True, reason="flat_rate_plan")
    if company.is_unlimited:
        return DebitResult(charged=True, reason="unlimited")
    if company.credit_balance > 0:
        company.credit_balance -= 1
        return DebitResult(charged=True, reason="debited")
    return DebitResult(charged=False, reason="insufficient_credit")


def grant_credits(company: auth.Company, amount: int) -> None:
    """Real-money and operator-grant path only — see module docstring points 1 and 3.
    Never called from a path a normal user's request can reach directly."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    company.credit_balance += amount


def grant_unlimited(company: auth.Company) -> None:
    """Operator-only — see module docstring point 3."""
    company.is_unlimited = True
