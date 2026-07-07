"""
Lever ATS integration — Phase 3 (see build_spec_offer_check.md).

Outbound only, mirrors greenhouse.py: post the closed session's outcome as a
note on the Lever opportunity, no raw dollar figures.

Caveat: the request shape below (Bearer auth, POST to
/v1/opportunities/{id}/notes) matches Lever's documented REST API as of this
writing but has not been exercised against a live Lever account in this
environment — confirm against current Lever docs before relying on it in
production.
"""
import httpx

from app.offercheck.integrations._shared import AtsNotConfigured, verify_hmac_signature

_LEVER_API_BASE = "https://api.lever.co/v1"


class LeverNotConfigured(AtsNotConfigured):
    pass


def verify_signature(raw_body: bytes, signature_header_value: str, webhook_secret: str) -> bool:
    return verify_hmac_signature(raw_body, signature_header_value, webhook_secret)


async def notify_outcome(ats_api_key: str, ats_candidate_ref: str, summary: str) -> str:
    """
    ats_api_key: the company's Lever API token (Bearer), never logged
    ats_candidate_ref: Lever opportunity id the note should attach to
    summary: OfferVerifiedCredential.summary — already scrubbed of raw numbers
    """
    if not ats_api_key:
        raise LeverNotConfigured("no Lever API token connected for this company")

    async with httpx.AsyncClient(base_url=_LEVER_API_BASE, headers={"Authorization": f"Bearer {ats_api_key}"}) as client:
        response = await client.post(
            f"/opportunities/{ats_candidate_ref}/notes",
            json={"value": f"Offer Check: {summary}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["data"]["id"]
