"""
Git commit corpus hasher — DealProof dev-credential vertical.

Hashing pipeline:
  commit  → hash_commit()              → 64-char hex
  commits → compute_repo_corpus_root() → 64-char hex (Merkle root)
  commits → extract_commit_metrics()   → structured metrics dict (no LLM)

Merkle algorithm is identical to app/props/transcript_hasher.py so the same
Props verification logic can validate a git corpus root.
"""
import hashlib
import json
from datetime import datetime
from pathlib import PurePosixPath


LANGUAGE_EXT_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".r": "R",
    ".sh": "Shell",
    ".bash": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "SCSS",
}


def hash_commit(commit: dict) -> str:
    """SHA-256 of canonical commit JSON: sha, author, timestamp, message, diff_stat."""
    canonical = {
        "author": commit.get("author"),
        "diff_stat": commit.get("diff_stat"),
        "message": commit.get("message"),
        "sha": commit.get("sha"),
        "timestamp": commit.get("timestamp"),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()


def compute_repo_corpus_root(commits: list[dict]) -> str:
    """Length-prefixed Merkle root over commits. Same algorithm as transcript_hasher."""
    if not commits:
        raise ValueError("compute_repo_corpus_root requires at least one commit")
    commit_hashes = [hash_commit(c) for c in commits]
    length_prefix = len(commit_hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h) for h in commit_hashes)
    return hashlib.sha256(raw).hexdigest()


def _parse_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _detect_language(filename: str) -> str | None:
    ext = PurePosixPath(filename).suffix.lower()
    return LANGUAGE_EXT_MAP.get(ext)


def _is_test_file(filename: str) -> bool:
    parts = filename.replace("\\", "/").lower().split("/")
    name = parts[-1]
    return (
        "test" in parts[:-1]
        or "tests" in parts[:-1]
        or "spec" in parts[:-1]
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_test.go")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
    )


def extract_commit_metrics(commits: list[dict]) -> dict:
    """
    Deterministic metrics extraction — no LLM.

    Expected commit dict fields:
      sha, author, timestamp, message,
      is_merge (bool), diff_stat ({"additions", "deletions", "total"}),
      files ([{"filename", "additions", "deletions"}])

    Returns:
      total_commits, active_months, languages, avg_diff_size,
      commit_message_avg_length, test_file_ratio, merge_commit_ratio,
      first_commit_date, last_commit_date
    """
    if not commits:
        return {
            "total_commits": 0,
            "active_months": 0,
            "languages": {},
            "avg_diff_size": 0.0,
            "commit_message_avg_length": 0.0,
            "test_file_ratio": 0.0,
            "merge_commit_ratio": 0.0,
            "first_commit_date": None,
            "last_commit_date": None,
        }

    dates = [_parse_date(c.get("timestamp")) for c in commits]
    dates_valid = [d for d in dates if d is not None]
    active_months = len({(d.year, d.month) for d in dates_valid})

    languages: dict[str, int] = {}
    diff_sizes: list[float] = []
    commits_with_test_files = 0
    merge_count = 0

    for commit in commits:
        if commit.get("is_merge"):
            merge_count += 1

        ds = commit.get("diff_stat") or {}
        total_lines = ds.get("total", 0)
        if total_lines > 0:
            diff_sizes.append(float(total_lines))

        files = commit.get("files") or []
        has_test = False
        for f in files:
            fname = f.get("filename", "")
            lang = _detect_language(fname)
            if lang:
                languages[lang] = languages.get(lang, 0) + f.get("additions", 0)
            if _is_test_file(fname):
                has_test = True
        if has_test:
            commits_with_test_files += 1

    total = len(commits)
    avg_diff_size = sum(diff_sizes) / len(diff_sizes) if diff_sizes else 0.0
    commit_message_avg_length = (
        sum(len(c.get("message") or "") for c in commits) / total
    )
    test_file_ratio = commits_with_test_files / total
    merge_commit_ratio = merge_count / total

    sorted_dates = sorted(dates_valid)
    first_commit_date = sorted_dates[0].isoformat() if sorted_dates else None
    last_commit_date = sorted_dates[-1].isoformat() if sorted_dates else None

    return {
        "total_commits": total,
        "active_months": active_months,
        "languages": languages,
        "avg_diff_size": avg_diff_size,
        "commit_message_avg_length": commit_message_avg_length,
        "test_file_ratio": test_file_ratio,
        "merge_commit_ratio": merge_commit_ratio,
        "first_commit_date": first_commit_date,
        "last_commit_date": last_commit_date,
    }
