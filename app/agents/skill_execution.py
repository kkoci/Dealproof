"""
SkillExecutionAgent — thin wrapper around app/skills/runner.run_skill().

Does not reimplement pipeline logic. Calls run_skill(), captures its receipt
dict, hashes it canonically, and returns a SkillExecutionReceipt model.
SkillExecutionError is raised (not swallowed) on any pipeline failure.
"""

import hashlib
import json

from app.api.schemas import SkillExecutionReceipt
from app.skills.runner import run_skill


class SkillExecutionError(Exception):
    pass


class SkillExecutionAgent:
    """
    Wraps run_skill() in the DealProof credential shape.

    execute() is synchronous — PIL and ffmpeg are CPU-bound, not I/O-bound,
    and the existing skill_runner pipeline is synchronous. Wrapping in asyncio
    would add complexity with no benefit here.
    """

    def execute(
        self,
        skill_path: str,
        input_path: str,
        output_path: str,
        tee_root: str,
        mock: bool = False,
    ) -> SkillExecutionReceipt:
        """
        Run the skill and return a receipt model with a canonical hash.

        Args:
            skill_path:  path to the .skill.json file (seller-controlled)
            input_path:  buyer-supplied input image
            output_path: where the styled result is written
            tee_root:    local path that replaces /tee/skill/ (never sent to buyer)
            mock:        pass True to skip Chutes ACI network call (dev/test only)

        Raises:
            SkillExecutionError: wraps any pipeline failure (ffmpeg, PIL, network)
        """
        try:
            receipt_dict = run_skill(skill_path, input_path, output_path, mock=mock, tee_root=tee_root)
        except Exception as exc:
            raise SkillExecutionError(f"Skill pipeline failed: {exc}") from exc

        backend = receipt_dict.get("chutes_aci_quote") or ""

        canonical = json.dumps(
            {
                "skill_id": receipt_dict["skill_id"],
                "input_sha256": receipt_dict["input_sha256"],
                "output_sha256": receipt_dict["output_sha256"],
                "lora_sha256": receipt_dict["lora_sha256"],
                "backend": backend,
                "pipeline_steps": receipt_dict["pipeline_steps"],
            },
            sort_keys=True,
        )
        receipt_hash = hashlib.sha256(canonical.encode()).hexdigest()

        return SkillExecutionReceipt(
            skill_id=receipt_dict["skill_id"],
            input_sha256=receipt_dict["input_sha256"],
            output_sha256=receipt_dict["output_sha256"],
            lora_sha256=receipt_dict["lora_sha256"],
            backend=backend,
            pipeline_steps=receipt_dict["pipeline_steps"],
            receipt_hash=receipt_hash,
        )
