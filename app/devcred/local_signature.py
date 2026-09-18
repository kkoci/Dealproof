"""
Route C signature verification — Dev Credential's "local .git upload" fallback.

Division of responsibility (this is the answer to the design ambiguity flagged in the
originating request — "confirm this in your read of the design before assuming"):

  - The FRONTEND (frontend/src/pages/devcred/LocalGitUpload.jsx) does a *structural*
    pre-check only: does the pasted signature look like a well-formed
    "-----BEGIN SSH SIGNATURE-----" armor block, does the public key look like a valid
    "ssh-ed25519 AAAA..." line. This is a fast-fail UX convenience, not a security
    boundary — a page can't be trusted to police itself, and nothing stops a caller from
    hitting the API directly with a bypassed frontend.
  - The SERVER (this module, called from app.devcred.routes) performs the actual
    cryptographic verification. This is the only place "verified via local .git
    signature" is genuinely verified rather than merely a nicely-formatted unverified
    claim — which would collapse Route C into Route D (self-reported) in all but name.

Signing contract (deliberately NOT git's native per-commit `git commit -S` signature —
see below for why): the client generates ONE fresh SSH signature at submission time,
over a canonical JSON payload binding this exact commit set to this exact credential
request:

    ssh-keygen -Y sign -n devcred-route-c -f ~/.ssh/id_ed25519 <payload file>

where <payload file> contains the UTF-8 bytes of
    json.dumps({"credential_id": ..., "developer_handle": ..., "corpus_root": ...},
                sort_keys=True, separators=(",", ":"))
and `corpus_root` is computed (client-side, for the user's own visibility, and
independently recomputed server-side as the source of truth) via
git_hasher.compute_repo_corpus_root() over the submitted commit envelopes.

Why not verify git's native embedded commit signatures instead: that would require
byte-exact reconstruction of the git commit object (tree/parent/author/committer lines
in git's exact serialization, with the gpgsig trailer stripped) for every submitted
commit, which is a much larger and more fragile parsing surface for marginal benefit —
one fresh signature over a small canonical payload proves the same thing this route
actually needs ("the person submitting this right now controls a key GitHub associates,
or once associated, with this account"), without needing to re-derive git's internal
object format at all. This is a deliberate scope decision, not an oversight.

Key type support: ssh-ed25519 only. RSA and ECDSA SSH keys are rejected with a clear
error rather than silently mis-verified — narrower but correct, matching this
codebase's own precedent (app.offercheck.integrations.workday's explicit stub,
market_data's national-only granularity) of a disclosed limitation over false coverage.

GPG (signature_format="gpg") is supported best-effort via the `gpg` binary through
python-gnupg. If the binary isn't present in the deployment image, verification fails
closed (returns invalid, never fabricates a pass) — flagged, not silently narrowed.

NOT verified against a real `ssh-keygen -Y sign` binary in this environment — the
SSHSIG wire-format implementation below follows OpenSSH's published PROTOCOL.sshsig
specification, and is unit-tested via a self-constructed reference blob (round-tripped
against this module's own encoder in tests/test_devcred.py), but has not been
cross-checked against genuine `ssh-keygen` output. Confirm with a real signature before
relying on this in production — same caveat this codebase already applies to BLS/ONS/
Stripe/Greenhouse/Lever request shapes that were implemented from documentation alone.
"""
import base64
import hashlib
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SSHSIG_MAGIC = b"SSHSIG"
SSHSIG_NAMESPACE = "devcred-route-c"
SUPPORTED_HASH_ALGS = {"sha256": hashlib.sha256, "sha512": hashlib.sha512}


@dataclass
class SignatureVerificationResult:
    valid: bool
    error: str | None = None
    key_fingerprint: str | None = None  # SHA256 fingerprint of the verifying public key


def _read_string(buf: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(buf):
        raise ValueError("truncated SSH wire string (length prefix)")
    (length,) = struct.unpack(">I", buf[offset:offset + 4])
    offset += 4
    if offset + length > len(buf):
        raise ValueError("truncated SSH wire string (body)")
    return buf[offset:offset + length], offset + length


def _write_string(value: bytes) -> bytes:
    return struct.pack(">I", len(value)) + value


def _parse_ssh_ed25519_public_key_blob(blob: bytes) -> Ed25519PublicKey:
    key_type, offset = _read_string(blob, 0)
    if key_type != b"ssh-ed25519":
        raise ValueError(f"unsupported SSH key type: {key_type!r} (only ssh-ed25519 is supported)")
    key_bytes, offset = _read_string(blob, offset)
    if len(key_bytes) != 32:
        raise ValueError("malformed ssh-ed25519 public key (expected 32-byte point)")
    return Ed25519PublicKey.from_public_bytes(key_bytes)


def parse_openssh_public_key_line(line: str) -> tuple[Ed25519PublicKey, bytes]:
    """
    Parses a single-line OpenSSH public key ("ssh-ed25519 AAAA... comment").
    Returns (public_key_object, raw_wire_blob) — the raw blob is compared against
    the key embedded inside the SSHSIG signature itself, so a submitted public_key
    that doesn't match the key that actually produced the signature is rejected
    rather than silently ignored.
    """
    parts = line.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("public_key must be an OpenSSH ssh-ed25519 line (\"ssh-ed25519 AAAA...\")")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except Exception as exc:
        raise ValueError(f"public_key is not valid base64: {exc}") from exc
    return _parse_ssh_ed25519_public_key_blob(blob), blob


def _key_fingerprint(wire_blob: bytes) -> str:
    digest = hashlib.sha256(wire_blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _strip_armor(armored: str, begin: str, end: str) -> bytes:
    lines = armored.strip().splitlines()
    if not lines or lines[0].strip() != begin or lines[-1].strip() != end:
        raise ValueError(f"missing {begin} / {end} armor markers")
    body = "".join(line.strip() for line in lines[1:-1])
    return base64.b64decode(body, validate=True)


def _build_signed_data(namespace: str, hash_alg: str, message_hash: bytes) -> bytes:
    """The exact byte sequence ssh-keygen signs over — PROTOCOL.sshsig 'signed data'."""
    out = SSHSIG_MAGIC
    out += _write_string(namespace.encode())
    out += _write_string(b"")  # reserved
    out += _write_string(hash_alg.encode())
    out += _write_string(message_hash)
    return out


def verify_ssh_signature(payload: bytes, signature_armored: str, public_key_line: str) -> SignatureVerificationResult:
    """
    Verifies an OpenSSH `ssh-keygen -Y sign -n devcred-route-c` detached signature
    over `payload`, per PROTOCOL.sshsig. Rejects (does not silently ignore) a
    namespace mismatch, an unsupported key/hash algorithm, or a submitted
    public_key that doesn't match the key embedded in the signature blob itself.
    """
    try:
        blob = _strip_armor(signature_armored, "-----BEGIN SSH SIGNATURE-----", "-----END SSH SIGNATURE-----")

        if blob[:6] != SSHSIG_MAGIC:
            return SignatureVerificationResult(False, "not a valid SSHSIG blob (bad magic)")
        offset = 6
        (version,) = struct.unpack(">I", blob[offset:offset + 4])
        offset += 4
        if version != 1:
            return SignatureVerificationResult(False, f"unsupported SSHSIG version: {version}")

        pubkey_blob, offset = _read_string(blob, offset)
        namespace, offset = _read_string(blob, offset)
        _reserved, offset = _read_string(blob, offset)
        hash_alg, offset = _read_string(blob, offset)
        signature_field, offset = _read_string(blob, offset)

        namespace_str = namespace.decode(errors="replace")
        if namespace_str != SSHSIG_NAMESPACE:
            return SignatureVerificationResult(
                False, f"signature namespace {namespace_str!r} does not match expected {SSHSIG_NAMESPACE!r}"
            )

        hash_alg_str = hash_alg.decode(errors="replace")
        hasher = SUPPORTED_HASH_ALGS.get(hash_alg_str)
        if hasher is None:
            return SignatureVerificationResult(False, f"unsupported hash algorithm: {hash_alg_str!r}")

        sig_key_type, sig_offset = _read_string(signature_field, 0)
        if sig_key_type != b"ssh-ed25519":
            return SignatureVerificationResult(
                False, f"unsupported signature key type: {sig_key_type!r} (only ssh-ed25519 is supported)"
            )
        raw_signature, _ = _read_string(signature_field, sig_offset)

        embedded_key = _parse_ssh_ed25519_public_key_blob(pubkey_blob)

        declared_key, declared_blob = parse_openssh_public_key_line(public_key_line)
        if declared_blob != pubkey_blob:
            return SignatureVerificationResult(
                False, "submitted public_key does not match the key embedded in the signature"
            )

        message_hash = hasher(payload).digest()
        signed_data = _build_signed_data(namespace_str, hash_alg_str, message_hash)

        embedded_key.verify(raw_signature, signed_data)

        return SignatureVerificationResult(True, key_fingerprint=_key_fingerprint(pubkey_blob))

    except InvalidSignature:
        return SignatureVerificationResult(False, "signature does not verify against the provided key")
    except Exception as exc:
        return SignatureVerificationResult(False, f"malformed signature or key: {exc}")


def verify_gpg_signature(payload: bytes, signature_armored: str, public_key_armored: str) -> SignatureVerificationResult:
    """
    Best-effort GPG verification via the `gpg` binary (python-gnupg). Fails closed
    (never fabricates a pass) if the binary isn't available in this deployment —
    flagged as a real limitation, not silently narrowed: confirm `gpg` is present in
    the production image before relying on this path.
    """
    try:
        import gnupg
    except ImportError:
        return SignatureVerificationResult(False, "GPG verification unavailable — python-gnupg not installed")

    import tempfile

    try:
        with tempfile.TemporaryDirectory() as gnupghome:
            gpg = gnupg.GPG(gnupghome=gnupghome)
            import_result = gpg.import_keys(public_key_armored)
            if not import_result.fingerprints:
                return SignatureVerificationResult(False, "could not import GPG public key")
            fingerprint = import_result.fingerprints[0]

            with tempfile.NamedTemporaryFile(suffix=".sig", delete=False) as sig_file:
                sig_file.write(signature_armored.encode())
                sig_path = sig_file.name
            with tempfile.NamedTemporaryFile(delete=False) as data_file:
                data_file.write(payload)
                data_path = data_file.name

            verified = gpg.verify_data(sig_path, open(data_path, "rb").read())
            if verified.valid:
                return SignatureVerificationResult(True, key_fingerprint=fingerprint)
            return SignatureVerificationResult(False, "GPG signature did not verify")
    except Exception as exc:
        return SignatureVerificationResult(False, f"GPG verification failed: {exc}")


def verify_signature(
    payload: bytes, signature: str, public_key: str, signature_format: str
) -> SignatureVerificationResult:
    """Dispatches to the SSH or GPG verifier. Unknown formats fail closed."""
    if signature_format == "ssh":
        return verify_ssh_signature(payload, signature, public_key)
    if signature_format == "gpg":
        return verify_gpg_signature(payload, signature, public_key)
    return SignatureVerificationResult(False, f"unsupported signature_format: {signature_format!r}")


def canonical_payload(credential_id: str, developer_handle: str, corpus_root: str) -> bytes:
    """The exact byte sequence Route C submissions must be signed over. Must match
    the frontend's canonicalisation exactly — sorted keys, no extra whitespace."""
    import json
    return json.dumps(
        {"credential_id": credential_id, "developer_handle": developer_handle, "corpus_root": corpus_root},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
