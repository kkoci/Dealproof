"""
Greenhouse ATS integration — Phase 3 (see build_spec_offer_check.md).

Outbound only: once a verification session closes, post the outcome (state,
round count, genuine_negotiation — never a raw dollar figure) as a candidate
activity-feed note via Greenhouse's Harvest API, so a recruiter sees
"Offer Check verified — 3 rounds, no conduct issues" directly on the
candidate's profile without leaving Greenhouse.

Inbound signature verification is also provided (`verify_signature`) for a
webhook receiver / connection-test ping — see app.offercheck.routes.

Caveat: the Harvest API request shape below (Basic auth with the API key as
username, POST to /v1/candidates/{id}/activity_feed/notes) matches
Greenhouse's documented API as of this writing but has not been exercised
against a live Greenhouse account in this environment — confirm against
current Greenhouse docs before relying on it in production.
"""
import httpx

from app.offercheck.integrations._shared import AtsNotConfigured, verify_hmac_signature

_HARVEST_API_BASE = "https://harvest.greenhouse.io/v1"


class GreenhouseNotConfigured(AtsNotConfigured):
    pass


def verify_signature(raw_body: bytes, signature_header_value: str, webhook_secret: str) -> bool:
    return verify_hmac_signature(raw_body, signature_header_value, webhook_secret)


async def notify_outcome(ats_api_key: str, ats_candidate_ref: str, summary: str) -> str:
    """
    Post a one-line note to the candidate's Greenhouse activity feed.

    ats_api_key: the company's Greenhouse Harvest API key (stored on Company, never logged)
    ats_candidate_ref: Greenhouse candidate id the note should attach to
    summary: OfferVerifiedCredential.summary — already scrubbed of raw numbers
    """
    if not ats_api_key:
        raise GreenhouseNotConfigured("no Greenhouse API key connected for this company")

    async with httpx.AsyncClient(base_url=_HARVEST_API_BASE, auth=(ats_api_key, "")) as client:
        response = await client.post(
            f"/candidates/{ats_candidate_ref}/activity_feed/notes",
            json={"body": f"Offer Check: {summary}", "visibility": "admin_only"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["id"]
