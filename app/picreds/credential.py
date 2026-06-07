"""
πCreds credential construction and hashing.

make_credential() builds a structured credential dict.
hash_credential() produces SHA-256 of a single credential.
hash_credentials() produces a combined SHA-256 over all credentials in a deal —
this combined hash is what gets embedded in the TDX report_data.

Credential types:
  "policy"  — certifies what rules an agent is bound by (from system prompt)
  "conduct" — certifies both agents complied with constraints (from transcript)

The code_hash field in a policy credential is SHA-256 of the system prompt,
allowing future verifiers to confirm a given prompt produces a given hash
without the prompt being revealed.
"""
import json
import hashlib
import time


def make_credential(
    credential_type: str,
    subject: str,
    audit_result: dict,
    deal_id: str,
    code_hash: str,
) -> dict:
    return {
        "type": "DealProofCredential",
        "credential_type": credential_type,
        "subject": subject,
        "deal_id": deal_id,
        "code_hash": code_hash,
        "audit_result": audit_result,
        "issued_at": int(time.time()),
    }


def hash_credential(credential: dict) -> str:
    return hashlib.sha256(
        json.dumps(credential, sort_keys=True).encode()
    ).hexdigest()


def hash_credentials(credentials: list[dict]) -> str:
    individual = sorted(hash_credential(c) for c in credentials)
    return hashlib.sha256(json.dumps(individual).encode()).hexdigest()
