"""
Generates valid seller_proof payloads for testing the DealProof API.
Run this script to get ready-to-paste JSON for /docs or curl.
"""
import hashlib
import json


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_merkle_root(chunk_hashes: list[str]) -> str:
    """Matches app/props/verifier.py: length-prefixed flat concatenation."""
    N = len(chunk_hashes)
    raw = N.to_bytes(4, "big") + b"".join(bytes.fromhex(h) for h in chunk_hashes)
    return hashlib.sha256(raw).hexdigest()


def make_proof(chunks: list[bytes]) -> tuple[str, dict]:
    """Returns (data_hash, seller_proof) ready to post."""
    chunk_hashes = [sha256(c) for c in chunks]
    root_hash = compute_merkle_root(chunk_hashes)
    proof = {
        "algorithm": "sha256",
        "chunk_count": len(chunk_hashes),
        "chunk_hashes": chunk_hashes,
        "root_hash": root_hash,
    }
    return root_hash, proof


def make_request(
    buyer_budget: float,
    floor_price: float,
    buyer_requirements: str,
    data_description: str,
    chunks: list[bytes],
) -> dict:
    data_hash, seller_proof = make_proof(chunks)
    return {
        "buyer_budget": buyer_budget,
        "floor_price": floor_price,
        "buyer_requirements": buyer_requirements,
        "data_description": data_description,
        "data_hash": data_hash,
        "seller_proof": seller_proof,
    }


# ---------------------------------------------------------------------------
# Scenario A — Happy path: 3-chunk dataset, budget well above floor
# ---------------------------------------------------------------------------
scenario_a = make_request(
    buyer_budget=120,
    floor_price=60,
    buyer_requirements="US demographic data segmented by age group for market research",
    data_description="US census demographic dataset split into three regional chunks",
    chunks=[
        b"US_CENSUS_CHUNK_1: Northeast region demographics, 2020, rows 0-33333",
        b"US_CENSUS_CHUNK_2: Midwest + South region demographics, 2020, rows 33334-66666",
        b"US_CENSUS_CHUNK_3: West region demographics, 2020, rows 66667-100000",
    ],
)

# ---------------------------------------------------------------------------
# Scenario B — Happy path: single-chunk dataset (edge case for chunk_count=1)
# ---------------------------------------------------------------------------
scenario_b = make_request(
    buyer_budget=50,
    floor_price=30,
    buyer_requirements="Compact medical trial summary dataset",
    data_description="Single anonymised CSV of Phase-II trial results",
    chunks=[
        b"MEDICAL_TRIAL_DATA: anonymised patient outcomes, trial XR-2024, n=500",
    ],
)

# ---------------------------------------------------------------------------
# Scenario C — Happy path: large chunk count (10 chunks)
# ---------------------------------------------------------------------------
scenario_c = make_request(
    buyer_budget=500,
    floor_price=200,
    buyer_requirements="Full social media sentiment corpus for NLP training",
    data_description="10-part Twitter sentiment dataset, 2023 Q1-Q4",
    chunks=[f"TWITTER_SENTIMENT_CHUNK_{i:02d}: shard {i} of 10, Q{(i-1)//3+1} 2023".encode() for i in range(1, 11)],
)

# ---------------------------------------------------------------------------
# Scenario D — No seller_proof (skip verification, basic flow)
# ---------------------------------------------------------------------------
scenario_d = {
    "buyer_budget": 80,
    "floor_price": 40,
    "buyer_requirements": "Financial time-series data for backtesting",
    "data_description": "Daily OHLCV stock data, S&P500, 2015-2023",
    "data_hash": "473287f8298dba7163a897908958f7c0eae733e25d2e027992ea2edc9bed2fa8",
    # seller_proof intentionally omitted — verification skipped
}

# ---------------------------------------------------------------------------
# Scenario E — Invalid: root_hash mismatch (tampered proof)
# ---------------------------------------------------------------------------
_, good_proof = make_proof([b"real data chunk"])
tampered_proof = dict(good_proof)
tampered_proof["root_hash"] = "a" * 64   # wrong root
scenario_e = {
    "buyer_budget": 100,
    "floor_price": 50,
    "buyer_requirements": "Test: tampered root_hash should be rejected",
    "data_description": "Adversarial proof — root_hash does not match data_hash",
    "data_hash": "a" * 64,  # matches tampered root_hash so it passes field check...
    "seller_proof": tampered_proof,
    # ^ will fail: computed Merkle root != claimed root_hash
}

# ---------------------------------------------------------------------------
# Scenario F — Invalid: duplicate chunk_hashes (should be rejected)
# ---------------------------------------------------------------------------
dup_hash = sha256(b"same chunk")
scenario_f_proof = {
    "algorithm": "sha256",
    "chunk_count": 2,
    "chunk_hashes": [dup_hash, dup_hash],
    "root_hash": compute_merkle_root([dup_hash, dup_hash]),
}
scenario_f = {
    "buyer_budget": 100,
    "floor_price": 50,
    "buyer_requirements": "Test: duplicate chunk hashes should be rejected",
    "data_description": "Proof with two identical chunk_hashes",
    "data_hash": compute_merkle_root([dup_hash, dup_hash]),
    "seller_proof": scenario_f_proof,
}

# ---------------------------------------------------------------------------
# Scenario G — Invalid: budget below floor (schema-level rejection)
# ---------------------------------------------------------------------------
scenario_g = {
    "buyer_budget": 30,
    "floor_price": 100,
    "buyer_requirements": "Test: buyer_budget < floor_price must be rejected at schema level",
    "data_description": "Any dataset",
    "data_hash": "473287f8298dba7163a897908958f7c0eae733e25d2e027992ea2edc9bed2fa8",
}

# ---------------------------------------------------------------------------
# Scenario H — Two-step flow (same payload as A, printed separately for each step)
# ---------------------------------------------------------------------------
# Step 1: POST /api/deals  (use this payload)
# Step 2: POST /api/deals/{deal_id}/negotiate  (no body needed)
# Step 3: GET  /api/deals/{deal_id}/status
# Step 4: GET  /api/deals/{deal_id}/verification
# Step 5: GET  /api/deals/{deal_id}/attestation
scenario_h_step1 = scenario_a  # identical payload to A

# ---------------------------------------------------------------------------
# Scenario I — Concurrent negotiate calls (optimistic lock)
# ---------------------------------------------------------------------------
# Step 1: POST /api/deals with this payload → get deal_id
# Step 2: fire two simultaneous POST /api/deals/{deal_id}/negotiate requests
#         → one returns 200, the other returns 409
scenario_i_step1 = scenario_a  # any valid payload works

# ---------------------------------------------------------------------------
# Scenario J — Status polling after verification_failed
# ---------------------------------------------------------------------------
# Step 1: POST /api/deals with this payload → get deal_id
# Step 2: POST /api/deals/{deal_id}/negotiate → 400 verification error
# Step 3: GET  /api/deals/{deal_id}/status    → status: verification_failed
# Step 4: GET  /api/deals/{deal_id}/attestation → 404
# Step 5: GET  /api/deals/{deal_id}/verification → verified: false, error present
scenario_j_step1 = scenario_e  # tampered proof — same payload as E

# ---------------------------------------------------------------------------
# Print all scenarios
# ---------------------------------------------------------------------------
scenarios = {
    "A — Happy path (3 chunks)": scenario_a,
    "B — Happy path (1 chunk)": scenario_b,
    "C — Happy path (10 chunks)": scenario_c,
    "D — No seller_proof (skip verification)": scenario_d,
    "E — Invalid: tampered root_hash": scenario_e,
    "F — Invalid: duplicate chunk_hashes": scenario_f,
    "G — Invalid: budget below floor": scenario_g,
}

scenarios_hij = {
    "H — Two-step flow (Step 1: POST /api/deals)": scenario_h_step1,
    "I — Concurrent lock (Step 1: POST /api/deals)": scenario_i_step1,
    "J — Verification failed (Step 1: POST /api/deals)": scenario_j_step1,
}

for name, payload in scenarios.items():
    print(f"\n{'='*70}")
    print(f"  SCENARIO {name}")
    print(f"{'='*70}")
    print(json.dumps(payload, indent=2))

print(f"\n\n{'#'*70}")
print("  SCENARIOS H / I / J  — multi-step flows")
print(f"{'#'*70}")
print("""
These scenarios require multiple HTTP calls. Use the payloads below for
Step 1 (POST /api/deals) to get a deal_id, then follow the steps in TESTING.md.
""")
for name, payload in scenarios_hij.items():
    print(f"\n{'='*70}")
    print(f"  SCENARIO {name}")
    print(f"{'='*70}")
    print(json.dumps(payload, indent=2))
