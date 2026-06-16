"""
Transcript corpus hasher — ETHGlobal NYC integration.

Hashing pipeline for TinyCloud Listen transcripts:
  sentence  → hash_sentence()         → 64-char hex
  sentences → hash_transcript()       → 64-char hex
  hashes    → compute_corpus_root()   → 64-char hex (Merkle root)

The corpus root is used as data_hash in POST /api/deals.
Algorithm is identical to app/props/verifier.py so the same
Props verification logic validates transcript corpora.
"""
import hashlib
import json


def hash_sentence(sentence: dict) -> str:
    """
    SHA-256 of canonical JSON of one TranscriptSentence.
    TinyCloud shape: { index, speaker_id, speaker_name, text, start_time, end_time, language }
    Null language coerced to 'en'. Fixed key set ignores future Listen schema additions.
    """
    canonical = {
        "end_time": sentence.get("end_time"),
        "index": sentence["index"],
        "language": sentence.get("language") or "en",
        "speaker_id": sentence["speaker_id"],
        "speaker_name": sentence["speaker_name"],
        "start_time": sentence.get("start_time"),
        "text": sentence["text"],
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()


def hash_transcript(sentences: list[dict]) -> str:
    """SHA-256 of canonical JSON of all sentences for one conversation."""
    if not sentences:
        raise ValueError("hash_transcript requires at least one sentence")
    ordered = sorted(sentences, key=lambda s: s["index"])
    canonical = [
        {
            "end_time": s.get("end_time"),
            "index": s["index"],
            "language": s.get("language") or "en",
            "speaker_id": s["speaker_id"],
            "speaker_name": s["speaker_name"],
            "start_time": s.get("start_time"),
            "text": s["text"],
        }
        for s in ordered
    ]
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode()
    ).hexdigest()


def compute_corpus_root(transcript_hashes: list[str]) -> str:
    """
    Length-prefixed Merkle root over per-conversation transcript hashes.
    Same algorithm as props/verifier.py compute_merkle_root — inlined here to
    avoid the httpx import chain. Corpus root plugs directly into seller_proof.
    """
    if not transcript_hashes:
        raise ValueError("compute_corpus_root requires at least one hash")
    length_prefix = len(transcript_hashes).to_bytes(4, "big")
    raw = length_prefix + b"".join(bytes.fromhex(h) for h in transcript_hashes)
    return hashlib.sha256(raw).hexdigest()
