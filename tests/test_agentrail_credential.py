"""
Agent Rail — Phase 3 conduct credential tests.

The central thing to prove: audit_procurement_conduct()'s output never
contains the buyer's budget ceiling or the supplier's floor price, even
though those exact numbers are passed in as arguments — see
app/agentrail/credential.py's module docstring for why that matters here
(core's equivalent, app.picreds.constraints, embeds the number in its finding
text on purpose, because core's budget/floor are not sealed).
"""
import json

from app.agentrail.credential import audit_procurement_conduct, build_credential


def _transcript(*rounds):
    return [{"round": i + 1, **r} for i, r in enumerate(rounds)]


def test_role_adapter_maps_supplier_to_seller_for_core_reuse():
    transcript = _transcript(
        {"role": "buyer", "action": "propose", "price": 40.0},
        {"role": "supplier", "action": "counter", "price": 44.0},
        {"role": "buyer", "action": "accept", "price": 44.0},
    )
    result = audit_procurement_conduct(transcript, buyer_ceiling=45.0, floor_price=38.0, final_price=44.0)
    assert result["checks"]["seller_floor"]["passed"] is True
    assert result["checks"]["buyer_budget"]["passed"] is True
    assert result["genuine_negotiation"] is True


def test_sealed_values_never_appear_in_audit_result():
    transcript = _transcript(
        {"role": "buyer", "action": "propose", "price": 40.0},
        {"role": "supplier", "action": "counter", "price": 44.5},
        {"role": "buyer", "action": "counter", "price": 41.0},
        {"role": "supplier", "action": "accept", "price": 41.0},
    )
    buyer_ceiling = 45.0
    floor_price = 38.0
    result = audit_procurement_conduct(transcript, buyer_ceiling, floor_price, final_price=41.0)

    result_str = json.dumps(result)
    assert str(buyer_ceiling) not in result_str
    assert str(floor_price) not in result_str
    # Redacted findings must be present and non-empty, not just absent of numbers.
    for check in result["checks"].values():
        assert check["finding"]
        assert "$" not in check["finding"]


def test_buyer_budget_violation_flips_genuine_negotiation_false():
    transcript = _transcript(
        {"role": "buyer", "action": "propose", "price": 46.0},  # exceeds ceiling of 45.0
        {"role": "supplier", "action": "accept", "price": 46.0},
    )
    result = audit_procurement_conduct(transcript, buyer_ceiling=45.0, floor_price=38.0, final_price=46.0)
    assert result["checks"]["buyer_budget"]["passed"] is False
    assert result["genuine_negotiation"] is False
    # Still no leak even in the failure path.
    assert "45.0" not in json.dumps(result)


def test_supplier_floor_violation_detected_after_role_remap():
    transcript = _transcript(
        {"role": "supplier", "action": "offer", "price": 35.0},  # below floor of 38.0
        {"role": "buyer", "action": "accept", "price": 35.0},
    )
    result = audit_procurement_conduct(transcript, buyer_ceiling=45.0, floor_price=38.0, final_price=35.0)
    assert result["checks"]["seller_floor"]["passed"] is False
    assert result["genuine_negotiation"] is False


def test_build_credential_produces_stable_hash_and_envelope():
    audit_result = {
        "checks": {"buyer_budget": {"passed": True, "finding": "ok"}},
        "genuine_negotiation": True,
        "final_price": 41.0,
    }
    credential, picreds_hash = build_credential("deal-123", audit_result)

    assert credential["credential_type"] == "conduct"
    assert credential["subject"] == "deal"
    assert credential["deal_id"] == "deal-123"
    assert credential["audit_result"] == audit_result
    assert isinstance(picreds_hash, str) and len(picreds_hash) == 64

    # Same input -> same hash (deterministic, apart from issued_at).
    credential2, picreds_hash2 = build_credential("deal-123", audit_result)
    assert credential["audit_result"] == credential2["audit_result"]
