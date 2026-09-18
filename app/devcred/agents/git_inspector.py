"""
GitInspectorAgent — deterministic layer, no LLM.

Computes hard boolean and scalar findings from commit metrics produced
by git_hasher.extract_commit_metrics(). These findings are authoritative:
the LLM layer (GitEvaluatorAgent) may adjust seniority upward but cannot
downgrade below the hard seniority_signal set here.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone


SENIORITY_ORDER = ["junior", "mid", "senior", "staff"]

LANG_DEPTH_THRESHOLD = 500       # additions to count a language as "deep"
TEST_CULTURE_THRESHOLD = 0.15    # test_file_ratio above this → has_test_culture
CONSISTENCY_THRESHOLD = 0.60     # active_months / total_months above this → consistent


@dataclass
class GitInspectionReport:
    years_active: float
    languages_deep: list[str]
    has_test_culture: bool
    consistent_contribution: bool
    avg_commit_quality: str   # "low" | "medium" | "high"
    seniority_signal: str     # "junior" | "mid" | "senior"


def _parse_iso(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        return None


def _commit_quality(msg_avg_len: float, avg_diff_size: float) -> str:
    """
    high:   meaningful messages (>=30 chars) AND focused diffs (10-300 lines)
    low:    terse messages (<15 chars) OR churn-indicator diffs (>500 lines)
    medium: everything else
    """
    if msg_avg_len >= 30 and 10 <= avg_diff_size <= 300:
        return "high"
    if msg_avg_len < 15 or avg_diff_size > 500:
        return "low"
    return "medium"


def _seniority(
    years_active: float,
    languages_deep: list[str],
    has_test_culture: bool,
    consistent_contribution: bool,
    avg_commit_quality: str,
) -> str:
    """
    Purely quantitative thresholds — LLM may adjust upward only.

    senior: >= 6 years, >= 2 deep languages, test culture, consistent
    mid:    >= 3 years, >= 1 deep language or consistent, medium/high commit quality
    junior: everything else
    """
    if (
        years_active >= 6
        and len(languages_deep) >= 2
        and has_test_culture
        and consistent_contribution
    ):
        return "senior"

    if (
        years_active >= 3
        and (len(languages_deep) >= 1 or consistent_contribution)
        and avg_commit_quality in ("medium", "high")
    ):
        return "mid"

    return "junior"


EVENTS_MID_SIGNAL_MIN_EVENTS = 50   # minimum total events to consider "mid" from events-stream evidence alone
EVENTS_MID_SIGNAL_MIN_MONTHS = 2    # minimum distinct active months for the same


@dataclass
class EventsInspectionReport:
    """
    Route B (events-stream fallback) counterpart to GitInspectionReport.

    Deliberately cannot reach "senior": GitHub's events timeline carries no diffs,
    languages, or test-file signal — the same evidence GitInspectionReport.seniority_signal
    requires (>= 2 deep languages, has_test_culture) to call something "senior" is
    structurally unavailable here. Capping this signal at "mid" is not a special-cased
    rule bolted on top — it falls out of the same _seniority() thresholds Route A uses,
    just fed permanently-empty/false values for the fields Route B cannot supply.
    """
    total_events: int
    active_months: int
    event_type_counts: dict
    first_event_date: str | None
    last_event_date: str | None
    seniority_signal: str   # "junior" | "mid" — never "senior" from events alone


def inspect_events(event_metrics: dict) -> EventsInspectionReport:
    """
    Deterministic, no-LLM inspection of Route B event metrics (see
    git_hasher.extract_event_metrics). Mirrors GitInspectorAgent.inspect()'s
    discipline — the hard signal here is likewise authoritative and cannot be
    upgraded by an LLM (Route B skips the LLM evaluation step entirely; see
    routes.py::evaluate_credential's events_stream branch for why).
    """
    total_events = event_metrics.get("total_events", 0)
    active_months = event_metrics.get("active_months", 0)
    event_type_counts = event_metrics.get("event_type_counts", {})

    has_pr_activity = event_type_counts.get("PullRequestEvent", 0) > 0
    has_review_activity = event_type_counts.get("PullRequestReviewEvent", 0) > 0

    # Events-specific "mid" bar: meaningful volume, spread across more than one
    # month (not a single burst), with evidence of collaborative work (a PR opened
    # or reviewed) rather than solo pushes alone. There is no path to "senior" here
    # at all — see the class docstring for why that's structural, not a threshold
    # tuning choice.
    if (
        total_events >= EVENTS_MID_SIGNAL_MIN_EVENTS
        and active_months >= EVENTS_MID_SIGNAL_MIN_MONTHS
        and (has_pr_activity or has_review_activity)
    ):
        seniority_signal = "mid"
    else:
        seniority_signal = "junior"

    return EventsInspectionReport(
        total_events=total_events,
        active_months=active_months,
        event_type_counts=event_type_counts,
        first_event_date=event_metrics.get("first_event_date"),
        last_event_date=event_metrics.get("last_event_date"),
        seniority_signal=seniority_signal,
    )


class GitInspectorAgent:
    """
    Deterministic layer. Runs first. No LLM, no network.
    All findings are computable from the metrics dict alone.
    """

    def inspect(self, metrics: dict) -> GitInspectionReport:
        first = _parse_iso(metrics.get("first_commit_date"))
        last = _parse_iso(metrics.get("last_commit_date"))

        if first and last:
            delta_days = (last - first).days
            years_active = round(delta_days / 365.25, 2)
            # months between first and last commit (floor 1 to avoid div-by-zero)
            total_months = max(1, round(delta_days / 30.44))
        else:
            years_active = 0.0
            total_months = 1

        active_months: int = metrics.get("active_months", 0)
        languages: dict = metrics.get("languages", {})

        languages_deep = [
            lang for lang, lines in languages.items() if lines > LANG_DEPTH_THRESHOLD
        ]

        has_test_culture = metrics.get("test_file_ratio", 0.0) > TEST_CULTURE_THRESHOLD

        consistent_contribution = (active_months / total_months) > CONSISTENCY_THRESHOLD

        avg_commit_quality = _commit_quality(
            msg_avg_len=metrics.get("commit_message_avg_length", 0.0),
            avg_diff_size=metrics.get("avg_diff_size", 0.0),
        )

        seniority_signal = _seniority(
            years_active=years_active,
            languages_deep=languages_deep,
            has_test_culture=has_test_culture,
            consistent_contribution=consistent_contribution,
            avg_commit_quality=avg_commit_quality,
        )

        return GitInspectionReport(
            years_active=years_active,
            languages_deep=languages_deep,
            has_test_culture=has_test_culture,
            consistent_contribution=consistent_contribution,
            avg_commit_quality=avg_commit_quality,
            seniority_signal=seniority_signal,
        )
