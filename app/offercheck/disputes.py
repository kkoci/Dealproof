"""
Dispute/contest surface — flagged independently by Andrew Miller's eight-move
governance framework ("no formal dispute/contest surface") and by Gil Rosen
("is negotiation fair if one agent is smarter") — both pointing at the same
architectural gap: an AGREED, attested Offer Check outcome had no way for
either party to formally register disagreement with it. This is a new,
separate module rather than an addition to negotiation.py: negotiation.py's
own docstring scopes it to "the revision-loop state machine" specifically,
and every other capability layered on top of a closed session already gets
its own module in this vertical (credential.py, provenance.py, package.py) —
disputes follow that same established boundary rather than growing
negotiation.py past its stated scope.

Two distinct dispute types, not one generic complaint bucket:
  - "process": a claim that the attested record doesn't match what the party
    experienced, or that a stated rule was violated (e.g. a stated floor
    wasn't respected, a round was miscounted, an approval vote was ignored).
    In principle checkable against data already captured in the session and
    its attested trace — this module does NOT itself re-run those checks
    (see "What this module deliberately does NOT do" below); it records the
    claim for a human (or a future auditor pass) to check against that data.
  - "outcome": a claim that the negotiated result itself is bad, grounded
    specifically against one of the two external signals this vertical
    already computes — negotiation.final_gap_pct or session.market_percentile
    — never vague dissatisfaction. Filing requires naming which one
    (referenced_field), and that field must actually have a value on this
    session: you can't dispute market_percentile against a session where the
    BLS/ONS lookup never succeeded and it's None (see fetch_market_range's
    own resilience contract in app.offercheck.integrations.market_data).

Disputes are fileable ONLY on an AGREED session. A dispute is inherently "I
disagree with the deal that was struck" — there is no deal to disagree with
before AGREED, and every other terminal state (WALKAWAY/EXPIRED/DECLINED/
STALEMATE) has no agreed_price for an outcome dispute to be grounded against
in the first place. No new session state is added for this (no "DISPUTED"
state) — filing is a flag recorded alongside an unmodified session.state,
not a transition; see the next paragraph for why that matters.

**Filing is flag-only, deliberately decoupled from the existing reopen
mechanism (app.offercheck.negotiation._resolve_approval's
"request_more_rounds" path).** This is the single most important design
constraint in this module: file_dispute() never touches session.state,
session.extension_count, session.max_rounds, and never calls anything in
negotiation.py's approval-vote machinery. If filing a dispute could cheaply
force a reopen, either party could use it as a free do-over button on an
outcome they already agreed to — filing costs nothing and nothing stops it
being repeated, which would quietly undermine the entire premise that an
AGREED, attested outcome is actually settled. A dispute is documented
justification a human reviews; ACTING on it (if warranted) means a human
manually driving the existing, completely unmodified approval/reopen flow —
this module supplies the evidence, not the trigger. (There is currently no
human-facing "reopen this AGREED session" endpoint at all — the existing
reopen path only fires from within the PENDING_APPROVAL vote resolution, on
a session that hasn't reached AGREED yet. Acting on a dispute today means an
operator manually coordinating a fresh negotiation/session out-of-band; this
module doesn't change that, and building an "reopen an AGREED session" entry
point is explicitly not part of this pass.)

**Filing never mutates any already-attested field.** agreed_price,
final_gap_pct, market_percentile, and every hash in
negotiation.attested_terms() are read, never written, by file_dispute(). A
dispute is purely additive — appended to session.disputes — layered on top
of an immutable outcome, never a mutation of it.

**What this module deliberately does NOT do:** it does not adjudicate a
dispute (there is no "uphold" / "reject" verdict) and it does not itself
re-run a process claim against the session's data to confirm or deny it —
that's a human (or a future auditor pass) reading the evidence field
alongside the session's existing attested data. This module's job stops at:
validate who's filing and that outcome disputes are grounded in a real
external signal, then record the claim immutably.

**Why disputes aren't folded into the original TDX quote.** Credential
hashes (credential.py) get embedded in report_data because
compute_credential() runs *before* sign_result() at the same AGREED-
transition moment (see routes.py::_maybe_attest). Disputes structurally
can't do this — they're filed *after* attestation has already fired
(session.attestation is set exactly once, at AGREED, before any dispute
could exist; _maybe_attest is idempotent and never re-fires). Each Dispute
still carries its own dispute_hash (see store.py) for the same tamper-
evident, sorted-keys-SHA-256 discipline as credential_hash — but it seals
the dispute record's own fields, not a new TDX report_data. A verifier gets
two honest, separately-verifiable views instead of one quote silently
redefined after the fact: (a) the original TDX quote, covering the outcome
as it stood at AGREED, via GET /sessions/{id}/attest, and (b) the live,
hash-stamped dispute list via GET /sessions/{id}/disputes (disputes_view()
below). Folding disputes into a fresh TDX quote per filing was considered
and rejected — it would mean attestation-worthy I/O firing on every dispute
filing, and blurs the "AGREED means settled" premise the decoupling above
exists to protect. `negotiation.attested_terms()` itself is intentionally
NOT touched by this module for the same reason: it only ever runs once, at
the AGREED transition, strictly before any dispute can exist — wiring
disputes into it would never actually surface a filed dispute in practice.

**Not yet built, flagged rather than silently skipped:** dispute filing has
no rate limit (app.offercheck.rate_limit covers every Claude-calling and
griefing-prone endpoint in this vertical, but filing makes no external call
and unlimited filing from either party is the intended behavior — a session
can legitimately have many disputes — so this wasn't added by default; worth
reconsidering if unbounded per-session storage growth becomes a real
concern). There is also no adjudication workflow, no dispute-status field,
and no notification when one is filed — all explicitly out of scope here.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.offercheck import negotiation
from app.offercheck.store import Dispute

if TYPE_CHECKING:
    from app.offercheck.store import Session

# 1000 chars (~150-200 words) — enough room for a genuine, specific explanation
# (dates, round numbers, quoted terms) without becoming an unbounded free-text
# blob in an in-memory, never-pruned list. Same order of magnitude as this
# vertical's other free-text fields (requirements, candidate/employer
# priorities), which are conventionally short but technically uncapped today;
# this field is capped because it's evidence a human is expected to actually
# read, not just a hint injected into an LLM prompt.
EVIDENCE_MAX_LENGTH = 1000

# The only two fields an "outcome" dispute may reference — both are the
# external signals this vertical actually computes (see module docstring).
# Deliberately not "any attested field": agreed_price is self-reported, not
# an external anchor, and isn't a valid target for this dispute type.
_OUTCOME_FIELD_RESOLVERS = {
    "final_gap_pct": lambda session: negotiation.final_gap_pct(session),
    "market_percentile": lambda session: session.market_percentile,
}


class DisputeError(Exception):
    """Base class for dispute-filing violations; routes.py maps these to HTTP codes."""


class SessionNotAgreed(DisputeError):
    pass


class NotAParty(DisputeError):
    pass


class ReferencedFieldRequired(DisputeError):
    pass


class ReferencedFieldNotAllowedForProcess(DisputeError):
    pass


class UnknownReferencedField(DisputeError):
    pass


class ReferencedFieldUnavailable(DisputeError):
    pass


class InvalidEvidence(DisputeError):
    pass


def file_dispute(
    session: "Session",
    filed_by: str,
    dispute_type: str,
    evidence: str,
    referenced_field: str | None = None,
) -> Dispute:
    """
    Validates and records a dispute. See module docstring for the full
    design rationale — in particular: this NEVER changes session.state or
    any already-attested field, and NEVER triggers the reopen mechanism.

    filed_by is expected to already be resolved from the caller's token by
    routes.py (the same app.offercheck.routes._resolve_viewer() every other
    endpoint in this vertical uses to derive actor identity — never trust a
    client-declared identity directly). Re-validated here anyway so this
    function is safe to call directly (e.g. from tests) without going
    through the HTTP layer.
    """
    if session.state != "AGREED":
        raise SessionNotAgreed(
            f"disputes can only be filed on an AGREED session (state={session.state}) — there is no "
            "settled outcome to contest before an agreement exists, and no agreed_price for an outcome "
            "dispute to be grounded against on any other terminal state"
        )

    if filed_by not in ("candidate", "employer"):
        raise NotAParty(f"{filed_by!r} is not a party to this session")

    if dispute_type == "outcome":
        if not referenced_field:
            raise ReferencedFieldRequired(
                "an outcome dispute must reference an existing attested field "
                f"(one of {sorted(_OUTCOME_FIELD_RESOLVERS)})"
            )
        if referenced_field not in _OUTCOME_FIELD_RESOLVERS:
            raise UnknownReferencedField(
                f"{referenced_field!r} is not a valid outcome-dispute field — must be one of {sorted(_OUTCOME_FIELD_RESOLVERS)}"
            )
        if _OUTCOME_FIELD_RESOLVERS[referenced_field](session) is None:
            raise ReferencedFieldUnavailable(
                f"{referenced_field!r} has no value on this session (the lookup that would have "
                "populated it never succeeded) — cannot dispute a value that was never computed"
            )
    elif dispute_type == "process":
        if referenced_field is not None:
            raise ReferencedFieldNotAllowedForProcess(
                "a process dispute must not reference an outcome field — that's what the 'outcome' dispute type is for"
            )
    else:
        raise DisputeError(f"unknown dispute_type {dispute_type!r} — must be 'process' or 'outcome'")

    stripped = evidence.strip() if evidence else ""
    if not stripped:
        raise InvalidEvidence("evidence must be non-empty")
    if len(evidence) > EVIDENCE_MAX_LENGTH:
        raise InvalidEvidence(f"evidence must be at most {EVIDENCE_MAX_LENGTH} characters (got {len(evidence)})")

    dispute = Dispute(
        dispute_id=secrets.token_urlsafe(12),
        session_id=session.id,
        filed_by=filed_by,
        dispute_type=dispute_type,
        evidence=evidence,
        referenced_field=referenced_field,
        filed_at=datetime.now(timezone.utc).isoformat(),
        dispute_hash="",
    )
    dispute.dispute_hash = _hash_dispute(dispute)
    session.disputes.append(dispute)
    return dispute


def _hash_dispute(dispute: Dispute) -> str:
    payload = {
        "dispute_id": dispute.dispute_id,
        "session_id": dispute.session_id,
        "filed_by": dispute.filed_by,
        "dispute_type": dispute.dispute_type,
        "evidence": dispute.evidence,
        "referenced_field": dispute.referenced_field,
        "filed_at": dispute.filed_at,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def disputes_view(session: "Session") -> dict:
    """
    Live, hash-stamped dispute list alongside the original attested outcome
    fields — see module docstring's "Why disputes aren't folded into the
    original TDX quote" for why this is a separate function from
    negotiation.attested_terms() rather than an addition to it. This is what
    routes.py's GET /sessions/{id}/disputes returns.
    """
    return {
        "session_id": session.id,
        "state": session.state,
        "agreed_price": session.agreed_price,
        "final_gap_pct": negotiation.final_gap_pct(session),
        "market_percentile": session.market_percentile,
        "disputes": [
            {
                "dispute_id": d.dispute_id,
                "filed_by": d.filed_by,
                "dispute_type": d.dispute_type,
                "evidence": d.evidence,
                "referenced_field": d.referenced_field,
                "filed_at": d.filed_at,
                "dispute_hash": d.dispute_hash,
            }
            for d in session.disputes
        ],
    }
