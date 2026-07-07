"""
Offer-letter PDF parsing — Phase 2 (see build_spec_offer_check.md).

Extracts text from an uploaded PDF via pypdf, then asks Claude to pull out
structured compensation fields. This is a convenience prefill only — the
candidate reviews and can correct every field before POST /sessions is ever
called, so a bad extraction never silently becomes the record of truth.
Never persisted; the PDF bytes and extracted text live only for the duration
of this request.
"""
import io
import json
import logging

import anthropic
from pypdf import PdfReader

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_CHARS_TO_MODEL = 8000

_EXTRACTION_SYSTEM_PROMPT = """You extract structured compensation data from job offer letters.
You will be given raw text extracted from a PDF offer letter. Pull out the fields below.
If a field is not present, use 0 for numbers or "" for strings — do not guess wildly.
Equity should be an annualized dollar estimate if the letter gives enough information to compute
one (e.g. total grant / vesting years); otherwise 0.

Always respond with valid JSON only, no extra text:
{
  "company": "<string>",
  "role": "<string>",
  "base_salary": <number>,
  "equity_value": <number, annualized estimate, 0 if not determinable>,
  "bonus": <number, 0 if none stated>,
  "start_date": "<ISO-8601 date e.g. 2026-09-01, best explicit date in the letter, "" if absent>,
  "confidence": "<high|medium|low>",
  "notes": [<string>, ...]
}

confidence guide:
- high: all core fields (company, role, base_salary) explicitly stated and unambiguous
- medium: core fields present but some (equity, bonus, start_date) required light inference
- low: any core field missing or the document doesn't look like an offer letter
"""


class OfferLetterParseError(Exception):
    """Raised for any parsing failure — routes.py maps this to HTTP 422."""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise OfferLetterParseError(f"could not read PDF: {exc}") from exc

    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    if not text.strip():
        raise OfferLetterParseError("no extractable text found in PDF (scanned image?)")
    return text


async def extract_offer_from_text(text: str) -> dict:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=_EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text[:_MAX_CHARS_TO_MODEL]}],
        )
        raw = response.content[0].text.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            data, _ = json.JSONDecoder().raw_decode(raw, start)
            return data
    except Exception as exc:
        logger.warning(f"offer letter extraction failed — {exc}")
        raise OfferLetterParseError(f"extraction failed: {exc}") from exc


async def parse_offer_letter(pdf_bytes: bytes) -> dict:
    text = extract_text_from_pdf(pdf_bytes)
    return await extract_offer_from_text(text)
