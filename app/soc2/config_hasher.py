"""
SOC 2 config corpus hasher — product/continuous-soc2.

Hashing pipeline for uploaded cloud infrastructure config files:
  config_file → hash_config_file()          → 64-char hex
  hashes      → compute_config_corpus_root() → 64-char hex (Merkle root)

Algorithm mirrors app/props/transcript_hasher.py exactly:
  root = SHA-256( len(configs).to_bytes(4, 'big') + concat(bytes(hash_i)) )

The corpus root identifies a unique snapshot of a customer's config evidence
and is embedded in the TDX report_data of the SOC2ControlCredential.

extract_control_evidence() is deterministic — no LLM, no I/O.
It returns {control_id: [evidence_snippets]} for each CC6/CC7 control.
"""
import hashlib
import json


# ── Hashing ──────────────────────────────────────────────────────────────────

def hash_config_file(config: dict) -> str:
    """
    SHA-256 of canonical JSON of one config entry.
    config must have: source (str), format (str), content (dict).
    sort_keys=True ensures determinism regardless of dict insertion order.
    """
    canonical = {
        "content": config["content"],
        "format": config["format"],
        "source": config["source"],
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()


def compute_config_corpus_root(configs: list[dict]) -> str:
    """
    Length-prefixed Merkle root over per-file config hashes.
    Same algorithm as app/props/transcript_hasher.py compute_corpus_root —
    which is identical to app/props/verifier.py compute_merkle_root.

    Algorithm:
      root = SHA-256( len(configs).to_bytes(4, 'big')
                    + bytes(hash_0) + bytes(hash_1) + ... )
    """
    if not configs:
        raise ValueError("compute_config_corpus_root requires at least one config")
    file_hashes = [hash_config_file(c) for c in configs]
    length_prefix = len(file_hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h) for h in file_hashes)
    return hashlib.sha256(raw).hexdigest()


# ── Evidence extraction helpers ───────────────────────────────────────────────

def _iter_statements(content: dict | list) -> list[dict]:
    """Flatten IAM policy content into a list of Statement dicts."""
    if isinstance(content, list):
        stmts = []
        for item in content:
            stmts.extend(_iter_statements(item))
        return stmts

    # AWS ListPolicies / GetPolicy response shape
    if "Policies" in content:
        return _iter_statements(content["Policies"])
    if "Policy" in content and isinstance(content["Policy"], dict):
        return _iter_statements(content["Policy"])

    # Inline policy document
    if "PolicyDocument" in content:
        doc = content["PolicyDocument"]
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except Exception:
                return []
        return _iter_statements(doc)

    # Raw policy document with Statement key
    if "Statement" in content:
        stmts = content["Statement"]
        if isinstance(stmts, dict):
            return [stmts]
        return [s for s in stmts if isinstance(s, dict)]

    return []


def _extract_mfa_evidence(content: dict | list) -> list[str]:
    """CC6.1 — find (or absence of) MFA enforcement conditions in IAM policies."""
    snippets = []
    stmts = _iter_statements(content)
    for stmt in stmts:
        effect = stmt.get("Effect", "Allow")
        cond = stmt.get("Condition", {})
        bool_cond = cond.get("Bool", {})
        null_cond = cond.get("Null", {})

        for key, val in bool_cond.items():
            if "multifactorauthpresent" in key.lower():
                snippets.append(
                    f"Statement Effect={effect}: {key}={val}"
                )
        for key, val in null_cond.items():
            if "multifactorauthpresent" in key.lower():
                snippets.append(
                    f"Statement Effect={effect} Null condition: {key}={val}"
                )

    if not snippets:
        snippets.append("No MFA conditions found in IAM policies")
    return snippets


def _extract_wildcard_evidence(content: dict | list) -> list[str]:
    """CC6.2 — find wildcard Action or Resource in Allow statements."""
    snippets = []
    stmts = _iter_statements(content)
    for stmt in stmts:
        effect = stmt.get("Effect", "Allow")
        actions = stmt.get("Action", [])
        resources = stmt.get("Resource", [])
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]

        if "*" in actions:
            snippets.append(f"Statement Effect={effect}: Action=* (wildcard)")
        if "*" in resources:
            snippets.append(f"Statement Effect={effect}: Resource=* (wildcard)")

    if not snippets:
        snippets.append("No wildcard Action/* or Resource/* found in IAM policies")
    return snippets


def _extract_event_selector_evidence(content: dict) -> list[str]:
    """CC6.3 — CloudTrail event selectors indicate access logging scope."""
    snippets = []

    selectors = content.get("EventSelectors", [])
    advanced = content.get("AdvancedEventSelectors", [])

    if selectors:
        for sel in selectors:
            rw = sel.get("ReadWriteType", "All")
            mgmt = sel.get("IncludeManagementEvents", False)
            snippets.append(
                f"EventSelector: ReadWriteType={rw}, IncludeManagementEvents={mgmt}"
            )
    if advanced:
        snippets.append(f"AdvancedEventSelectors: {len(advanced)} selector(s) configured")

    if not snippets:
        snippets.append("No EventSelectors found in CloudTrail config")
    return snippets


def _extract_public_bucket_evidence(content: dict | list) -> list[str]:
    """CC6.6 — find public-access grants in bucket policies or ACLs."""
    snippets = []
    items = content if isinstance(content, list) else [content]

    for item in items:
        bucket_name = item.get("BucketName", item.get("Bucket", "unknown"))

        # Bucket policy string or dict
        policy_raw = item.get("Policy", item.get("BucketPolicy", None))
        if policy_raw:
            if isinstance(policy_raw, str):
                try:
                    policy_raw = json.loads(policy_raw)
                except Exception:
                    policy_raw = None
            if isinstance(policy_raw, dict):
                stmts = _iter_statements(policy_raw)
                for stmt in stmts:
                    principal = stmt.get("Principal", "")
                    effect = stmt.get("Effect", "Allow")
                    is_wildcard = (
                        principal == "*"
                        or (isinstance(principal, dict) and principal.get("AWS") == "*")
                    )
                    if is_wildcard and effect == "Allow":
                        snippets.append(
                            f"Bucket '{bucket_name}': Allow Principal=* (public access)"
                        )

        # Public access block settings
        pab = item.get("PublicAccessBlockConfiguration", {})
        if pab:
            blocked = all([
                pab.get("BlockPublicAcls", False),
                pab.get("IgnorePublicAcls", False),
                pab.get("BlockPublicPolicy", False),
                pab.get("RestrictPublicBuckets", False),
            ])
            snippets.append(
                f"Bucket '{bucket_name}': PublicAccessBlock={'fully enabled' if blocked else 'partially or not configured'}"
            )

    if not snippets:
        snippets.append("No bucket policy or public access configuration found")
    return snippets


def _extract_cloudtrail_active_evidence(content: dict) -> list[str]:
    """CC7.1 — check IsLogging and trail configuration."""
    snippets = []

    is_logging = content.get("IsLogging")
    if is_logging is not None:
        snippets.append(f"Trail IsLogging={is_logging}")

    trail = content.get("Trail", content.get("trail", {}))
    if trail:
        name = trail.get("Name", trail.get("TrailARN", ""))
        multi_region = trail.get("IsMultiRegionTrail", False)
        log_file_val = trail.get("LogFileValidationEnabled", False)
        if name:
            snippets.append(
                f"Trail '{name}': MultiRegion={multi_region}, LogValidation={log_file_val}"
            )

    if not snippets:
        snippets.append("No CloudTrail status information found")
    return snippets


def _extract_alarm_evidence(content: dict) -> list[str]:
    """CC7.2 — count CloudWatch alarms and summarise configuration."""
    snippets = []
    alarms = content.get("MetricAlarms", content.get("CompositeAlarms", []))
    if isinstance(alarms, list):
        count = len(alarms)
        snippets.append(f"CloudWatch alarms found: {count}")
        for alarm in alarms[:3]:  # show up to 3 examples
            name = alarm.get("AlarmName", "")
            state = alarm.get("StateValue", "")
            snippets.append(f"  Alarm '{name}': state={state}")
    else:
        snippets.append("No CloudWatch alarms data found")
    return snippets


# ── Main extraction entry point ───────────────────────────────────────────────

def extract_control_evidence(configs: list[dict]) -> dict:
    """
    Deterministic extraction — no LLM, no I/O.
    Returns {control_id: [evidence_snippets]} for CC6.1, CC6.2, CC6.3,
    CC6.6, CC7.1, CC7.2 based on the uploaded config files.

    Evidence snippets are text descriptions of what was found in the raw
    config — not pass/fail booleans (those are ConfigInspectorAgent's job).
    """
    # Index configs by source name for O(1) lookup
    by_source: dict[str, list[dict]] = {}
    for cfg in configs:
        source = cfg.get("source", "").lower()
        by_source.setdefault(source, []).append(cfg.get("content", {}))

    evidence: dict[str, list[str]] = {
        "CC6.1": [],
        "CC6.2": [],
        "CC6.3": [],
        "CC6.6": [],
        "CC7.1": [],
        "CC7.2": [],
    }

    for content in by_source.get("iam_policies", []):
        evidence["CC6.1"].extend(_extract_mfa_evidence(content))
        evidence["CC6.2"].extend(_extract_wildcard_evidence(content))

    for content in by_source.get("cloudtrail_config", []):
        evidence["CC6.3"].extend(_extract_event_selector_evidence(content))
        evidence["CC7.1"].extend(_extract_cloudtrail_active_evidence(content))

    for content in by_source.get("bucket_policies", []):
        evidence["CC6.6"].extend(_extract_public_bucket_evidence(content))

    for content in by_source.get("cloudwatch_alarms", []):
        evidence["CC7.2"].extend(_extract_alarm_evidence(content))

    # Emit "no data provided" for any control with no source config uploaded
    for control_id, snippets in evidence.items():
        if not snippets:
            evidence[control_id] = [f"No relevant config source uploaded for {control_id}"]

    return evidence
