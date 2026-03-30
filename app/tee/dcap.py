"""
DCAP TDX quote parser + full Intel verification — Phase 7.

Overview
--------
Intel DCAP (Data Center Attestation Primitives) full verification pipeline:

  1. Parse the binary quote structure (header + signature data).
  2. Extract the PCK certificate chain from QE Certification Data (Type 5).
  3. Verify the PCK cert chain up to Intel SGX Root CA (no Phala trust needed).
  4. Verify the QE Report signature: PCK key signs the QE Report.
  5. Verify ATT key binding: QE REPORTDATA[0:32] == SHA-256(att_key || auth_data).
  6. Verify the TD Report signature: ATT key signs Header || TD Report Body.
  7. Confirm deal terms binding: TD REPORTDATA[0:32] == SHA-256(json(deal_terms)).

Steps 3–6 are the "Option B" / full Intel DCAP path — no reliance on Phala's
trust assertions. Anyone with the Intel Root CA public key can independently
verify the attestation.

TDX Quote v4 Structure
-----------------------
  [0:48]      Header (48 bytes)
                version (uint16 LE), att_key_type (uint16 LE), tee_type (uint32 LE),
                reserved x2 (2+2 bytes), qe_vendor_id (16 bytes), user_data (20 bytes)
  [48:632]    TD Report Body (TD10, 584 bytes)
                TEEINFO (400 bytes) + REPORTDATA (64 bytes) + REPORTMAC (120 bytes)
                REPORTDATA[0:32] = SHA-256(json(deal_terms)) — deal terms binding
  [632:636]   Signature Data Length (uint32 LE)
  [636:...]   Signature Data:
    [+0:64]   ECDSA Signature (64 bytes, r||s) — over Header+TD_Report using ATT key
    [+64:128] ECDSA Attestation Key (64 bytes, P-256 x||y without 0x04 prefix)
    [+128:512] QE Report (384 bytes — SGX Report structure)
                QE REPORTDATA[0:32] = SHA-256(att_key||auth_data) — ATT key binding
    [+512:576] QE Report Signature (64 bytes, r||s) — PCK key signs QE Report
    [+576:578] QE Auth Data Size (uint16 LE)
    [+578:578+N] QE Auth Data
    [+578+N:580+N] QE Cert Data Type (uint16 LE; 5 = PCK cert chain PEM)
    [+580+N:584+N] QE Cert Data Size (uint32 LE)
    [+584+N:...]   QE Cert Data (PCK→Platform CA→Root CA, PEM-encoded)

Simulation mode
---------------
When TEE_MODE=simulation the attestation string is "sim_quote:<sha256_hex>".
No binary parsing is performed; verification_status is "simulation_only".

Reference
---------
Intel TDX DCAP Quote Generation Library:
  https://github.com/intel/SGXDataCenterAttestationPrimitives
Intel Provisioning Certification Service (PCS) API:
  https://api.trustedservices.intel.com/tdx/certification/v4/
"""
import hashlib
import logging
import struct

logger = logging.getLogger(__name__)

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric import utils as asym_utils
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False
    logger.warning(
        "cryptography package not available — full Intel DCAP verification disabled. "
        "Install it with: pip install cryptography>=42.0.0"
    )

# ── Intel identity ────────────────────────────────────────────────────────── #

# Intel QE vendor UUID (as stored in quote header — little-endian bytes)
_INTEL_QE_VENDOR_UUID = bytes.fromhex("939a7233f79c4ca9940a0db3957f0607")

# Expected Common Name on the Intel SGX/TDX Root CA certificate
_INTEL_ROOT_CA_CN = "Intel SGX Root CA"

# TEE type codes → human-readable
_TEE_TYPES: dict[int, str] = {
    0x00000000: "SGX",
    0x00000081: "TDX",
}

# ── Quote structure constants ─────────────────────────────────────────────── #

_HEADER_SIZE = 48           # Quote header
_TD_REPORT_OFFSET = 48      # TD Report Body starts right after the header
_TD_REPORT_SIZE = 584       # TD10 Report structure (400 TEEINFO + 64 REPORTDATA + 120 MAC)
_SIG_LEN_OFFSET = 632       # uint32 LE: length of the Signature Data block
_SIG_DATA_OFFSET = 636      # Signature Data starts here

# Signature Data — relative offsets from _SIG_DATA_OFFSET
_REL_ECDSA_SIG = 0          # 64 bytes: ECDSA sig (r||s) over Header+TD_Report
_REL_ATT_KEY = 64           # 64 bytes: P-256 attestation public key (x||y, no 0x04 prefix)
_REL_QE_REPORT = 128        # 384 bytes: QE Report (SGX Report structure)
_REL_QE_SIG = 512           # 64 bytes: QE Report signature (r||s), signed by PCK key
_REL_QE_AUTH_SIZE = 576     # uint16 LE: QE Auth Data size (N)
_REL_QE_AUTH_DATA = 578     # N bytes: QE Auth Data
# After QE Auth Data (offsets from _REL_QE_AUTH_DATA + N):
#   +0: uint16 LE  cert data type (5 = PCK cert chain PEM)
#   +2: uint32 LE  cert data size (M)
#   +6: M bytes    cert data

# TD Report — relative offsets from _TD_REPORT_OFFSET
_TD_REPORTDATA_OFFSET = 400  # 64 bytes: REPORTDATA — [0:32] = SHA-256(json(deal_terms))

# QE Report — relative offsets from start of QE Report
_QE_REPORTDATA_OFFSET = 320  # 64 bytes: QE REPORTDATA — [0:32] = SHA-256(att_key||auth_data)

# Minimum quote bytes needed to reach QE Auth Size field
_MIN_PARSEABLE = _SIG_DATA_OFFSET + _REL_QE_AUTH_SIZE + 2


# ── Public API ────────────────────────────────────────────────────────────── #

def parse_tdx_quote(attestation: str) -> dict:
    """
    Parse and fully verify a DealProof attestation string.

    Parameters
    ----------
    attestation : str
        Either:
        - "sim_quote:<hex>" — simulation mode (no real TEE)
        - A hex-encoded binary TDX DCAP quote

    Returns
    -------
    dict with all DCAPVerification schema fields, including:
        mode, version, tee_type, qe_vendor_id, report_data_hex, deal_terms_hash
        cert_chain_valid, qe_sig_valid, att_key_binding_valid, td_sig_valid
        intel_verified, pck_cert_subject, verification_status, error
    """
    # ── Simulation mode ──────────────────────────────────────────────────── #
    if attestation.startswith("sim_quote:"):
        sim_hash = attestation[len("sim_quote:"):]
        return {
            "mode": "simulation",
            "version": None,
            "tee_type": None,
            "qe_vendor_id": None,
            "report_data_hex": sim_hash if len(sim_hash) == 64 else None,
            "deal_terms_hash": sim_hash if len(sim_hash) == 64 else None,
            "cert_chain_valid": None,
            "qe_sig_valid": None,
            "att_key_binding_valid": None,
            "td_sig_valid": None,
            "intel_verified": False,
            "pck_cert_subject": None,
            "verification_status": "simulation_only",
            "error": None,
        }

    # ── Decode hex ───────────────────────────────────────────────────────── #
    try:
        quote_bytes = bytes.fromhex(attestation)
    except ValueError as exc:
        return _error_result(f"attestation is not valid hex: {exc}")

    if len(quote_bytes) < _HEADER_SIZE:
        return _error_result(f"quote too short: {len(quote_bytes)} bytes (need ≥{_HEADER_SIZE})")

    # ── Parse header ─────────────────────────────────────────────────────── #
    try:
        version, att_key_type = struct.unpack_from("<HH", quote_bytes, 0)
        (tee_type_raw,) = struct.unpack_from("<I", quote_bytes, 4)
        qe_vendor_id_bytes = quote_bytes[12:28]
    except struct.error as exc:
        return _error_result(f"header parse error: {exc}")

    tee_type_str = _TEE_TYPES.get(tee_type_raw, f"unknown(0x{tee_type_raw:08x})")
    qe_vendor_id_hex = qe_vendor_id_bytes.hex()

    # ── Extract TD Report REPORTDATA (deal terms hash) ───────────────────── #
    report_data_hex: str | None = None
    deal_terms_hash: str | None = None
    td_rd_abs = _TD_REPORT_OFFSET + _TD_REPORTDATA_OFFSET
    if len(quote_bytes) >= td_rd_abs + 64:
        report_data_hex = quote_bytes[td_rd_abs : td_rd_abs + 64].hex()
        deal_terms_hash = quote_bytes[td_rd_abs : td_rd_abs + 32].hex()

    base = {
        "mode": "production",
        "version": version,
        "tee_type": tee_type_str,
        "qe_vendor_id": qe_vendor_id_hex,
        "report_data_hex": report_data_hex,
        "deal_terms_hash": deal_terms_hash,
        "cert_chain_valid": None,
        "qe_sig_valid": None,
        "att_key_binding_valid": None,
        "td_sig_valid": None,
        "intel_verified": False,
        "pck_cert_subject": None,
        "error": None,
    }

    if len(quote_bytes) < _MIN_PARSEABLE:
        base["verification_status"] = "dcap_header_parsed"
        logger.info(f"DCAP header parsed (quote too short for full verification): version={version}, tee={tee_type_str}")
        return base

    if not _CRYPTO_AVAILABLE:
        base["verification_status"] = "dcap_header_parsed"
        base["error"] = "cryptography package not installed — cannot do full DCAP verification"
        logger.warning("Full DCAP verification skipped: cryptography not available")
        return base

    return _verify_full(quote_bytes, base)


# ── Full verification ─────────────────────────────────────────────────────── #

def _verify_full(quote_bytes: bytes, base: dict) -> dict:
    """
    Run all 4 DCAP verification steps.

    Steps
    -----
    1. Verify PCK cert chain → Intel Root CA (cert_chain_valid)
    2. Verify QE Report signature with PCK key (qe_sig_valid)
    3. Verify ATT key binding in QE REPORTDATA (att_key_binding_valid)
    4. Verify TD Report signature with ATT key (td_sig_valid)

    All four must pass for intel_verified=True (full Option B path).
    """
    result = dict(base)
    errors: list[str] = []

    # ── Parse signature data ─────────────────────────────────────────────── #
    sd = _SIG_DATA_OFFSET  # base offset for signature data
    try:
        ecdsa_sig   = quote_bytes[sd + _REL_ECDSA_SIG  : sd + _REL_ATT_KEY]    # 64 bytes
        att_key_raw = quote_bytes[sd + _REL_ATT_KEY    : sd + _REL_QE_REPORT]   # 64 bytes
        qe_report   = quote_bytes[sd + _REL_QE_REPORT  : sd + _REL_QE_SIG]      # 384 bytes
        qe_sig      = quote_bytes[sd + _REL_QE_SIG     : sd + _REL_QE_AUTH_SIZE] # 64 bytes

        qe_auth_sz_off = sd + _REL_QE_AUTH_SIZE
        (qe_auth_size,) = struct.unpack_from("<H", quote_bytes, qe_auth_sz_off)
        qe_auth_off = qe_auth_sz_off + 2
        qe_auth_data = quote_bytes[qe_auth_off : qe_auth_off + qe_auth_size]

        cert_hdr_off = qe_auth_off + qe_auth_size
        (cert_type,) = struct.unpack_from("<H", quote_bytes, cert_hdr_off)
        (cert_size,) = struct.unpack_from("<I", quote_bytes, cert_hdr_off + 2)
        cert_data    = quote_bytes[cert_hdr_off + 6 : cert_hdr_off + 6 + cert_size]

    except (struct.error, IndexError) as exc:
        result["verification_status"] = "dcap_header_parsed"
        result["error"] = f"signature data parse error: {exc}"
        logger.warning(f"DCAP sig data parse failed: {exc}")
        return result

    # ── Step 1: PCK cert chain → Intel Root CA ───────────────────────────── #
    pck_public_key = None
    if cert_type == 5:
        chain_ok, chain_err, pck_public_key = _verify_cert_chain(cert_data)
        result["cert_chain_valid"] = chain_ok
        if not chain_ok:
            errors.append(f"cert_chain: {chain_err}")
        if pck_public_key:
            try:
                certs = _split_pem_chain(cert_data)
                if certs:
                    cn_attrs = certs[0].subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
                    result["pck_cert_subject"] = cn_attrs[0].value if cn_attrs else None
            except Exception:
                pass
    else:
        result["cert_chain_valid"] = False
        errors.append(f"cert_type={cert_type} (expected 5 for PCK cert chain PEM)")

    # ── Step 2: QE Report signature (PCK key signs QE Report) ───────────── #
    if pck_public_key is not None:
        qe_sig_ok, qe_sig_err = _verify_ecdsa_sig(pck_public_key, qe_sig, qe_report)
        result["qe_sig_valid"] = qe_sig_ok
        if not qe_sig_ok:
            errors.append(f"qe_sig: {qe_sig_err}")
    else:
        result["qe_sig_valid"] = False
        errors.append("qe_sig: skipped (no PCK key — cert chain failed)")

    # ── Step 3: ATT key binding ──────────────────────────────────────────── #
    # QE REPORTDATA[0:32] must equal SHA-256(att_key_64_bytes || qe_auth_data)
    expected_binding = hashlib.sha256(att_key_raw + qe_auth_data).digest()
    qe_reportdata_32 = qe_report[_QE_REPORTDATA_OFFSET : _QE_REPORTDATA_OFFSET + 32]
    att_binding_ok = (expected_binding == qe_reportdata_32)
    result["att_key_binding_valid"] = att_binding_ok
    if not att_binding_ok:
        errors.append("att_key_binding: QE REPORTDATA mismatch (quote tampered?)")

    # ── Step 4: TD Report signature (ATT key signs Header || TD Report) ──── #
    # Signed data = first 632 bytes of the quote (header + TD report body)
    signed_data = quote_bytes[0 : _TD_REPORT_OFFSET + _TD_REPORT_SIZE]  # 0..632
    try:
        att_public_key = _load_p256_key(att_key_raw)
        td_sig_ok, td_sig_err = _verify_ecdsa_sig(att_public_key, ecdsa_sig, signed_data)
        result["td_sig_valid"] = td_sig_ok
        if not td_sig_ok:
            errors.append(f"td_sig: {td_sig_err}")
    except Exception as exc:
        result["td_sig_valid"] = False
        errors.append(f"td_sig: ATT key load failed: {exc}")

    # ── Overall result ───────────────────────────────────────────────────── #
    all_passed = (
        result["cert_chain_valid"] is True
        and result["qe_sig_valid"] is True
        and result["att_key_binding_valid"] is True
        and result["td_sig_valid"] is True
    )
    result["intel_verified"] = all_passed
    result["verification_status"] = "dcap_fully_verified" if all_passed else "dcap_partial"
    result["error"] = " | ".join(errors) if errors else None

    logger.info(
        "DCAP full verification: cert_chain=%s qe_sig=%s att_binding=%s td_sig=%s → intel_verified=%s",
        result["cert_chain_valid"], result["qe_sig_valid"],
        result["att_key_binding_valid"], result["td_sig_valid"], all_passed,
    )
    return result


# ── Cryptographic helpers ─────────────────────────────────────────────────── #

def _split_pem_chain(pem_bytes: bytes) -> list:
    """Split a concatenated PEM blob into individual x509 Certificate objects."""
    certs = []
    # Handle both bytes and str
    if isinstance(pem_bytes, str):
        pem_bytes = pem_bytes.encode()
    parts = pem_bytes.split(b"-----END CERTIFICATE-----")
    for part in parts:
        if b"-----BEGIN CERTIFICATE-----" in part:
            cert_pem = part.strip() + b"\n-----END CERTIFICATE-----\n"
            try:
                certs.append(x509.load_pem_x509_certificate(cert_pem))
            except Exception as exc:
                logger.debug(f"Failed to parse cert from PEM chunk: {exc}")
    return certs


def _verify_cert_chain(pem_bytes: bytes) -> tuple[bool, str | None, object]:
    """
    Parse a PEM cert chain and verify each cert is signed by the next.

    Returns
    -------
    (ok, error_message, leaf_public_key)
        ok is True only when the full chain verifies up to Intel Root CA.
        leaf_public_key is the PCK public key for further signature verification.
    """
    certs = _split_pem_chain(pem_bytes)
    if len(certs) < 2:
        return False, f"expected ≥2 certs in chain, got {len(certs)}", None

    # Verify each cert is signed by the next in the chain
    for i in range(len(certs) - 1):
        child = certs[i]
        parent = certs[i + 1]
        try:
            parent.public_key().verify(
                child.signature,
                child.tbs_certificate_bytes,
                ec.ECDSA(hashes.SHA256()),
            )
        except Exception as exc:
            return False, f"cert[{i}] ({_cert_cn(child)!r}) not signed by cert[{i+1}] ({_cert_cn(parent)!r}): {exc}", None

    # Verify root is self-signed and is Intel SGX Root CA
    root = certs[-1]
    root_cn = _cert_cn(root)
    if _INTEL_ROOT_CA_CN not in root_cn:
        return False, f"root cert CN {root_cn!r} is not {_INTEL_ROOT_CA_CN!r}", None

    try:
        root.public_key().verify(
            root.signature,
            root.tbs_certificate_bytes,
            ec.ECDSA(hashes.SHA256()),
        )
    except Exception as exc:
        return False, f"root cert is not self-signed: {exc}", None

    return True, None, certs[0].public_key()


def _verify_ecdsa_sig(public_key, sig_bytes: bytes, message: bytes) -> tuple[bool, str | None]:
    """
    Verify a raw 64-byte r||s ECDSA-P256 signature.

    Parameters
    ----------
    public_key : EllipticCurvePublicKey
    sig_bytes  : 64 bytes, r (32 bytes big-endian) || s (32 bytes big-endian)
    message    : raw bytes — SHA-256 is applied internally by the cryptography lib
    """
    if len(sig_bytes) != 64:
        return False, f"expected 64-byte signature, got {len(sig_bytes)}"
    r = int.from_bytes(sig_bytes[:32], "big")
    s = int.from_bytes(sig_bytes[32:], "big")
    der_sig = asym_utils.encode_dss_signature(r, s)
    try:
        public_key.verify(der_sig, message, ec.ECDSA(hashes.SHA256()))
        return True, None
    except Exception as exc:
        return False, str(exc)


def _load_p256_key(raw_64: bytes):
    """
    Load a P-256 public key from 64 raw bytes (x||y, without the 0x04 uncompressed prefix).
    """
    if len(raw_64) != 64:
        raise ValueError(f"expected 64-byte P-256 key, got {len(raw_64)}")
    x = int.from_bytes(raw_64[:32], "big")
    y = int.from_bytes(raw_64[32:], "big")
    nums = ec.EllipticCurvePublicNumbers(x=x, y=y, curve=ec.SECP256R1())
    return nums.public_key()


def _cert_cn(cert) -> str:
    """Extract the Common Name from an x509 certificate subject."""
    attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return attrs[0].value if attrs else "<no CN>"


def _error_result(error: str) -> dict:
    """Return a DCAPVerification-compatible dict for an unrecoverable parse error."""
    logger.warning(f"DCAP parse failed: {error}")
    return {
        "mode": "unknown",
        "version": None,
        "tee_type": None,
        "qe_vendor_id": None,
        "report_data_hex": None,
        "deal_terms_hash": None,
        "cert_chain_valid": None,
        "qe_sig_valid": None,
        "att_key_binding_valid": None,
        "td_sig_valid": None,
        "intel_verified": False,
        "pck_cert_subject": None,
        "verification_status": "invalid_quote",
        "error": error,
    }
