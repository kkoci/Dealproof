"""
Employer-initiated invite flow — lets an authenticated employer (company auth,
Phase 3, see app.offercheck.auth) start a negotiation before any candidate
exists, instead of the candidate always being the one who calls POST
/sessions first.

An EmployerInvite is a pending record only — no Session exists yet, so there
is no employer_token/candidate_token to hand out until a candidate claims it.
store.create_session() still runs exactly once, at claim time
(POST /candidate/join/{invite_id}); this module never duplicates or bypasses
it. Same in-memory, no-DB precedent as every other store in this vertical
(auth.py's Company, store.py's Session, demo_auth's consumed-token set).
"""
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

PENDING = "PENDING_CANDIDATE"
CLAIMED = "CLAIMED"


@dataclass
class EmployerInvite:
    id: str
    company_id: str
    band_min: float
    band_mid: float
    band_max: float
    requirements: str | None = None
    ats_candidate_ref: str | None = None
    employer_authority_limit: float | None = None
    employer_priorities: str | None = None
    status: str = PENDING
    session_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_INVITES: dict[str, EmployerInvite] = {}


def reset() -> None:
    """Test-only: clear all invites between test cases."""
    _INVITES.clear()


def create_invite(
    company_id: str,
    band_min: float,
    band_mid: float,
    band_max: float,
    requirements: str | None = None,
    ats_candidate_ref: str | None = None,
    employer_authority_limit: float | None = None,
    employer_priorities: str | None = None,
) -> EmployerInvite:
    invite = EmployerInvite(
        id=secrets.token_urlsafe(12),
        company_id=company_id,
        band_min=band_min,
        band_mid=band_mid,
        band_max=band_max,
        requirements=requirements,
        ats_candidate_ref=ats_candidate_ref,
        employer_authority_limit=employer_authority_limit,
        employer_priorities=employer_priorities,
    )
    _INVITES[invite.id] = invite
    return invite


def get_invite(invite_id: str) -> EmployerInvite | None:
    return _INVITES.get(invite_id)


def claim_invite(invite: EmployerInvite, session_id: str) -> None:
    invite.status = CLAIMED
    invite.session_id = session_id
