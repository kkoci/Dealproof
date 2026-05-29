"""
Unit tests for app.dkim.verifier.

All httpx and dkimpy calls are mocked so tests pass without network access
or a real DKIM-signed email.
"""
import base64
import sys
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_eml(domain: str = "example.com", selector: str = "s1") -> bytes:
    """Minimal RFC-2822 email with a well-formed DKIM-Signature header."""
    return (
        f"DKIM-Signature: v=1; a=rsa-sha256; d={domain}; s={selector}; "
        f"h=from:to:subject; bh=abc123==; b=fakesig==\r\n"
        f"From: seller@{domain}\r\n"
        f"To: buyer@other.com\r\n"
        f"Subject: Deal\r\n"
        f"\r\nEmail body.\r\n"
    ).encode()


def _b64(eml: bytes) -> str:
    return base64.b64encode(eml).decode()


def _mock_httpx_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status.side_effect = HTTPStatusError(
            "error", request=MagicMock(), response=MagicMock()
        )
    return resp


# ---------------------------------------------------------------------------
# _doh_get_txt
# ---------------------------------------------------------------------------

def test_doh_get_txt_single_part_record():
    """Single-quoted TXT record is returned as one _TXTRecord with one string."""
    from app.dkim.verifier import _doh_get_txt

    payload = {
        "Answer": [{"type": 16, "data": '"v=DKIM1; k=rsa; p=ABCDEF"'}]
    }
    with patch("app.dkim.verifier.httpx.get", return_value=_mock_httpx_response(payload)):
        records = _doh_get_txt(b"s1._domainkey.example.com")

    assert len(records) == 1
    assert records[0].strings == [b"v=DKIM1; k=rsa; p=ABCDEF"]


def test_doh_get_txt_multi_part_record():
    """Multi-quoted TXT record (long key split across strings) is parsed correctly."""
    from app.dkim.verifier import _doh_get_txt

    payload = {
        "Answer": [{"type": 16, "data": '"v=DKIM1; k=rsa; p=AAAA" "BBBBCCCC"'}]
    }
    with patch("app.dkim.verifier.httpx.get", return_value=_mock_httpx_response(payload)):
        records = _doh_get_txt(b"s1._domainkey.example.com")

    assert len(records) == 1
    assert records[0].strings == [b"v=DKIM1; k=rsa; p=AAAA", b"BBBBCCCC"]


def test_doh_get_txt_filters_non_txt_types():
    """Records with type != 16 are silently ignored."""
    from app.dkim.verifier import _doh_get_txt

    payload = {
        "Answer": [
            {"type": 1, "data": "93.184.216.34"},   # A record
            {"type": 16, "data": '"v=DKIM1; k=rsa; p=XYZ"'},
        ]
    }
    with patch("app.dkim.verifier.httpx.get", return_value=_mock_httpx_response(payload)):
        records = _doh_get_txt(b"s1._domainkey.example.com")

    assert len(records) == 1
    assert records[0].strings == [b"v=DKIM1; k=rsa; p=XYZ"]


def test_doh_get_txt_empty_answer_returns_empty_list():
    """No Answer section → empty list (dkimpy will raise KeyFormatError downstream)."""
    from app.dkim.verifier import _doh_get_txt

    with patch("app.dkim.verifier.httpx.get", return_value=_mock_httpx_response({"Answer": []})):
        records = _doh_get_txt(b"missing._domainkey.example.com")

    assert records == []


def test_doh_get_txt_fallback_unquoted_data():
    """If data has no quoted segments, the whole value becomes one string."""
    from app.dkim.verifier import _doh_get_txt

    payload = {"Answer": [{"type": 16, "data": "v=DKIM1; k=rsa; p=NOQ"}]}
    with patch("app.dkim.verifier.httpx.get", return_value=_mock_httpx_response(payload)):
        records = _doh_get_txt(b"s1._domainkey.example.com")

    assert len(records) == 1
    assert records[0].strings == [b"v=DKIM1; k=rsa; p=NOQ"]


def test_doh_get_txt_accepts_str_name():
    """_doh_get_txt accepts a plain str as well as bytes for the name."""
    from app.dkim.verifier import _doh_get_txt

    payload = {"Answer": [{"type": 16, "data": '"v=DKIM1; p=ABC"'}]}
    mock_get = MagicMock(return_value=_mock_httpx_response(payload))
    with patch("app.dkim.verifier.httpx.get", mock_get):
        records = _doh_get_txt("s1._domainkey.example.com")

    assert len(records) == 1
    # Verify the correct hostname was passed to httpx.get
    call_params = mock_get.call_args[1]["params"]
    assert call_params["name"] == "s1._domainkey.example.com"


def test_doh_get_txt_network_error_raises_os_error():
    """A network exception from httpx is wrapped in OSError."""
    from app.dkim.verifier import _doh_get_txt
    import httpx

    with patch("app.dkim.verifier.httpx.get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(OSError, match="DoH lookup failed"):
            _doh_get_txt(b"s1._domainkey.example.com")


def test_doh_get_txt_http_error_raises_os_error():
    """An HTTP error status from the DoH endpoint is wrapped in OSError."""
    from app.dkim.verifier import _doh_get_txt

    with patch("app.dkim.verifier.httpx.get", return_value=_mock_httpx_response({}, status_code=503)):
        with pytest.raises(OSError, match="DoH lookup failed"):
            _doh_get_txt(b"s1._domainkey.example.com")


# ---------------------------------------------------------------------------
# verify_email_proof — input validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_invalid_base64():
    """Non-base64 input returns error without touching DNS or dkimpy."""
    from app.dkim.verifier import verify_email_proof

    result = await verify_email_proof("not-valid-base64!!!")

    assert result.verified is False
    assert result.domain is None
    assert "base64 decode" in result.error


@pytest.mark.asyncio
async def test_verify_no_dkim_signature_header():
    """Email without a DKIM-Signature header returns a clear error."""
    from app.dkim.verifier import verify_email_proof

    eml = b"From: a@b.com\r\nTo: c@d.com\r\nSubject: Hi\r\n\r\nBody"
    result = await verify_email_proof(_b64(eml))

    assert result.verified is False
    assert result.domain is None
    assert "No DKIM-Signature" in result.error


@pytest.mark.asyncio
async def test_verify_dkim_header_missing_d_tag():
    """DKIM-Signature header without d= tag returns a clear error."""
    from app.dkim.verifier import verify_email_proof

    eml = b"DKIM-Signature: v=1; a=rsa-sha256; s=sel\r\nFrom: a@b.com\r\n\r\nBody"
    result = await verify_email_proof(_b64(eml))

    assert result.verified is False
    assert result.domain is None
    assert "d= domain tag" in result.error


# ---------------------------------------------------------------------------
# verify_email_proof — dkimpy interaction
# ---------------------------------------------------------------------------

def _make_mock_dkim_module(verify_return: bool = True, side_effect=None):
    """Build a mock dkim module whose DKIM().verify() behaves as specified."""
    mock_dkim_instance = MagicMock()
    if side_effect:
        mock_dkim_instance.verify.side_effect = side_effect
    else:
        mock_dkim_instance.verify.return_value = verify_return

    mock_dkim_mod = MagicMock()
    mock_dkim_mod.DKIM.return_value = mock_dkim_instance
    mock_dkim_mod.ValidationError = Exception
    return mock_dkim_mod


@pytest.mark.asyncio
async def test_verify_happy_path():
    """Valid DKIM signature returns verified=True with the correct domain."""
    from app.dkim.verifier import verify_email_proof

    eml = _make_eml(domain="company.com")
    mock_dkim = _make_mock_dkim_module(verify_return=True)

    with patch.dict(sys.modules, {"dkim": mock_dkim}):
        result = await verify_email_proof(_b64(eml))

    assert result.verified is True
    assert result.domain == "company.com"
    assert result.error is None
    assert result.dns_unavailable is False


@pytest.mark.asyncio
async def test_verify_injects_doh_resolver():
    """verify_email_proof sets d.dnsfunc to _doh_get_txt before calling verify()."""
    from app.dkim.verifier import verify_email_proof, _doh_get_txt

    eml = _make_eml()
    mock_dkim_instance = MagicMock()
    mock_dkim_instance.verify.return_value = True
    mock_dkim_mod = MagicMock()
    mock_dkim_mod.DKIM.return_value = mock_dkim_instance
    mock_dkim_mod.ValidationError = Exception

    with patch.dict(sys.modules, {"dkim": mock_dkim_mod}):
        await verify_email_proof(_b64(eml))

    assert mock_dkim_instance.dnsfunc is _doh_get_txt


@pytest.mark.asyncio
async def test_verify_signature_mismatch():
    """dkimpy returning False → verified=False with signature-mismatch error."""
    from app.dkim.verifier import verify_email_proof

    eml = _make_eml()
    mock_dkim = _make_mock_dkim_module(verify_return=False)

    with patch.dict(sys.modules, {"dkim": mock_dkim}):
        result = await verify_email_proof(_b64(eml))

    assert result.verified is False
    assert result.domain == "example.com"
    assert "signature mismatch" in result.error


@pytest.mark.asyncio
async def test_verify_validation_error():
    """dkim.ValidationError is caught and surfaced as verified=False."""
    from app.dkim.verifier import verify_email_proof

    eml = _make_eml()

    class FakeValidationError(Exception):
        pass

    mock_dkim_instance = MagicMock()
    mock_dkim_instance.verify.side_effect = FakeValidationError("bad key format")
    mock_dkim_mod = MagicMock()
    mock_dkim_mod.DKIM.return_value = mock_dkim_instance
    mock_dkim_mod.ValidationError = FakeValidationError

    with patch.dict(sys.modules, {"dkim": mock_dkim_mod}):
        result = await verify_email_proof(_b64(eml))

    assert result.verified is False
    assert result.domain == "example.com"
    assert "bad key format" in result.error


@pytest.mark.asyncio
async def test_verify_generic_exception_from_dkimpy():
    """Any unexpected exception from dkimpy is caught and returned as an error."""
    from app.dkim.verifier import verify_email_proof

    eml = _make_eml()
    mock_dkim = _make_mock_dkim_module(side_effect=RuntimeError("unexpected"))

    with patch.dict(sys.modules, {"dkim": mock_dkim}):
        result = await verify_email_proof(_b64(eml))

    assert result.verified is False
    assert result.domain == "example.com"
    assert "unexpected" in result.error


@pytest.mark.asyncio
async def test_verify_dkimpy_not_installed():
    """ImportError for dkimpy still returns domain with a clear not-installed message."""
    from app.dkim.verifier import verify_email_proof

    eml = _make_eml(domain="corp.io")

    # Setting sys.modules['dkim'] = None causes `import dkim` to raise ImportError
    # without touching builtins.__import__ (which triggers recursion in Py 3.14+).
    with patch.dict(sys.modules, {"dkim": None}):
        result = await verify_email_proof(_b64(eml))

    assert result.verified is False
    assert result.domain == "corp.io"
    assert "not installed" in result.error


@pytest.mark.asyncio
async def test_verify_domain_lowercased_and_stripped():
    """Domain extracted from d= tag is lowercased and trailing dots removed."""
    from app.dkim.verifier import verify_email_proof

    eml = (
        b"DKIM-Signature: v=1; a=rsa-sha256; d=UPPER.Example.COM.; s=s1; "
        b"h=from; bh=x; b=y\r\nFrom: a@UPPER.Example.COM\r\n\r\nBody"
    )
    mock_dkim = _make_mock_dkim_module(verify_return=True)

    with patch.dict(sys.modules, {"dkim": mock_dkim}):
        result = await verify_email_proof(_b64(eml))

    assert result.domain == "upper.example.com"
