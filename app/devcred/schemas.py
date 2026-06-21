"""
Dev credential Pydantic schemas — Phase 3.
"""
from pydantic import BaseModel, Field
from typing import Optional


class DevCredIngestRequest(BaseModel):
    credential_id: str
    developer_handle: str = ""
    mode: str = "direct"          # "direct" | "github"
    github_token: Optional[str] = None   # used in github mode, never stored
    repos: list[str] = []                # github mode: ["owner/repo"]
    commits: list[dict] = []             # direct mode: pre-built commit dicts


class DevCredEvaluateRequest(BaseModel):
    developer_handle: Optional[str] = None  # override if not set during ingest


class SeniorDevCredential(BaseModel):
    credential_type: str = "SeniorDevCredential"
    credential_id: str
    developer_handle: str          # GitHub username only — no email, no employer name
    repo_corpus_root: str          # Merkle root over commits
    commit_count: int
    years_active: float
    hard_seniority_signal: str     # from GitInspectorAgent — the floor
    seniority_level: str           # from GitEvaluatorAgent — >= hard_seniority_signal
    primary_languages: list[str]
    specializations: list[str]
    has_test_culture: bool
    qualitative_assessment: str
    confidence: str
    caveats: list[str]
    credential_hash: str
    tee_quote: Optional[str] = None
    tee_attested: bool
    issued_at: str
    # Deliberately omitted: employer names, repo names, file paths, raw diffs
