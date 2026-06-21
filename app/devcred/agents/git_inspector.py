"""
GitInspectorAgent — deterministic hard-finding layer.

Runs first. No LLM, no network. Computes hard findings from commit metrics.
Mirrors MetricsInspectorAgent pattern — hard findings are authoritative;
the LLM evaluator receives them as grounding and cannot downgrade below them.
"""
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------------------
# Thresholds — named constants, never magic numbers
# ---------------------------------------------------------------------------

YEARS_SENIOR = 6.0               # minimum years active for senior hard signal
YEARS_MID = 3.0                  # minimum years active for mid hard signal
LANGUAGE_DEPTH_MIN_FILES = 20    # file touches to be "deep" in a language
TEST_RATIO_THRESHOLD = 0.15      # test_file_ratio for "test culture"
CONSISTENCY_THRESHOLD = 0.60     # active_months / total_possible_months
MSG_LENGTH_HIGH = 50             # avg first-line chars for "high" quality
MSG_LENGTH_MED = 20              # avg first-line chars for "medium" quality
DIFF_SIZE_MEANINGFUL = 20.0      # avg lines changed for meaningful commits
COMMIT_COUNT_MID = 200           # minimum commits to count toward mid signal


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class GitInspectionReport:
    years_active: float
    languages_deep: list[str]          # langs with >= LANGUAGE_DEPTH_MIN_FILES touches
    has_test_culture: bool             # test_file_ratio >= TEST_RATIO_THRESHOLD
    consistent_contribution: bool      # active_months / total_months >= CONSISTENCY_THRESHOLD
    avg_commit_quality: str            # "low" | "medium" | "high"
    seniority_signal: str              # "junior" | "mid" | "senior" — hard floor for LLM


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class GitInspectorAgent:
    """
    Deterministic layer. No LLM. Runs first.

    Accepts metrics dict from extract_commit_metrics.
    The LLM evaluator may adjust seniority upward only —
    it must never downgrade below seniority_signal.
    """

    def inspect(self, metrics: dict) -> GitInspectionReport:
        # ------------------------------------------------------------------ #
        # Years active — from first/last commit date
        # ------------------------------------------------------------------ #
        first = metrics.get("first_commit_date")
        last = metrics.get("last_commit_date")
        years_active = 0.0
        if first and last and len(first) >= 10 and len(last) >= 10:
            try:
                d0 = datetime.fromisoformat(first[:10])
                d1 = datetime.fromisoformat(last[:10])
                years_active = max(0.0, (d1 - d0).days / 365.25)
            except (ValueError, TypeError):
                pass

        # ------------------------------------------------------------------ #
        # Language depth
        # ------------------------------------------------------------------ #
        languages = metrics.get("languages", {})
        languages_deep = sorted(
            lang for lang, count in languages.items()
            if count >= LANGUAGE_DEPTH_MIN_FILES
        )

        # ------------------------------------------------------------------ #
        # Test culture
        # ------------------------------------------------------------------ #
        test_ratio = metrics.get("test_file_ratio", 0.0)
        has_test_culture = test_ratio >= TEST_RATIO_THRESHOLD

        # ------------------------------------------------------------------ #
        # Consistency — active months vs total possible months
        # ------------------------------------------------------------------ #
        active_months = metrics.get("active_months", 0)
        total_possible = max(1, round(years_active * 12))
        consistent = (active_months / total_possible) >= CONSISTENCY_THRESHOLD

        # ------------------------------------------------------------------ #
        # Commit quality — from message length and diff size
        # ------------------------------------------------------------------ #
        avg_msg = metrics.get("commit_message_avg_length", 0.0)
        avg_diff = metrics.get("avg_diff_size", 0.0)
        merge_ratio = metrics.get("merge_commit_ratio", 0.0)
        # Normalize diff size by excluding merge commits
        adjusted_diff = avg_diff / max(1 - merge_ratio, 0.1)
        if avg_msg >= MSG_LENGTH_HIGH and adjusted_diff >= DIFF_SIZE_MEANINGFUL:
            quality = "high"
        elif avg_msg >= MSG_LENGTH_MED or adjusted_diff >= DIFF_SIZE_MEANINGFUL:
            quality = "medium"
        else:
            quality = "low"

        # ------------------------------------------------------------------ #
        # Seniority signal — hard floor; LLM may raise but not lower
        # ------------------------------------------------------------------ #
        total_commits = metrics.get("total_commits", 0)

        if (
            years_active >= YEARS_SENIOR
            and len(languages_deep) >= 2
            and consistent
            and has_test_culture
        ):
            seniority = "senior"
        elif years_active >= YEARS_MID and (
            len(languages_deep) >= 1 or total_commits >= COMMIT_COUNT_MID
        ):
            seniority = "mid"
        else:
            seniority = "junior"

        return GitInspectionReport(
            years_active=round(years_active, 2),
            languages_deep=languages_deep,
            has_test_culture=has_test_culture,
            consistent_contribution=consistent,
            avg_commit_quality=quality,
            seniority_signal=seniority,
        )
