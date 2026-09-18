"""
SeniorDevCredential — Pydantic schema for the dev-credential vertical.

Privacy constraints (non-negotiable):
  - employer names: never present for a *verified* credential (direct_access,
    events_stream, local_git_upload) — see SelfReportedContext below for the one
    deliberate, clearly-labeled exception.
  - repo names: hashed into repo_corpus_root, not stored here
  - file paths: absent — only aggregate metrics
  - raw diffs: absent — only line counts
  - developer email / real name: absent — GitHub username only

Provenance (revoked-repo-access fallback — see app/devcred/routes.py module docstring
for the full three-route design):

  provenance_method is the single, authoritative field distinguishing how a credential's
  underlying signal was obtained. Deliberately NOT a single boolean — the earlier design
  conversation that scoped this fallback flagged "one boolean flag" as insufficient,
  since a caller (including DealProof's own negotiation flow) needs to tell apart four
  meaningfully different trust levels, not just verified/unverified:

    direct_access    — Route A: full commit history fetched live via the GitHub API.
                        The original, highest-fidelity signal (languages, diffs, test
                        culture all visible).
    events_stream     — Route B: GitHub's events timeline (GET /users/{username}/events)
                         used as a fallback when direct repo access was revoked but the
                         revocation is recent enough (GitHub's own retention window —
                         confirmed 2026-09 against current docs: up to 300 events, only
                         those created in the past 30 days) to still carry signal. No
                         source code, diffs, or file paths are ever visible via this
                         endpoint — only event type/repo/timestamp. Structurally capped
                         below "senior" (see git_inspector.EventsInspectionReport).
    local_git_upload  — Route C: the candidate uploaded derived metrics from a local
                         .git folder they still hold, cryptographically bound to a
                         GitHub-associated SSH (or GPG) key via a fresh signature (see
                         app/devcred/local_signature.py). No file paths are available
                         in this path either (client never sends them), so
                         has_test_culture and primary_languages are structurally empty
                         here too, same discipline as events_stream.
    self_reported     — The honest dead end: repo access was revoked, outside the
                         events-stream window, and no local .git copy exists. No
                         verifiable signal of any kind. The candidate may still supply
                         plain contextual claims (role title, company name, employment
                         dates) via `self_reported` below — but nothing here is
                         cryptographically or platform-attested, and `verified` is
                         always False for this method. This must never be visually or
                         semantically confused with a real verified credential.

  verified is a convenience boolean derived from provenance_method (True for the three
  Route A/B/C methods, False only for self_reported) — kept as an explicit field rather
  than requiring every consumer to know which enum values count as "verified", since
  that's exactly the kind of ambiguity a single ad-hoc boolean would otherwise create.
"""
from enum import Enum

from pydantic import BaseModel


class ProvenanceMethod(str, Enum):
    DIRECT_ACCESS = "direct_access"
    EVENTS_STREAM = "events_stream"
    LOCAL_GIT_UPLOAD = "local_git_upload"
    SELF_REPORTED = "self_reported"


class SelfReportedContext(BaseModel):
    """
    Present only when provenance_method == self_reported. This is the one place in
    this schema where an employer name is deliberately stored in the clear — the
    entire point of this path is an honest, explicitly-unverified claim, not a
    hashed/private credential. It must never be mistaken for the verified pipeline's
    privacy guarantees, which is why it lives in its own nested model rather than as
    loose fields on SeniorDevCredential itself.
    """
    role_title: str
    company_name: str
    employment_start: str          # ISO-8601 date, self-reported
    employment_end: str | None = None  # None = still employed there per the candidate


class SeniorDevCredential(BaseModel):
    credential_type: str = "SeniorDevCredential"
    credential_id: str
    developer_handle: str          # GitHub username only — no email, no real name

    provenance_method: ProvenanceMethod = ProvenanceMethod.DIRECT_ACCESS
    verified: bool = True          # False only when provenance_method == self_reported

    # Populated for direct_access, events_stream, and local_git_upload. None/0 for
    # self_reported — there is no git evidence to hash or count in that case.
    repo_corpus_root: str | None = None   # Merkle root; content depends on provenance_method
                                            # (commits for direct_access/local_git_upload,
                                            # events for events_stream) — see routes.py.
    commit_count: int = 0
    event_count: int | None = None         # populated only for events_stream
    years_active: float = 0.0
    hard_seniority_signal: str | None = None   # from GitInspectorAgent / inspect_events — authoritative floor
    seniority_level: str = "junior"            # from GitEvaluatorAgent (direct_access/local_git_upload only)
                                                 # — always >= hard_seniority_signal where both exist
    primary_languages: list[str] = []
    specializations: list[str] = []
    has_test_culture: bool = False
    qualitative_assessment: str = ""
    confidence: str = "low"        # "low" | "medium" | "high"
    caveats: list[str] = []

    self_reported: SelfReportedContext | None = None  # populated only for self_reported

    credential_hash: str           # SHA-256 of all above fields — embedded in TDX report_data
    issued_at: str                 # ISO-8601 UTC
    tee_attested: bool             # attests that THIS RECORD was processed inside the TEE —
                                     # for self_reported, this does NOT mean the underlying
                                     # employment claim was verified, only that the honestly-
                                     # labeled unverified record itself was signed as such.


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


# ---------------------------------------------------------------------------
# Route C (local_git_upload) request schema
# ---------------------------------------------------------------------------

class LocalGitCommitEnvelope(BaseModel):
    """
    Same shape as the canonical commit dict git_hasher.hash_commit() hashes for
    Route A — deliberately missing `files`: no file paths ever leave the client
    for this route. diff_stat may be null (the reference frontend implementation
    does not attempt in-browser tree diffing — see LocalGitUpload.jsx).
    """
    sha: str
    author: str | None = None
    timestamp: str | None = None
    message: str = ""
    diff_stat: dict | None = None


class LocalGitUploadRequest(BaseModel):
    credential_id: str
    developer_handle: str
    commits: list[LocalGitCommitEnvelope]
    signature: str          # armored SSH or GPG detached signature over the canonical payload
    signature_format: str   # "ssh" | "gpg"
    public_key: str         # OpenSSH "ssh-ed25519 AAAA..." line, or armored GPG public key


class LocalGitUploadResponse(BaseModel):
    credential_id: str
    corpus_root: str
    commit_count: int
    key_fingerprint: str | None = None
    github_key_currently_listed: bool | None = None  # best-effort cross-check against
                                                        # GET /users/{handle}/keys — None
                                                        # if that lookup itself failed


# ---------------------------------------------------------------------------
# Route D (self_reported) request schema
# ---------------------------------------------------------------------------

class SelfReportedRequest(BaseModel):
    credential_id: str
    developer_handle: str | None = None
    role_title: str
    company_name: str
    employment_start: str
    employment_end: str | None = None
