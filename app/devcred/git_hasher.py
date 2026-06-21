"""
Git corpus hasher — dev-credential vertical.

Hashing pipeline for authenticated commit history:
  commit  → hash_commit()               → 64-char hex
  commits → compute_repo_corpus_root()  → 64-char hex (Merkle root)
  commits → extract_commit_metrics()    → structured metrics dict

The corpus root is used as repo_corpus_root in the SeniorDevCredential.
Algorithm is identical to app/props/transcript_hasher.py.
"""
import hashlib
import json


def hash_commit(commit: dict) -> str:
    """SHA-256 of canonical commit JSON: sha, author, timestamp, message, diff_stat."""
    canonical = {
        "author": commit.get("author", ""),
        "diff_stat": commit.get("diff_stat", {}),
        "message": commit.get("message", ""),
        "sha": commit["sha"],
        "timestamp": commit.get("timestamp", ""),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def compute_repo_corpus_root(commits: list[dict]) -> str:
    """Length-prefixed Merkle root over commit hashes. Same algorithm as transcript_hasher."""
    if not commits:
        raise ValueError("compute_repo_corpus_root requires at least one commit")
    commit_hashes = [hash_commit(c) for c in commits]
    length_prefix = len(commit_hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h) for h in commit_hashes)
    return hashlib.sha256(raw).hexdigest()


_EXT_TO_LANG = {
    ".py": "Python", ".go": "Go", ".rs": "Rust",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".java": "Java", ".kt": "Kotlin", ".swift": "Swift",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".c": "C", ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
    ".sol": "Solidity", ".scala": "Scala",
    ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell",
}


def _is_test_file(filename: str) -> bool:
    lower = filename.lower()
    return (
        "/test" in lower
        or lower.startswith("test_")
        or lower.startswith("tests/")
        or lower.endswith("_test.py")
        or lower.endswith("_test.go")
        or lower.endswith(".test.js")
        or lower.endswith(".test.ts")
        or lower.endswith(".spec.js")
        or lower.endswith(".spec.ts")
        or "/spec/" in lower
        or "/specs/" in lower
    )


def _lang_from_files(filenames: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for fname in filenames:
        if "." in fname:
            ext = "." + fname.rsplit(".", 1)[-1].lower()
            lang = _EXT_TO_LANG.get(ext)
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    return counts


def extract_commit_metrics(commits: list[dict]) -> dict:
    """
    Deterministic extraction — no LLM.
    Returns:
    {
      total_commits: int,
      active_months: int,
      languages: {lang: file_count},
      avg_diff_size: float,
      commit_message_avg_length: float,
      test_file_ratio: float,
      merge_commit_ratio: float,
      first_commit_date: str | None,
      last_commit_date: str | None,
    }
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

    total = len(commits)
    active_months: set[str] = set()
    language_counts: dict[str, int] = {}
    diff_sizes: list[float] = []
    msg_lengths: list[int] = []
    test_commit_count = 0
    merge_count = 0

    for commit in commits:
        ts = commit.get("timestamp", "")
        if ts and len(ts) >= 7:
            active_months.add(ts[:7])

        msg = commit.get("message", "")
        first_line = msg.split("\n")[0].strip()
        msg_lengths.append(len(first_line))

        if first_line.lower().startswith("merge "):
            merge_count += 1

        diff_stat = commit.get("diff_stat", {})
        additions = diff_stat.get("additions", 0) or 0
        deletions = diff_stat.get("deletions", 0) or 0
        diff_sizes.append(float(additions + deletions))

        changed_files = commit.get("changed_files", [])
        for lang, cnt in _lang_from_files(changed_files).items():
            language_counts[lang] = language_counts.get(lang, 0) + cnt
        if any(_is_test_file(f) for f in changed_files):
            test_commit_count += 1

    timestamps = sorted(c.get("timestamp", "") for c in commits if c.get("timestamp"))

    return {
        "total_commits": total,
        "active_months": len(active_months),
        "languages": language_counts,
        "avg_diff_size": sum(diff_sizes) / len(diff_sizes) if diff_sizes else 0.0,
        "commit_message_avg_length": (
            sum(msg_lengths) / len(msg_lengths) if msg_lengths else 0.0
        ),
        "test_file_ratio": test_commit_count / total if total > 0 else 0.0,
        "merge_commit_ratio": merge_count / total if total > 0 else 0.0,
        "first_commit_date": timestamps[0] if timestamps else None,
        "last_commit_date": timestamps[-1] if timestamps else None,
    }
