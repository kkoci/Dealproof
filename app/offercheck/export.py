"""
Training-data export — Phase 5 (scoping pass, see the fine-tuning scoping report
this implements). Converts this system's own in-memory Session objects into a
structured record loosely shaped like the Yamaguchi et al. (EACL 2021) Job
Interview corpus eval_harness.py already evaluates against — same top-level
"dialogue with rounds + a final solution" shape — so any future fine-tuning
pipeline can treat DealProof's own real transcripts and the academic corpus as
two sources feeding the same downstream format, not two incompatible ones.

**Anonymization policy — read before changing what this exports.** Offer Check
has no consent mechanism today (no opt-in flag anywhere in CompetingOffer,
Session, or the request schemas) for "this negotiation's data may be used for
training." Given that, this module's policy is: treat every session as
non-consented and strip anything that could identify a real person or company,
unconditionally — there is no flag that relaxes this. Specifically excluded,
on purpose, never included regardless of any future setting added elsewhere:
  - competing_offer.company — the real employer name. This is the single
    highest-risk field in the whole data model; a company name plus a salary
    figure is realistically re-identifying on its own.
  - candidate_priorities / employer_priorities — free text. A person can type
    anything here, including their own name, a competing offer's company name,
    or other identifying detail. There is no reliable automatic redaction for
    free text, so this is dropped entirely rather than attempting one.
  - ats_candidate_ref — an external ATS system's real candidate identifier.
  - company_id — Offer Check's own Company record id. Not a person's identity,
    but still lets every session from the same real business be correlated
    against each other in an exported corpus, which isn't needed for training
    a negotiation *strategy* model and is easy to leave out.
  - candidate_provenance_credential, dispute evidence — both already scrubbed
    of raw names/repos/tokens at the source (see app.offercheck.provenance and
    app.offercheck.disputes), but excluded here anyway: neither is negotiation
    strategy signal, and there's no reason to widen this export's surface area
    for fields that don't serve its actual purpose.
  - candidate_token / employer_token — these are bearer secrets, not data.

Kept, judged low-risk on their own and genuinely useful training signal:
  - role (free text, but a job title alone — "Senior Software Engineer" — is
    not realistically re-identifying without the company name attached)
  - location (already coarse — see market_data.py's own metro/region
    granularity discussion; not a street address)
  - every negotiated value/round/move, agreed_price or agreed package,
    final_gap_pct, market_percentile — these are the actual training signal,
    and final_gap_pct/market_percentile were already engineered elsewhere in
    this codebase to carry no raw private number beyond the derived figure.

session.id itself is never exported raw — see `_anonymized_id`.

**A real structural gap, stated plainly rather than papered over:** the
Yamaguchi corpus was built as a utility-elicitation study — every dialogue
carries each party's real private weights (0-1) over every dimension. Offer
Check is a real product, not an elicitation study; it has never asked either
party "how much do you weight salary vs. start date" and has no such data to
export. `dimensions` below therefore describes each dimension's *type and
legal range only* (matching the public half of Yamaguchi's dimension spec) —
`utilities` is never populated, because there is nothing honest to put there.
Any future fine-tuning effort mixing these two sources needs to either treat
DealProof-sourced dialogues as weight-free (harder to use directly for reward
modeling) or build a genuine utility-elicitation step into the product first —
see the scoping report's data-volume section for why this matters.
"""
import hashlib

from app.offercheck.negotiation import TERMINAL_STATES, final_gap_pct
from app.offercheck.package import PACKAGE_TERMINAL_STATES, total_comp_value
from app.offercheck.store import Session

# The 9 fixed package fields (see schemas.OfferPackage) — described here only as
# type/range metadata for the exported dimension spec, mirroring
# extract_dimensions()'s own "public spec, not weights" shape in eval_harness.py.
PACKAGE_DIMENSION_SPEC = {
    "base": {"type": "int", "min": 0},
    "equity_grant": {"type": "int", "min": 0},
    "vesting_years": {"type": "number", "min": 0},
    "cliff_months": {"type": "number", "min": 0},
    "signing_bonus": {"type": "int", "min": 0},
    "annual_bonus_pct": {"type": "number", "min": 0},
    "remote": {"type": "discrete", "options": ["remote", "hybrid", "onsite"]},
    "start_date_days": {"type": "number", "min": 0},
    "pto_days": {"type": "number", "min": 0},
}
SCALAR_DIMENSION_SPEC = {"value": {"type": "int", "min": 0}}


def _anonymized_id(session_id: str) -> str:
    """Stable one-way id — lets an export be de-duplicated across runs without
    ever round-tripping back to the real session (and therefore the real
    candidate_token/employer_token bearer secrets tied to it)."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:16]


def _is_package_mode(session: Session) -> bool:
    return session.package_round_number > 0


def export_session(session: Session) -> dict | None:
    """
    Converts one Session into an anonymized training-data record, or None if
    the session never reached a real outcome worth exporting (still in
    progress — see TERMINAL_STATES/PACKAGE_TERMINAL_STATES). A session that
    reached a terminal state with NO agreement (WALKAWAY/EXPIRED/DECLINED/
    STALEMATE) is still exported, status "aborted" — matching Yamaguchi's own
    corpus, which includes non-agreements as real negotiation-behavior signal,
    not just successes.
    """
    package_mode = _is_package_mode(session)
    state = session.package_state if package_mode else session.state
    terminal_states = PACKAGE_TERMINAL_STATES if package_mode else TERMINAL_STATES
    if state not in terminal_states:
        return None

    agreed = state == "AGREED"
    rounds = (
        [{"round": r["round"], "actor": r["actor"], "move": r["move"], "value": r["package"]}
         for r in session.package_history]
        if package_mode
        else [{"round": r.round_number, "actor": r.actor, "move": r.move, "value": r.value}
              for r in session.history]
    )
    final_value = None
    final_total_comp = None
    if agreed:
        if package_mode:
            final_value = session.package_agreed
            final_total_comp = total_comp_value(session.package_agreed) if session.package_agreed else None
        else:
            final_value = session.agreed_price

    return {
        "id": _anonymized_id(session.id),
        "status": "completed" if agreed else "aborted",
        "mode": "package" if package_mode else "scalar",
        "role_category": session.competing_offer.role,
        "location": session.competing_offer.location,
        "currency": session.competing_offer.currency,
        "dimensions": PACKAGE_DIMENSION_SPEC if package_mode else SCALAR_DIMENSION_SPEC,
        "rounds": rounds,
        "final_solution": final_value,
        "final_total_comp": final_total_comp,  # package mode only — see package.total_comp_value
        # Only meaningful once AGREED — see negotiation.final_gap_pct /
        # session.market_percentile's own docstrings for why these specific two
        # derived numbers were already judged safe to expose elsewhere in this
        # codebase (they carry outcome-quality signal without a raw private
        # number attached).
        "final_gap_pct": final_gap_pct(session) if not package_mode and agreed else None,
        "market_percentile": session.market_percentile if not package_mode and agreed else None,
    }


def export_sessions(sessions) -> list[dict]:
    """sessions: any iterable of Session objects (e.g. app.offercheck.store's
    current in-memory _SESSIONS.values(), via the admin export route). Skips
    non-terminal sessions (export_session returns None for those) rather than
    raising, since a live store will always have some sessions still in
    progress at any given moment."""
    return [r for s in sessions if (r := export_session(s)) is not None]
