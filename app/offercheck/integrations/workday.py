"""
Workday integration — Phase 3 stretch goal (see build_spec_offer_check.md,
which itself marks Workday "(stretch)").

Deliberately a stub. Workday integrations are tenant-specific SOAP/REST
setups (WSDL endpoints, OAuth client credentials scoped per customer instance)
with no generic public endpoint to point at — unlike Greenhouse/Lever there
is no single "the API" to write against without a specific customer's tenant
details. notify_outcome() always raises WorkdayNotConfigured; this is
intentional, not a placeholder that was forgotten.
"""
from app.offercheck.integrations._shared import AtsNotConfigured, verify_hmac_signature


class WorkdayNotConfigured(AtsNotConfigured):
    pass


def verify_signature(raw_body: bytes, signature_header_value: str, webhook_secret: str) -> bool:
    return verify_hmac_signature(raw_body, signature_header_value, webhook_secret)


async def notify_outcome(ats_api_key: str, ats_candidate_ref: str, summary: str) -> str:
    raise WorkdayNotConfigured(
        "Workday integration is a stretch goal with no generic endpoint — "
        "requires tenant-specific WSDL/OAuth setup not implemented here"
    )
