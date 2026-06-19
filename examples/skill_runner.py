#!/usr/bin/env python3
"""
skill.tee.v1 runner.

Dev:  python skill_runner.py skill.json input.jpg output.jpg --mock-inference
Prod: runs inside dstack TDX CVM; network policy in docker-compose enforces allowNet.
      Deno alternative: deno run --allow-net=chutes.ai --allow-read --allow-write
                        --allow-run=ffmpeg skill_runner.ts
"""

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _remap(value: str, tee_root: str) -> str:
    if tee_root:
        return value.replace("/tee/skill/", tee_root.rstrip("/") + "/")
    return value


def run_ffmpeg(step: dict, paths: dict, workdir: str, tee_root: str = "") -> None:
    src = paths[step["reads"][0]]
    dst = str(Path(workdir) / f"{step['id']}.jpg")
    paths[step["writes"][0]] = dst

    args = [_remap(a, tee_root) for a in step.get("args", [])]
    cmd = ["ffmpeg", "-y", "-i", src] + args + [dst]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg step '{step['id']}' failed:\n{result.stderr}")


def run_pil_style(step: dict, paths: dict, workdir: str) -> str:
    """Local PIL approximation of a warm film style — no API, no key needed."""
    from PIL import Image, ImageEnhance, ImageOps
    import numpy as np

    src = paths[step["reads"][0]]
    dst = str(Path(workdir) / f"{step['id']}.jpg")
    paths[step["writes"][0]] = dst

    img = Image.open(src).convert("RGB")
    arr = np.array(img, dtype=np.float32) / 255.0

    # Lift shadows (S-curve bottom), pull highlights
    arr = np.where(arr < 0.5,
                   arr * (1 + 0.12 * (1 - arr * 2)),
                   arr)
    # Warm shift: boost R, slightly lift G, pull B
    arr[:, :, 0] = np.clip(arr[:, :, 0] * 1.10 + 0.02, 0, 1)
    arr[:, :, 1] = np.clip(arr[:, :, 1] * 1.03, 0, 1)
    arr[:, :, 2] = np.clip(arr[:, :, 2] * 0.88, 0, 1)
    # Slight desaturation (matte / film look)
    lum = arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114
    arr = arr * 0.82 + lum[:, :, None] * 0.18

    out = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    # Boost contrast slightly
    out = ImageEnhance.Contrast(out).enhance(1.08)
    out.save(dst, quality=92)
    return "pil-style:local"


def run_fal(step: dict, paths: dict, workdir: str, tee_root: str = "") -> str:
    import fal_client

    src = paths[step["reads"][0]]
    dst = str(Path(workdir) / f"{step['id']}.jpg")
    paths[step["writes"][0]] = dst

    image_url = fal_client.upload_file(src)

    prompt_path = _remap(step.get("stylePromptPath", ""), tee_root)
    with open(prompt_path) as f:
        prompt = f.read().strip()

    fal_args = {
        "image_url": image_url,
        "prompt": prompt,
        "strength": step.get("strength", 0.52),
        "num_inference_steps": step.get("steps", 28),
        "guidance_scale": step.get("guidanceScale", 3.5),
    }
    if "loraWeightsUrl" in step:
        fal_args["loras"] = [{"path": step["loraWeightsUrl"], "scale": step.get("loraScale", 1.0)}]

    model = step.get("falModel", "fal-ai/flux/dev/image-to-image")
    result = fal_client.run(model, arguments=fal_args)

    output_url = result["images"][0]["url"]
    urllib.request.urlretrieve(output_url, dst)

    return f"fal:{result.get('request_id', 'unknown')}"


def run_chutes_aci(step: dict, paths: dict, skill: dict, workdir: str, mock: bool, tee_root: str = "") -> str:
    src = paths[step["reads"][0]]
    dst = str(Path(workdir) / f"{step['id']}.jpg")
    paths[step["writes"][0]] = dst

    if mock:
        shutil.copy(src, dst)
        return "mock-aci-quote-" + sha256_file(src)[:16]

    api_key = os.environ["CHUTES_API_KEY"]
    endpoint = skill["providers"]["inference"]["endpoint"]

    with open(src, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    with open(_remap(step["stylePromptPath"], tee_root)) as f:
        prompt = f.read().strip()

    payload = json.dumps({
        "model": skill["providers"]["inference"]["model"],
        "lora_path": skill["lora"]["path"],
        "prompt": prompt,
        "image": image_b64,
        "strength": step.get("strength", 0.52),
        "guidance_scale": step.get("guidanceScale", 3.5),
        "num_inference_steps": step.get("steps", 28),
    }).encode()

    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        aci_quote = resp.headers.get("x-chutes-aci-quote", "")
        body = json.loads(resp.read())

    with open(dst, "wb") as f:
        f.write(base64.b64decode(body["image"]))

    return aci_quote


def run_skill(skill_path: str, input_photo: str, output_photo: str, mock: bool, tee_root: str = "") -> dict:
    with open(skill_path) as f:
        skill = json.load(f)

    assert skill["schemaVersion"] == "skill.tee.v1"

    input_hash = sha256_file(input_photo)
    paths = {"input.photo": input_photo}
    aci_quote = None

    with tempfile.TemporaryDirectory(prefix="skill_work_") as workdir:
        for step in skill["pipeline"]:
            tool = step["tool"]
            if tool == "ffmpeg":
                run_ffmpeg(step, paths, workdir, tee_root)
            elif tool == "pil-style":
                aci_quote = run_pil_style(step, paths, workdir)
            elif tool == "fal":
                aci_quote = run_fal(step, paths, workdir, tee_root)
            elif tool == "chutes-aci":
                aci_quote = run_chutes_aci(step, paths, skill, workdir, mock, tee_root)
            else:
                raise ValueError(f"Unknown tool: {tool}")

        shutil.copy(paths["output.photo"], output_photo)

    lora_path = _remap(skill["lora"]["path"], tee_root)
    lora_hash = sha256_file(lora_path) if Path(lora_path).exists() else skill["lora"]["sha256"]

    return {
        "skill_id": skill["id"],
        "input_sha256": input_hash,
        "output_sha256": sha256_file(output_photo),
        "lora_sha256": lora_hash,
        "chutes_aci_quote": aci_quote,
        "pipeline_steps": [s["id"] for s in skill["pipeline"]],
    }


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
