"""
Proof-of-concept run of the training-data export pipeline (app/offercheck/export.py).

Builds a handful of realistic sessions through the SAME real state-machine
functions the product itself uses (app.offercheck.store.create_session,
app.offercheck.negotiation.apply_move/apply_approval_vote,
app.offercheck.package.apply_package_move) — not fabricated export JSON — then
runs the real export pipeline against them and writes the anonymized result to
eval_results/training_data_sample_<timestamp>.json.

This is demo/synthetic data (no real users), built specifically so the export
pipeline has something real to run against without needing a live server with
real production sessions in memory. Confirms end-to-end: session creation ->
negotiation -> terminal state -> export -> anonymized JSON on disk.

Run: python scripts/export_training_sample.py
"""
import json
from datetime import datetime
from pathlib import Path

from app.offercheck import export, negotiation, package, store, verifier
from app.offercheck.schemas import CompetingOffer, OfferPackage


def _scalar_agreed_session():
    offer = CompetingOffer(
        company="Example Corp", role="Senior Backend Engineer", base_salary=180_000,
        equity_value=40_000, bonus=15_000, start_date="2026-10-01",
        location="Seattle, WA", currency="USD",
    )
    consistency = verifier.check_consistency(offer, 190_000)
    session = store.create_session(offer, 190_000, consistency)
    negotiation.set_employer_band(session, 160_000, 180_000, 200_000)
    negotiation.apply_move(session, actor="employer", move="counter", value=175_000)
    negotiation.apply_move(session, actor="candidate", move="counter", value=185_000)
    negotiation.apply_move(session, actor="employer", move="accept", value=None)
    negotiation.apply_approval_vote(session, actor="employer", decision="approve")
    negotiation.apply_approval_vote(session, actor="candidate", decision="approve")
    return session


def _scalar_walkaway_session():
    offer = CompetingOffer(
        company="Another Corp", role="Data Scientist", base_salary=150_000,
        equity_value=20_000, bonus=10_000, start_date="2026-11-01",
        location="London", currency="GBP",
    )
    consistency = verifier.check_consistency(offer, 175_000)
    session = store.create_session(offer, 175_000, consistency)
    negotiation.set_employer_band(session, 120_000, 135_000, 150_000)
    negotiation.apply_move(session, actor="employer", move="walk", value=None)
    return session


def _package_agreed_session():
    offer = CompetingOffer(
        company="Third Corp", role="Staff Engineer", base_salary=210_000,
        equity_value=80_000, bonus=20_000, start_date="2026-09-15",
        location="Austin, TX", currency="USD",
    )
    consistency = verifier.check_consistency(offer, 220_000)
    session = store.create_session(offer, 220_000, consistency)
    negotiation.set_employer_band(session, 190_000, 210_000, 230_000)

    opening_employer = OfferPackage(base=205_000, equity_grant=70_000, signing_bonus=10_000).model_dump()
    package.apply_package_move(session, actor="employer", move="counter", package=opening_employer)
    package.apply_package_move(session, actor="candidate", move="accept", package=None)
    package.apply_package_approval_vote(session, actor="employer", decision="approve")
    package.apply_package_approval_vote(session, actor="candidate", decision="approve")
    return session


def main():
    store.reset()
    sessions = [_scalar_agreed_session(), _scalar_walkaway_session(), _package_agreed_session()]

    records = export.export_sessions(sessions)

    out_dir = Path("eval_results")
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = out_dir / f"training_data_sample_{stamp}.json"
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"Exported {len(records)} record(s) to {out_path}")
    for r in records:
        print(f"  {r['id']}  mode={r['mode']}  status={r['status']}  role={r['role_category']!r}  rounds={len(r['rounds'])}")


if __name__ == "__main__":
    main()
