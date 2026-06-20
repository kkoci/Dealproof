"""
Synthetic git commit fixtures for DealProof dev-credential tests.

Each scenario produces a list of commit dicts in the same format as
app/devcred/git_hasher.extract_commit_metrics() expects:

  {
    sha, author, timestamp (ISO-8601), message,
    is_merge (bool),
    diff_stat: {additions, deletions, total} | None,
    files: [{filename, additions, deletions}]
  }

Seven scenarios
---------------
genuine_senior        8 years, Go + Python, 35% test ratio, meaningful messages
genuine_mid           4 years, JavaScript, 15% test ratio
genuine_junior        1 year, Python, low test ratio, short messages
adversarial_messages  SCAE: junior metrics, impressive commit messages
adversarial_churn     SCAE: high commit count, whitespace/formatting noise
adversarial_plagiarism SCAE: large diffs, low test ratio, inconsistent months
thin_history          edge: 90 days, insufficient signal

All values are derived deterministically — no random module required.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _fake_sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _spread_dates(start: datetime, end: datetime, count: int) -> list[datetime]:
    """Return `count` evenly-spaced datetimes from start to end (inclusive)."""
    if count <= 1:
        return [start]
    delta = (end - start) / (count - 1)
    return [start + delta * i for i in range(count)]


def _make_commit(
    index: int,
    scenario: str,
    dt: datetime,
    message: str,
    files: list[dict],
    is_merge: bool = False,
) -> dict:
    sha = _fake_sha(f"{scenario}:{index}:{dt.isoformat()}")
    additions = sum(f["additions"] for f in files)
    deletions = sum(f["deletions"] for f in files)
    return {
        "sha": sha,
        "author": "Developer",
        "timestamp": _iso(dt),
        "message": message,
        "is_merge": is_merge,
        "diff_stat": {"additions": additions, "deletions": deletions, "total": additions + deletions},
        "files": files,
    }


# ---------------------------------------------------------------------------
# Scenario generators
# ---------------------------------------------------------------------------

def _genuine_senior() -> list[dict]:
    """
    8 years, Go + Python, 35% test ratio, meaningful long messages.
    Expected: seniority_signal = 'senior'
    """
    start = datetime(2016, 1, 15, tzinfo=timezone.utc)
    end = datetime(2024, 1, 15, tzinfo=timezone.utc)
    count = 1000
    dates = _spread_dates(start, end, count)

    commits = []
    go_files = [
        {"filename": "app/api/handler.go", "additions": 60, "deletions": 8},
        {"filename": "app/db/store.go", "additions": 45, "deletions": 5},
    ]
    py_files = [
        {"filename": "scripts/analyze.py", "additions": 55, "deletions": 6},
        {"filename": "tools/bench.py", "additions": 30, "deletions": 4},
    ]
    test_go_files = [
        {"filename": "app/api/handler_test.go", "additions": 40, "deletions": 3},
    ]
    test_py_files = [
        {"filename": "tests/test_analyze.py", "additions": 35, "deletions": 2},
    ]

    messages = [
        "feat: add distributed consensus handler for leader election",
        "fix: resolve race condition in connection pool under load",
        "refactor: extract authentication middleware into separate package",
        "feat: implement retry logic with exponential backoff",
        "fix: correct off-by-one error in pagination cursor",
        "perf: cache frequently accessed user records in memory",
        "feat: add structured logging with correlation IDs",
        "refactor: migrate database layer to use prepared statements",
    ]

    for i, dt in enumerate(dates):
        msg = messages[i % len(messages)]
        is_test = (i % 3 == 0)  # 33% test commits → above 0.15 threshold
        if is_test:
            files = test_go_files if i % 2 == 0 else test_py_files
        else:
            files = go_files if i % 2 == 0 else py_files
        commits.append(_make_commit(i, "senior", dt, msg, files))

    return commits


def _genuine_mid() -> list[dict]:
    """
    4 years, JavaScript + TypeScript, 15% test ratio, medium messages.
    Expected: seniority_signal = 'mid'
    """
    start = datetime(2020, 3, 1, tzinfo=timezone.utc)
    end = datetime(2024, 3, 1, tzinfo=timezone.utc)
    count = 350
    dates = _spread_dates(start, end, count)

    src_files = [
        {"filename": "src/components/Dashboard.tsx", "additions": 45, "deletions": 6},
        {"filename": "src/api/client.js", "additions": 38, "deletions": 4},
        {"filename": "src/utils/format.ts", "additions": 22, "deletions": 3},
    ]
    test_files = [
        {"filename": "tests/dashboard.test.ts", "additions": 30, "deletions": 2},
    ]
    messages = [
        "add dashboard component with filtering",
        "fix API response parsing for empty arrays",
        "update type definitions for user model",
        "refactor utility functions",
        "improve error handling in data fetch",
        "add loading state to list component",
    ]

    commits = []
    for i, dt in enumerate(dates):
        msg = messages[i % len(messages)]
        is_test = (i % 7 == 0)  # ~14% → just above 0.15 threshold in aggregate
        files = test_files if is_test else src_files
        commits.append(_make_commit(i, "mid", dt, msg, files))

    return commits


def _genuine_junior() -> list[dict]:
    """
    1 year, Python only, low test ratio, terse messages.
    Expected: seniority_signal = 'junior'
    """
    start = datetime(2023, 1, 10, tzinfo=timezone.utc)
    end = datetime(2024, 1, 10, tzinfo=timezone.utc)
    count = 28
    dates = _spread_dates(start, end, count)

    files = [{"filename": "app.py", "additions": 12, "deletions": 3}]
    messages = ["update", "fix", "changes", "wip", "edit", "add", "remove"]

    commits = []
    for i, dt in enumerate(dates):
        msg = messages[i % len(messages)]
        commits.append(_make_commit(i, "junior", dt, msg, files))

    return commits


def _adversarial_messages() -> list[dict]:
    """
    SCAE: junior-level metrics (1 year, tiny Python diffs, no tests)
    but impressively-worded commit messages claiming senior-level work.

    Hard seniority_signal must remain 'junior' — the inspector uses metrics,
    not message content, for its determination.
    """
    start = datetime(2023, 1, 10, tzinfo=timezone.utc)
    end = datetime(2024, 1, 10, tzinfo=timezone.utc)
    count = 28
    dates = _spread_dates(start, end, count)

    # Same tiny diffs as genuine_junior
    files = [{"filename": "app.py", "additions": 12, "deletions": 3}]

    # Impressive-sounding messages — should not affect GitInspectorAgent
    impressive_messages = [
        "led architecture refactor of distributed consensus layer",
        "designed microservices orchestration framework from scratch",
        "drove migration of monolith to event-driven microservices",
        "architected zero-downtime blue-green deployment pipeline",
        "implemented custom CRDT-based conflict resolution engine",
        "introduced domain-driven design patterns across the codebase",
        "spearheaded adoption of formal verification for critical paths",
    ]

    commits = []
    for i, dt in enumerate(dates):
        msg = impressive_messages[i % len(impressive_messages)]
        commits.append(_make_commit(i, "adv_messages", dt, msg, files))

    return commits


def _adversarial_churn() -> list[dict]:
    """
    SCAE: high commit count (600) from whitespace/formatting commits.
    avg_diff_size is tiny (~3 lines) and messages are terse (~3 chars).
    commit_message_avg_length < 15 → avg_commit_quality = 'low'.

    Expected: seniority_signal = 'junior'
    """
    start = datetime(2022, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 6, 1, tzinfo=timezone.utc)
    count = 600
    dates = _spread_dates(start, end, count)

    # Tiny formatting diffs — single file, 2 lines changed
    churn_files = [{"filename": "app/main.go", "additions": 2, "deletions": 1}]
    churn_messages = ["fmt", "fix", "wip", "doc"]

    commits = []
    for i, dt in enumerate(dates):
        msg = churn_messages[i % len(churn_messages)]
        commits.append(_make_commit(i, "adv_churn", dt, msg, churn_files))

    return commits


def _adversarial_plagiarism() -> list[dict]:
    """
    SCAE: commits contain large, sophisticated-looking diffs (copied from OSS repos)
    but test_file_ratio is near zero and active months are sparse.

    Copying does not come with tests; activity is bursts, not consistent.
    Expected: seniority_signal != 'senior'
    """
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, tzinfo=timezone.utc)
    count = 200
    # Burst pattern: only 8 out of 24 months active
    active_months = [0, 1, 5, 6, 12, 13, 19, 20]
    active_dates: list[datetime] = []
    for m_offset in active_months:
        month_start = start + timedelta(days=m_offset * 30)
        # 25 commits clustered in each active month
        for d in range(25):
            active_dates.append(month_start + timedelta(days=d))
    # trim to count
    active_dates = sorted(active_dates)[:count]

    # Large diffs (looks sophisticated) — no test files
    oss_files = [
        {"filename": "lib/vendor/framework.go", "additions": 200, "deletions": 50},
        {"filename": "lib/vendor/utils.go", "additions": 150, "deletions": 30},
    ]
    messages = [
        "add framework integration",
        "integrate vendor library",
        "port utility module",
        "add OSS component",
    ]

    commits = []
    for i, dt in enumerate(active_dates):
        msg = messages[i % len(messages)]
        commits.append(_make_commit(i, "adv_plagiarism", dt, msg, oss_files))

    return commits


def _thin_history() -> list[dict]:
    """
    Edge case: only 90 days of activity, 8 commits. Insufficient signal.
    Expected: seniority_signal = 'junior'
    """
    start = datetime(2023, 10, 1, tzinfo=timezone.utc)
    end = datetime(2023, 12, 31, tzinfo=timezone.utc)
    count = 8
    dates = _spread_dates(start, end, count)

    files = [{"filename": "README.md", "additions": 5, "deletions": 1}]
    messages = ["initial commit", "update docs", "add example"]

    commits = []
    for i, dt in enumerate(dates):
        msg = messages[i % len(messages)]
        commits.append(_make_commit(i, "thin", dt, msg, files))

    return commits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, list[dict]] = {
    "genuine_senior": _genuine_senior(),
    "genuine_mid": _genuine_mid(),
    "genuine_junior": _genuine_junior(),
    "adversarial_messages": _adversarial_messages(),
    "adversarial_churn": _adversarial_churn(),
    "adversarial_plagiarism": _adversarial_plagiarism(),
    "thin_history": _thin_history(),
}


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None

    for name, commits in SCENARIOS.items():
        if target and name != target:
            continue
        print(f"\n{'='*60}")
        print(f"Scenario: {name}  ({len(commits)} commits)")
        from app.devcred.git_hasher import extract_commit_metrics, compute_repo_corpus_root
        metrics = extract_commit_metrics(commits)
        root = compute_repo_corpus_root(commits)
        print(f"corpus_root:    {root[:32]}...")
        print(f"total_commits:  {metrics['total_commits']}")
        print(f"active_months:  {metrics['active_months']}")
        print(f"avg_diff_size:  {metrics['avg_diff_size']:.1f}")
        print(f"test_ratio:     {metrics['test_file_ratio']:.3f}")
        print(f"msg_avg_len:    {metrics['commit_message_avg_length']:.1f}")
        print(f"languages:      {list(metrics['languages'].keys())}")
        print(f"first→last:     {metrics['first_commit_date'][:10]} → {metrics['last_commit_date'][:10]}")
