"""
SOC 2 Pydantic schemas — product/continuous-soc2.

ControlFinding and SOC2ControlCredential mirror the W3C VC structure
used by the existing DealProofCredential in app/api/schemas.py.
"""
from pydantic import BaseModel


class ControlFinding(BaseModel):
    control_id: str
    hard_finding: bool
    evidence_snippets: list[str]
    effective: bool
    qualitative_assessment: str
    risk_notes: str


class SOC2ControlCredential(BaseModel):
    credential_type: str = "SOC2ControlCredential"
    audit_id: str
    org_name: str
    corpus_root: str
    controls_assessed: list[str]
    control_findings: list[ControlFinding]
    overall_assessment: str
    material_weaknesses: list[str]
    significant_deficiencies: list[str]
    all_controls_effective: bool
    credential_hash: str
    issued_at: str
    tee_attested: bool
