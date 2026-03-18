"""
Props data-authenticity verifier — Phase 3.

Implements a TEE-internal verification protocol inspired by the Props for ML
Security paper (Juels & Koushanfar, 2024, https://eprint.iacr.org/2024/1024).

The core idea: a seller commits to their dataset by advertising a root hash.
Before any negotiation starts the TEE verifies that the seller's chunk-level
proof is internally consistent and matches the advertised root hash.  If it
checks out, the TEE signs the verification result with a TDX quote — giving
buyers a hardware-backed guarantee that the data they're buying matches the
hash they were shown.

Proof format
------------
The seller submits a `seller_proof` dict with the following fields:

  {
    "root_hash":    "<64 hex chars>",          # SHA-256 of the full dataset
    "chunk_hashes": ["<64 hex>", ...],         # SHA-256 of each ordered chunk
    "chunk_count":  <int>,                     # must equal len(chunk_hashes)
    "algorithm":    "sha256"                   # reserved; only sha256 supported
  }

Verification steps (all run inside the TEE)
-------------------------------------------
1. Structural validation — root_hash is 64 lower-case hex chars, chunk_hashes
   are all valid, chunk_count matches the list length, algorithm is "sha256".
2. root_hash consistency — seller_proof["root_hash"] must equal data_hash
   (the hash the seller advertised in the deal).
3. Merkle root recomputation — the verifier independently computes:
     computed_root = SHA-256(raw_bytes(chunk_hash[0])
                           + raw_bytes(chunk_hash[1])
                           + ...
                           + raw_bytes(chunk_hash[N-1]))
   and checks that computed_root == root_hash.
   This is a flat (single-level) concatenation hash, not a binary tree.
   It is deterministic, order-preserving, length-prefixed (defeating preimage
   attacks), and easy to recompute independently.
4. TEE sign — sign_result() is called with:
     {
       "data_hash": data_hash,
       "verified": True,
       "chunk_count": N,
       "algorithm": "sha256"
     }
   The returned TDX quote binds the verification to those exact parameters.

Why flat concatenation instead of a full Merkle tree?
------------------------------------------------------
A full binary Merkle tree would allow selective proof of individual chunks
without revealing the whole set (useful for zero-knowledge scenarios).  For
the hackathon's purpose — proving the full dataset commitment is consistent —
flat concatenation is sufficient, simpler to audit, and trivially reproducible
by any verifier with a SHA-256 library.
"""
import hashlib
from dataclasses import dataclass

from app.tee.attestation import sign_result


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    verified: bool
    data_hash: str
    chunk_count: int = 0
    attestation: str | None = None  # TDX quote from tappd covering this result
    error: str | None = None        # human-readable reason when verified=False


# ---------------------------------------------------------------------------
# Pure helpers (no I/O — safe to unit-test without mocking)
# ---------------------------------------------------------------------------

_HEX_CHARS = frozenset("0123456789abcdef")


def _is_valid_sha256_hex(value: str) -> bool:
    """Return True if `value` is exactly 64 lower-case hex characters."""
    return isinstance(value, str) and len(value) == 64 and all(c in _HEX_CHARS for c in value.lower())


def compute_merkle_root(chunk_hashes: list[str]) -> str:
    """
    Compute the length-prefixed flat Merkle root of an ordered list of
    chunk hashes.

    Algorithm:
      root = SHA-256( len(chunk_hashes).to_bytes(4, 'big')
                    + bytes(chunk_hash[0])
                    + bytes(chunk_hash[1])
                    + ... )

    The 4-byte length prefix defeats preimage attacks where an attacker
    could substitute N chunks of 32 bytes with 1 chunk of 32*N bytes and
    produce the same root hash.

    Returns a 64-char lower-case hex string.
    Raises ValueError if any entry is not a valid SHA-256 hex string.
    """
    if not chunk_hashes:
        raise ValueError("chunk_hashes must be a non-empty list")
    length_prefix = len(chunk_hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h.lower()) for h in chunk_hashes)
    return hashlib.sha256(raw).hexdigest()


def validate_proof_structure(data_hash: str, seller_proof: dict) -> str | None:
    """
    Validate the structure of a seller_proof dict.

    Returns None if valid, or an error message string describing the first
    structural problem found.  Does not verify the Merkle root — that is
    done by verify_data_authenticity().
    """
    if not _is_valid_sha256_hex(data_hash):
        return f"data_hash is not a valid SHA-256 hex string (got: {data_hash!r})"

    required = {"root_hash", "chunk_hashes", "chunk_count", "algorithm"}
    missing = required - set(seller_proof.keys())
    if missing:
        return f"seller_proof missing required fields: {sorted(missing)}"

    if seller_proof.get("algorithm") != "sha256":
        return f"unsupported algorithm {seller_proof.get('algorithm')!r} — only 'sha256' is supported"

    root_hash = seller_proof.get("root_hash", "")
    if not _is_valid_sha256_hex(root_hash):
        return f"seller_proof.root_hash is not a valid SHA-256 hex string"

    chunk_hashes = seller_proof.get("chunk_hashes", [])
    if not isinstance(chunk_hashes, list) or len(chunk_hashes) == 0:
        return "seller_proof.chunk_hashes must be a non-empty list"

    for i, h in enumerate(chunk_hashes):
        if not _is_valid_sha256_hex(h):
            return f"seller_proof.chunk_hashes[{i}] is not a valid SHA-256 hex string"

    declared_count = seller_proof.get("chunk_count")
    if not isinstance(declared_count, int) or declared_count != len(chunk_hashes):
        return (
            f"seller_proof.chunk_count ({declared_count!r}) does not match "
            f"len(chunk_hashes) ({len(chunk_hashes)})"
        )

    # Duplicate chunk hashes would allow a seller to deliver fewer unique
    # chunks than claimed (e.g. 5 identical hashes = 1 real chunk repeated).
    normalised = [h.lower() for h in chunk_hashes]
    if len(set(normalised)) != len(normalised):
        return "seller_proof.chunk_hashes contains duplicate entries"

    return None  # all good


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def verify_data_authenticity(data_hash: str, seller_proof: dict) -> VerificationResult:
    """
    Verify that the seller's dataset proof is consistent with data_hash.

    Runs entirely inside the TEE.  On success, calls sign_result() to produce
    a TDX attestation quote that binds to the verification outcome.

    Parameters
    ----------
    data_hash : str
        The SHA-256 hash of the dataset as advertised in the deal
        (from DealCreate.data_hash).
    seller_proof : dict
        The structured proof supplied by the seller (see module docstring
        for the expected format).

    Returns
    -------
    VerificationResult
        .verified=True  and .attestation set (TDX quote) on success.
        .verified=False and .error set with a human-readable reason on failure.
    """
    # Step 1 — structural validation
    error = validate_proof_structure(data_hash, seller_proof)
    if error:
        return VerificationResult(verified=False, data_hash=data_hash, error=error)

    chunk_hashes: list[str] = [h.lower() for h in seller_proof["chunk_hashes"]]
    root_hash: str = seller_proof["root_hash"].lower()
    chunk_count: int = seller_proof["chunk_count"]

    # Step 2 — root_hash must match the advertised data_hash
    if root_hash != data_hash.lower():
        return VerificationResult(
            verified=False,
            data_hash=data_hash,
            error=(
                f"seller_proof.root_hash ({root_hash[:16]}…) "
                f"does not match data_hash ({data_hash[:16]}…)"
            ),
        )

    # Step 3 — recompute Merkle root from chunk hashes and compare
    try:
        computed_root = compute_merkle_root(chunk_hashes)
    except ValueError as exc:
        return VerificationResult(
            verified=False,
            data_hash=data_hash,
            error=f"Merkle root computation failed: {exc}",
        )

    if computed_root != root_hash:
        return VerificationResult(
            verified=False,
            data_hash=data_hash,
            error=(
                f"Merkle root mismatch: computed {computed_root[:16]}… "
                f"but seller claimed {root_hash[:16]}…"
            ),
        )

    # Step 4 — all checks passed; get a TDX attestation over the result
    attestation = await sign_result(
        {
            "data_hash": data_hash.lower(),
            "verified": True,
            "chunk_count": chunk_count,
            "algorithm": "sha256",
        }
    )

    return VerificationResult(
        verified=True,
        data_hash=data_hash.lower(),
        chunk_count=chunk_count,
        attestation=attestation,
    )
