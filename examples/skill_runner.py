#!/usr/bin/env python3
"""
skill.tee.v1 runner — CLI entry point.

Core logic lives in app/skills/runner.py.
This file is a thin shim so the CLI keeps working as before.

Dev:  python skill_runner.py skill.json input.jpg output.jpg --mock-inference
Prod: runs inside dstack TDX CVM; network policy in docker-compose enforces allowNet.
      Deno alternative: deno run --allow-net=chutes.ai --allow-read --allow-write
                        --allow-run=ffmpeg skill_runner.ts
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root so app.skills is importable when running this file directly.
_ROOT = str(Path(__file__).parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Re-export everything from the package module so callers that do
#   sys.path.insert(0, "<examples dir>")
#   from skill_runner import run_skill, sha256_file
# continue to work without modification.
from app.skills.runner import (  # noqa: E402 — path patch above
    run_skill,
    sha256_file,
    _remap,
    _ffmpeg_path,
    run_ffmpeg,
    run_pil_style,
    run_fal,
    run_chutes_aci,
)

__all__ = [
    "run_skill",
    "sha256_file",
    "_remap",
    "_ffmpeg_path",
    "run_ffmpeg",
    "run_pil_style",
    "run_fal",
    "run_chutes_aci",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("skill", help="Path to .skill.json")
    parser.add_argument("input", help="Input photo")
    parser.add_argument("output", help="Output photo")
    parser.add_argument("--mock-inference", action="store_true",
                        help="Skip Chutes call; copy input→output (dev only)")
    parser.add_argument("--tee-root", default="",
                        help="Remap /tee/skill/ paths to a local directory (dev only)")
    args = parser.parse_args()

    receipt = run_skill(args.skill, args.input, args.output, args.mock_inference, args.tee_root)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
