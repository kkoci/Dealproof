"""
Tests for skill_runner.py.

All tests use --mock-inference so no network or LoRA weights required.
The FFmpeg normalize and grade steps run for real (tests that ffmpeg pipeline works).
"""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from skill_runner import run_skill, sha256_file

SKILL_PATH = Path(__file__).parent / "johnny_wedding.skill.json"
FIXTURE = Path(__file__).parent / "evals/wedding/fixtures/test_warm.jpg"
TEE_ROOT = str(Path(__file__).parent / "dev_assets") + "/"


def test_fixture_exists():
    assert FIXTURE.exists(), f"Run: ffmpeg -f lavfi -i color=c=0xF5E6D0:size=100x100:rate=1 -frames:v 1 {FIXTURE}"


def test_mock_run_produces_output():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name
    try:
        receipt = run_skill(str(SKILL_PATH), str(FIXTURE), out, mock=True, tee_root=TEE_ROOT)
        assert Path(out).exists()
        assert Path(out).stat().st_size > 0
    finally:
        os.unlink(out)


def test_receipt_shape():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name
    try:
        receipt = run_skill(str(SKILL_PATH), str(FIXTURE), out, mock=True, tee_root=TEE_ROOT)
        assert receipt["skill_id"] == "johnny-wedding-style"
        assert len(receipt["input_sha256"]) == 64
        assert len(receipt["output_sha256"]) == 64
        assert receipt["chutes_aci_quote"].startswith("mock-aci-quote-")
        assert receipt["pipeline_steps"] == ["normalize", "style_inference", "grade"]
    finally:
        os.unlink(out)


def test_input_hash_in_receipt():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name
    try:
        receipt = run_skill(str(SKILL_PATH), str(FIXTURE), out, mock=True, tee_root=TEE_ROOT)
        assert receipt["input_sha256"] == sha256_file(str(FIXTURE))
    finally:
        os.unlink(out)


def test_output_differs_from_input():
    """FFmpeg normalize+grade steps should change the file."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name
    try:
        receipt = run_skill(str(SKILL_PATH), str(FIXTURE), out, mock=True, tee_root=TEE_ROOT)
        # Hashes must differ because ffmpeg re-encoded even if pixels are same
        # (timestamps, metadata). If they collide the pipeline is a no-op.
        assert receipt["input_sha256"] != receipt["output_sha256"]
    finally:
        os.unlink(out)


def test_unknown_tool_raises():
    import copy
    with open(SKILL_PATH) as f:
        skill = json.load(f)
    skill["pipeline"][0]["tool"] = "imaginary-tool"

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as sf:
        json.dump(skill, sf)
        skill_tmp = sf.name

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name

    try:
        with pytest.raises(ValueError, match="Unknown tool"):
            run_skill(skill_tmp, str(FIXTURE), out, mock=True)
    finally:
        os.unlink(skill_tmp)
        os.unlink(out)


def test_wrong_schema_raises():
    with open(SKILL_PATH) as f:
        skill = json.load(f)
    skill["schemaVersion"] = "skill.tee.v99"

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as sf:
        json.dump(skill, sf)
        skill_tmp = sf.name

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        out = f.name

    try:
        with pytest.raises(AssertionError):
            run_skill(skill_tmp, str(FIXTURE), out, mock=True)
    finally:
        os.unlink(skill_tmp)
        os.unlink(out)
