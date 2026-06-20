"""
SeniorDevCredential — Pydantic schema for the dev-credential vertical.

Privacy constraints (non-negotiable):
  - employer names: never present
  - repo names: hashed into repo_corpus_root, not stored here
  - file paths: absent — only aggregate metrics
  - raw diffs: absent — only line counts
  - developer email / real name: absent — GitHub username only
"""
from pydantic import BaseModel


class SeniorDevCredential(BaseModel):
    credential_type: str = "SeniorDevCredential"
    credential_id: str
    developer_handle: str         # GitHub username only — no email, no real name
    repo_corpus_root: str         # Merkle root of the commit corpus
    commit_count: int
    years_active: float
    hard_seniority_signal: str    # from GitInspectorAgent — authoritative floor
    seniority_level: str          # from GitEvaluatorAgent — always >= hard_seniority_signal
    primary_languages: list[str]
    specializations: list[str]
    has_test_culture: bool
    qualitative_assessment: str
    confidence: str               # "low" | "medium" | "high"
    caveats: list[str]
    credential_hash: str          # SHA-256 of all above fields — embedded in TDX report_data
    issued_at: str                # ISO-8601 UTC
    tee_attested: bool


class DevCredEvaluateResponse(BaseModel):
    credential_id: str
    credential: SeniorDevCredential
    tee_quote: str
    tee_attested: bool


class DevCredStatusResponse(BaseModel):
    credential_id: str
    status: str
    credential: SeniorDevCredential | None = None
    tee_quote: str | None = None
