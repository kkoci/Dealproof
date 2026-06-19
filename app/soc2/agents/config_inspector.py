"""
ConfigInspectorAgent — deterministic SOC 2 control checks.

Mirrors app/picreds/constraints.py exactly:
- Pure functions, no LLM, no I/O.
- Hard boolean per control — authoritative, cannot be overridden by LLM.
- Runs first, always. ControlEvaluatorAgent receives these as established facts.

CC6.1  MFA enforced on all IAM users
CC6.2  No wildcard * policies (Action+Resource both * in Allow statements)
CC6.3  Access reviews logged (CloudTrail event selectors present)
CC6.6  No public S3 buckets
CC7.1  CloudTrail active (IsLogging: true)
CC7.2  Alerts configured (CloudWatch alarm count > 0)
"""
import json
from dataclasses import dataclass, field


@dataclass
class ControlCheckResult:
    control_id: str
    passed: bool
    finding: str
    evidence: list[str] = field(default_factory=list)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _iter_statements(content: dict | list) -> list[dict]:
    """Recursively flatten IAM policy content into Statement dicts."""
    if isinstance(content, list):
        stmts = []
        for item in content:
            stmts.extend(_iter_statements(item))
        return stmts
    if "Policies" in content:
        return _iter_statements(content["Policies"])
    if "Policy" in content and isinstance(content["Policy"], dict):
        return _iter_statements(content["Policy"])
    if "PolicyDocument" in content:
        doc = content["PolicyDocument"]
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except Exception:
                return []
        return _iter_statements(doc)
    if "Statement" in content:
        stmts = content["Statement"]
        return [stmts] if isinstance(stmts, dict) else [s for s in stmts if isinstance(s, dict)]
    return []


def _by_source(configs: list[dict]) -> dict[str, list[dict]]:
    """Index config entries by source name (lower-case)."""
    idx: dict[str, list[dict]] = {}
    for cfg in configs:
        src = cfg.get("source", "").lower()
        idx.setdefault(src, []).append(cfg.get("content", {}))
    return idx


# ── Individual checks ──────────────────────────────────────────────────────────

def check_mfa_enforcement(configs: list[dict]) -> ControlCheckResult:
    """
    CC6.1 — Pass if at least one IAM statement enforces MFA.

    Accepted patterns:
    - Deny + Condition.Bool["aws:MultiFactorAuthPresent"] = "false"
      (deny access when MFA absent — the standard AWS MFA enforcement pattern)
    - Allow + Condition.Bool["aws:MultiFactorAuthPresent"] = "true"
      (allow only when MFA present)
    """
    by_src = _by_source(configs)
    enforcing = []

    for content in by_src.get("iam_policies", []):
        for stmt in _iter_statements(content):
            effect = stmt.get("Effect", "Allow")
            cond = stmt.get("Condition", {})
            bool_cond = cond.get("Bool", {})
            for key, val in bool_cond.items():
                if "multifactorauthpresent" not in key.lower():
                    continue
                val_str = str(val).lower()
                if (effect == "Deny" and val_str == "false") or \
                   (effect == "Allow" and val_str == "true"):
                    enforcing.append(
                        f"Statement Effect={effect}: {key}={val} (MFA enforced)"
                    )

    if enforcing:
        return ControlCheckResult(
            control_id="CC6.1",
            passed=True,
            finding=f"MFA enforcement detected in {len(enforcing)} statement(s)",
            evidence=enforcing,
        )
    return ControlCheckResult(
        control_id="CC6.1",
        passed=False,
        finding="No MFA enforcement conditions found in IAM policies",
        evidence=["No Deny+MFA or Allow+MFA conditions present"],
    )


def check_least_privilege(configs: list[dict]) -> ControlCheckResult:
    """
    CC6.2 — Fail if any Allow statement has BOTH Action=* AND Resource=*.

    Deny wildcards are acceptable (they restrict, not grant).
    Partial wildcards (Action=* but Resource is scoped) are a finding but
    not the worst case — we flag them as evidence without failing the check,
    unless the full Action+Resource wildcard combination is present.
    """
    by_src = _by_source(configs)
    full_wildcards = []
    partial_wildcards = []

    for content in by_src.get("iam_policies", []):
        for stmt in _iter_statements(content):
            effect = stmt.get("Effect", "Allow")
            if effect != "Allow":
                continue
            actions = stmt.get("Action", [])
            resources = stmt.get("Resource", [])
            if isinstance(actions, str):
                actions = [actions]
            if isinstance(resources, str):
                resources = [resources]
            has_action_wildcard = "*" in actions
            has_resource_wildcard = "*" in resources
            if has_action_wildcard and has_resource_wildcard:
                full_wildcards.append("Allow: Action=* Resource=* (full admin access)")
            elif has_action_wildcard:
                partial_wildcards.append(
                    f"Allow: Action=* Resource={resources} (scoped resource)"
                )

    if full_wildcards:
        return ControlCheckResult(
            control_id="CC6.2",
            passed=False,
            finding=f"Full wildcard Allow found: {len(full_wildcards)} statement(s) grant unrestricted access",
            evidence=full_wildcards + partial_wildcards,
        )
    if partial_wildcards:
        return ControlCheckResult(
            control_id="CC6.2",
            passed=True,
            finding=f"No full wildcard Allow found; {len(partial_wildcards)} partial wildcard(s) noted",
            evidence=partial_wildcards,
        )
    return ControlCheckResult(
        control_id="CC6.2",
        passed=True,
        finding="No wildcard Allow policies found — least privilege principle observed",
        evidence=[],
    )


def check_access_logging(configs: list[dict]) -> ControlCheckResult:
    """
    CC6.3 — Pass if CloudTrail EventSelectors include management events.
    """
    by_src = _by_source(configs)
    found = []

    for content in by_src.get("cloudtrail_config", []):
        selectors = content.get("EventSelectors", [])
        advanced = content.get("AdvancedEventSelectors", [])
        for sel in selectors:
            if sel.get("IncludeManagementEvents", False):
                rw = sel.get("ReadWriteType", "All")
                found.append(f"EventSelector: ReadWriteType={rw}, IncludeManagementEvents=true")
        if advanced:
            found.append(f"AdvancedEventSelectors: {len(advanced)} configured")

    if found:
        return ControlCheckResult(
            control_id="CC6.3",
            passed=True,
            finding=f"CloudTrail management event logging confirmed ({len(found)} selector(s))",
            evidence=found,
        )
    return ControlCheckResult(
        control_id="CC6.3",
        passed=False,
        finding="No CloudTrail EventSelectors with IncludeManagementEvents=true found",
        evidence=["Management event logging cannot be confirmed"],
    )


def check_no_public_buckets(configs: list[dict]) -> ControlCheckResult:
    """
    CC6.6 — Pass if all buckets have PublicAccessBlock fully enabled
    AND no bucket policy grants public (Principal=*) Allow access.
    """
    by_src = _by_source(configs)
    failures = []
    passing = []

    for content in by_src.get("bucket_policies", []):
        items = content if isinstance(content, list) else [content]
        for item in items:
            bucket = item.get("BucketName", item.get("Bucket", "unknown"))
            pab = item.get("PublicAccessBlockConfiguration", {})
            fully_blocked = pab and all([
                pab.get("BlockPublicAcls", False),
                pab.get("IgnorePublicAcls", False),
                pab.get("BlockPublicPolicy", False),
                pab.get("RestrictPublicBuckets", False),
            ])
            if fully_blocked:
                passing.append(f"Bucket '{bucket}': PublicAccessBlock fully enabled")
            else:
                # Check bucket policy for public Allow
                policy_raw = item.get("Policy", item.get("BucketPolicy"))
                if isinstance(policy_raw, str):
                    try:
                        policy_raw = json.loads(policy_raw)
                    except Exception:
                        policy_raw = None
                if isinstance(policy_raw, dict):
                    for stmt in _iter_statements(policy_raw):
                        principal = stmt.get("Principal", "")
                        is_public = (
                            principal == "*"
                            or (isinstance(principal, dict) and principal.get("AWS") == "*")
                        )
                        if is_public and stmt.get("Effect") == "Allow":
                            failures.append(
                                f"Bucket '{bucket}': Allow Principal=* (public access granted)"
                            )
                if not failures or all(bucket not in f for f in failures):
                    if not fully_blocked:
                        failures.append(
                            f"Bucket '{bucket}': PublicAccessBlock not fully enabled"
                        )

    if not by_src.get("bucket_policies"):
        return ControlCheckResult(
            control_id="CC6.6",
            passed=False,
            finding="No bucket_policies config provided — cannot verify CC6.6",
            evidence=["Upload bucket policies to verify public access controls"],
        )

    if failures:
        return ControlCheckResult(
            control_id="CC6.6",
            passed=False,
            finding=f"Public access risk found in {len(failures)} bucket configuration(s)",
            evidence=failures,
        )
    return ControlCheckResult(
        control_id="CC6.6",
        passed=True,
        finding=f"All {len(passing)} bucket(s) have public access blocked",
        evidence=passing,
    )


def check_cloudtrail_active(configs: list[dict]) -> ControlCheckResult:
    """
    CC7.1 — Pass if at least one CloudTrail trail has IsLogging=true.
    """
    by_src = _by_source(configs)
    active = []
    inactive = []

    for content in by_src.get("cloudtrail_config", []):
        is_logging = content.get("IsLogging")
        trail = content.get("Trail", content.get("trail", {}))
        name = trail.get("Name", trail.get("TrailARN", "unnamed")) if trail else "unnamed"
        if is_logging is True:
            active.append(f"Trail '{name}': IsLogging=true")
        elif is_logging is False:
            inactive.append(f"Trail '{name}': IsLogging=false")

    if not by_src.get("cloudtrail_config"):
        return ControlCheckResult(
            control_id="CC7.1",
            passed=False,
            finding="No cloudtrail_config provided — cannot verify CC7.1",
            evidence=["Upload CloudTrail configuration to verify logging status"],
        )

    if active:
        return ControlCheckResult(
            control_id="CC7.1",
            passed=True,
            finding=f"CloudTrail active: {len(active)} active trail(s)",
            evidence=active + inactive,
        )
    return ControlCheckResult(
        control_id="CC7.1",
        passed=False,
        finding=f"No active CloudTrail trails found{'; ' + str(len(inactive)) + ' inactive' if inactive else ''}",
        evidence=inactive or ["IsLogging status not found in config"],
    )


def check_alerting_configured(configs: list[dict]) -> ControlCheckResult:
    """
    CC7.2 — Pass if at least one CloudWatch alarm is configured.
    """
    by_src = _by_source(configs)
    alarm_names = []

    for content in by_src.get("cloudwatch_alarms", []):
        alarms = content.get("MetricAlarms", content.get("CompositeAlarms", []))
        if isinstance(alarms, list):
            alarm_names.extend(
                a.get("AlarmName", "unnamed") for a in alarms
            )

    if not by_src.get("cloudwatch_alarms"):
        return ControlCheckResult(
            control_id="CC7.2",
            passed=False,
            finding="No cloudwatch_alarms config provided — cannot verify CC7.2",
            evidence=["Upload CloudWatch alarm configuration to verify alerting"],
        )

    if alarm_names:
        return ControlCheckResult(
            control_id="CC7.2",
            passed=True,
            finding=f"{len(alarm_names)} CloudWatch alarm(s) configured",
            evidence=[f"Alarm: {name}" for name in alarm_names[:10]],
        )
    return ControlCheckResult(
        control_id="CC7.2",
        passed=False,
        finding="No CloudWatch alarms found — alerting not configured",
        evidence=["MetricAlarms list is empty"],
    )


# ── Agent class ───────────────────────────────────────────────────────────────

class ConfigInspectorAgent:
    """
    Deterministic SOC 2 control inspector — mirrors app/picreds/constraints.py.
    No LLM, no I/O. Hard boolean per control. Always runs before ControlEvaluatorAgent.
    """

    CHECKS = {
        "CC6.1": check_mfa_enforcement,
        "CC6.2": check_least_privilege,
        "CC6.3": check_access_logging,
        "CC6.6": check_no_public_buckets,
        "CC7.1": check_cloudtrail_active,
        "CC7.2": check_alerting_configured,
    }

    def inspect(self, configs: list[dict]) -> dict[str, ControlCheckResult]:
        """
        Run all six CC6/CC7 checks against the uploaded configs.
        Returns {control_id: ControlCheckResult} — all six keys always present.
        """
        return {
            control_id: check_fn(configs)
            for control_id, check_fn in self.CHECKS.items()
        }
