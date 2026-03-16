#!/usr/bin/env python3
"""
DealProof — CLI Demo Script
===========================
Runs a complete verifiable AI negotiation end-to-end and prints every step
live in the terminal.

Usage
-----
  # Against local server (docker compose up --build first, or uvicorn):
  python demo.py

  # Against a Phala Cloud CVM:
  python demo.py --url https://your-cvm.phala.network

  # Pick a specific scenario:
  python demo.py --scenario medical

  # Two-step flow (create then negotiate separately):
  python demo.py --two-step

  # Skip Props verification (no seller_proof — Phase 2 mode):
  python demo.py --no-proof

Scenarios
---------
  medical    — 10 GB DICOM medical imaging dataset
  vision     — 10 GB labelled COCO-style image dataset   (default)
  lidar      — 50 GB autonomous vehicle LiDAR point cloud
  finance    — 5-year tick-by-tick FX trading time series
  nlp        — 2B-token filtered web text corpus

Requirements
------------
  pip install httpx   (already in requirements.txt)
  Server must be running (local or remote).
"""

import sys
import time
import json
import hashlib
import argparse
import threading
import textwrap
from datetime import datetime

import httpx

# ---------------------------------------------------------------------------
# ANSI colours — fall back gracefully if terminal doesn't support them
# ---------------------------------------------------------------------------
try:
    import os
    _COLOUR = os.name != "nt" or "WT_SESSION" in os.environ or "TERM" in os.environ
except Exception:
    _COLOUR = False

def _c(code: str, text: str) -> str:
    if not _COLOUR:
        return text
    return f"\033[{code}m{text}\033[0m"

BOLD   = lambda t: _c("1", t)
DIM    = lambda t: _c("2", t)
GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
CYAN   = lambda t: _c("36", t)
RED    = lambda t: _c("31", t)
BLUE   = lambda t: _c("34", t)
MAGENTA = lambda t: _c("35", t)

# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------
SCENARIOS = {
    "vision": {
        "label": "Labelled Vision Dataset",
        "buyer_budget": 1000.0,
        "buyer_requirements": (
            "10 GB COCO-style labelled image dataset for fine-tuning a computer vision model. "
            "Must include bounding boxes, segmentation masks, and class labels. "
            "Minimum 500k images across 80+ categories. 2023 or newer."
        ),
        "data_description": (
            "10 GB curated COCO-style dataset: 520k images, 80 categories, "
            "bounding boxes + segmentation masks, quality-verified 2024, "
            "licensed for ML training use."
        ),
        "floor_price": 600.0,
        "chunks": [
            b"coco_images_part1_520k_bbox",
            b"coco_images_part2_segmasks",
            b"coco_metadata_labels_2024",
            b"coco_quality_verification_cert",
            b"coco_license_ml_training_only",
        ],
    },
    "medical": {
        "label": "Medical Imaging Dataset",
        "buyer_budget": 1200.0,
        "buyer_requirements": (
            "10 GB DICOM medical imaging dataset for training a radiology AI model. "
            "Must be fully de-identified (HIPAA compliant), include radiologist labels, "
            "and cover chest, abdomen, and brain MRI. 2022 or newer."
        ),
        "data_description": (
            "10 GB de-identified DICOM dataset: 12,000 studies across chest/abdomen/brain MRI, "
            "double-blind radiologist labels, IRB-cleared, HIPAA-compliant, "
            "licensed for non-commercial ML research."
        ),
        "floor_price": 800.0,
        "chunks": [
            b"dicom_chest_4200_studies_labelled",
            b"dicom_abdomen_3800_studies_labelled",
            b"dicom_brain_4000_studies_labelled",
            b"dicom_radiologist_labels_v2",
            b"dicom_hipaa_clearance_cert_2024",
        ],
    },
    "lidar": {
        "label": "Autonomous Vehicle LiDAR Data",
        "buyer_budget": 2500.0,
        "buyer_requirements": (
            "50 GB LiDAR point cloud dataset for autonomous vehicle perception. "
            "Needs 3D bounding boxes, lane markings, weather diversity (rain/fog/night), "
            "and GPS-synchronised camera frames. Urban + highway scenarios."
        ),
        "data_description": (
            "50 GB multi-modal AV dataset: 1,200 hours LiDAR + camera, "
            "3D bounding boxes, HD map annotations, 6 weather conditions, "
            "collected across 12 cities, 2023-2024."
        ),
        "floor_price": 1800.0,
        "chunks": [
            b"lidar_urban_600h_3d_bbox",
            b"lidar_highway_600h_lane_marks",
            b"camera_sync_rgb_depth_1200h",
            b"hd_map_annotations_12_cities",
            b"weather_labels_6_conditions",
            b"gps_imu_sync_metadata",
        ],
    },
    "finance": {
        "label": "FX Trading Time Series",
        "buyer_budget": 800.0,
        "buyer_requirements": (
            "5-year tick-by-tick FX trading data for training a quant model. "
            "Must cover major pairs (EUR/USD, GBP/USD, USD/JPY), include bid/ask spread, "
            "volume, and order book depth. Clean (no gaps > 30 min)."
        ),
        "data_description": (
            "5-year FX tick data (2019-2024): 8 major pairs, bid/ask/mid, "
            "level-2 order book depth, 99.7% uptime, 2.1B rows, "
            "sourced from Tier-1 prime broker feed."
        ),
        "floor_price": 500.0,
        "chunks": [
            b"fx_ticks_2019_2020_eurusd_gbpusd",
            b"fx_ticks_2021_2022_usdjpy_usdchf",
            b"fx_ticks_2023_2024_majors",
            b"orderbook_l2_depth_all_pairs",
            b"data_quality_gap_report",
        ],
    },
    "nlp": {
        "label": "NLP Training Corpus",
        "buyer_budget": 1500.0,
        "buyer_requirements": (
            "2B-token filtered web text corpus for pre-training a language model. "
            "Must be deduplicated, toxicity-filtered, language-identified (English only), "
            "and include source URL provenance. CommonCrawl-derived acceptable."
        ),
        "data_description": (
            "2.1B-token curated English web corpus: CommonCrawl-derived, "
            "C4-style quality filter, 98.3% dedup rate, toxicity filter (Perspective API), "
            "URL provenance included, compressed parquet format."
        ),
        "floor_price": 900.0,
        "chunks": [
            b"nlp_corpus_shard_1_500M_tokens",
            b"nlp_corpus_shard_2_500M_tokens",
            b"nlp_corpus_shard_3_500M_tokens",
            b"nlp_corpus_shard_4_600M_tokens",
            b"nlp_dedup_quality_filter_report",
            b"nlp_toxicity_provenance_metadata",
        ],
    },
}

# ---------------------------------------------------------------------------
# Proof builder
# ---------------------------------------------------------------------------

def build_seller_proof(chunks: list[bytes]) -> tuple[str, dict]:
    """
    Build a valid DealProof Props seller_proof from a list of chunk byte strings.
    Returns (data_hash, seller_proof).
    """
    chunk_hashes = [hashlib.sha256(c).hexdigest() for c in chunks]
    raw = b"".join(bytes.fromhex(h) for h in chunk_hashes)
    root_hash = hashlib.sha256(raw).hexdigest()
    return root_hash, {
        "root_hash": root_hash,
        "chunk_hashes": chunk_hashes,
        "chunk_count": len(chunks),
        "algorithm": "sha256",
    }

# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------

class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str):
        self.message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._start_time = time.time()

    def _spin(self):
        i = 0
        while not self._stop.is_set():
            elapsed = time.time() - self._start_time
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r{CYAN(frame)} {self.message}  {DIM(f'{elapsed:.1f}s')}  ")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        elapsed = time.time() - self._start_time
        sys.stdout.write(f"\r{' ' * (len(self.message) + 20)}\r")
        sys.stdout.flush()
        return False

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

WIDTH = 68

def divider(char="─"):
    print(DIM(char * WIDTH))

def header(title: str):
    pad = (WIDTH - len(title) - 2) // 2
    print(DIM("─" * pad) + " " + BOLD(title) + " " + DIM("─" * (WIDTH - pad - len(title) - 2)))

def truncate_attestation(quote: str, max_bytes: int = 32) -> str:
    """Show first N bytes of a hex quote with byte count."""
    clean = quote.lstrip("0x")
    byte_count = len(clean) // 2
    preview = clean[: max_bytes * 2]
    return f"0x{preview}…  [{byte_count} bytes, Intel TDX quote]"

# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------

def run_demo(base_url: str, scenario_key: str, two_step: bool, include_proof: bool):
    scenario = SCENARIOS[scenario_key]

    # Header
    print()
    print(BOLD("╔" + "═" * (WIDTH - 2) + "╗"))
    print(BOLD("║") + CYAN("       DealProof — Verifiable AI Data Negotiation       ").center(WIDTH - 2) + BOLD("║"))
    print(BOLD("║") + DIM("  Powered by Claude claude-sonnet-4-6 + Phala TEE (Intel TDX)  ").center(WIDTH - 2) + BOLD("║"))
    print(BOLD("╚" + "═" * (WIDTH - 2) + "╝"))
    print()

    print(f"  {BOLD('Scenario:')}  {CYAN(scenario['label'])}")
    print(f"  {BOLD('Buyer budget:')}  ${scenario['buyer_budget']:,.2f}   "
          f"{BOLD('Seller floor:')}  ${scenario['floor_price']:,.2f}")
    print(f"  {BOLD('Server:')}  {base_url}")
    print(f"  {BOLD('Props verification:')}  {'enabled' if include_proof else 'disabled (--no-proof)'}")
    print()

    # Health check
    try:
        resp = httpx.get(f"{base_url}/health", timeout=5.0)
        resp.raise_for_status()
        health = resp.json()
        tee_label = GREEN("production (real Intel TDX)") if health.get("tee_mode") == "production" else YELLOW("simulation (tappd-simulator)")
        print(f"  {GREEN('✓')} Server healthy  |  TEE mode: {tee_label}")
    except Exception as exc:
        print(f"  {RED('✗')} Cannot reach server at {base_url}: {exc}")
        print(f"    Run:  {DIM('docker compose up --build')}  or  {DIM('uvicorn app.main:app --reload')}")
        sys.exit(1)

    print()

    # Build seller proof
    data_hash, seller_proof = build_seller_proof(scenario["chunks"])
    if include_proof:
        print(f"  {BOLD('[Props]')} Generated seller proof for {len(scenario['chunks'])} data chunks")
        print(f"  {BOLD('[Props]')} Root hash: {DIM(data_hash[:32])}…")
        print()

    # Build request payload
    payload: dict = {
        "buyer_budget":       scenario["buyer_budget"],
        "buyer_requirements": scenario["buyer_requirements"],
        "data_description":   scenario["data_description"],
        "data_hash":          data_hash,
        "floor_price":        scenario["floor_price"],
    }
    if include_proof:
        payload["seller_proof"] = seller_proof

    # Run negotiation
    t_start = time.time()
    result_data = None
    error = None

    if two_step:
        # ── Two-step: POST /api/deals → POST /api/deals/{id}/negotiate ──
        with Spinner("Creating deal…"):
            try:
                r = httpx.post(f"{base_url}/api/deals", json=payload, timeout=10.0)
                r.raise_for_status()
                deal_id = r.json()["deal_id"]
            except Exception as exc:
                error = str(exc)

        if not error:
            print(f"  {GREEN('✓')} Deal created: {DIM(deal_id)}")
            print()
            with Spinner("Running verification + negotiation inside TEE…"):
                try:
                    r = httpx.post(
                        f"{base_url}/api/deals/{deal_id}/negotiate",
                        timeout=180.0,
                    )
                    r.raise_for_status()
                    result_data = r.json()
                except Exception as exc:
                    error = str(exc)
    else:
        # ── Single-call: POST /api/deals/run ──
        with Spinner("Running verification + negotiation inside TEE…"):
            try:
                r = httpx.post(
                    f"{base_url}/api/deals/run",
                    json=payload,
                    timeout=180.0,
                )
                r.raise_for_status()
                result_data = r.json()
            except httpx.HTTPStatusError as exc:
                error = f"HTTP {exc.response.status_code}: {exc.response.text}"
            except Exception as exc:
                error = str(exc)

    elapsed = time.time() - t_start

    if error:
        print(f"  {RED('✗')} Request failed: {error}")
        sys.exit(1)

    # Print transcript
    print()
    header("TRANSCRIPT")
    print()

    transcript = result_data.get("transcript", [])
    if not transcript:
        print(f"  {DIM('(no transcript returned)')}")
    else:
        prev_round = 0
        for entry in transcript:
            rnd = entry["round"]
            if rnd != prev_round:
                prev_round = rnd

            role    = entry["role"].upper()
            action  = entry["action"].upper()
            price   = entry.get("price", 0)
            reason  = entry.get("reasoning", "")

            role_str   = CYAN(f"{'SELLER':6}") if entry["role"] == "seller" else YELLOW(f"{'BUYER':6}")
            action_str = GREEN(f"{action:8}") if action in ("ACCEPT",) else \
                         RED(f"{action:8}")   if action in ("REJECT",) else \
                         BLUE(f"{action:8}")

            # Truncate reasoning to keep output clean
            short_reason = textwrap.shorten(reason, width=45, placeholder="…")

            print(
                f"  {DIM(f'[Round {rnd}]'):12} "
                f"{role_str} {action_str} "
                f"{BOLD(f'${price:>9,.2f}')}  "
                f"{DIM(short_reason)}"
            )

    print()
    header("RESULT")
    print()

    agreed = result_data.get("agreed", False)

    if agreed:
        price = result_data.get("final_price", 0)
        terms = result_data.get("terms") or {}
        scope = terms.get("access_scope", "—")
        days  = terms.get("duration_days", "—")

        print(f"  {GREEN('✓ Deal agreed')}  at  {BOLD(CYAN(f'${price:,.2f}'))}")
        print(f"  {BOLD('Access scope:')}  {scope}   {BOLD('Duration:')}  {days} days")
        print()

        # Props verification attestation
        verif_att = result_data.get("data_verification_attestation")
        if verif_att:
            print(f"  {BOLD(MAGENTA('Data Verification Attestation (Props / TDX):'))}")
            print(f"  {DIM(truncate_attestation(verif_att))}")
            print()

        # Deal attestation
        deal_att = result_data.get("attestation")
        if deal_att:
            print(f"  {BOLD(MAGENTA('Deal Attestation (Negotiation / TDX):'))}")
            print(f"  {DIM(truncate_attestation(deal_att))}")
            print()

        if verif_att or deal_att:
            print(f"  {DIM('Both quotes independently verifiable via Intel DCAP root CA.')}")
            print(f"  {DIM('On a real Phala Cloud CVM, submit to: https://proof.phala.network')}")
        else:
            print(f"  {YELLOW('⚠')}  No TEE attestation returned.")
            print(f"  {DIM('Start with: docker compose up --build  (requires tappd simulator)')}")

        print()

        # On-chain placeholder (Phase 4)
        print(f"  {BOLD('On-chain escrow:')}  {DIM('Phase 4 — not yet deployed')}")
        print(f"  {DIM('(Phase 4 will: deposit ETH to DealProof.sol → verify attestation → release payment)')}")

    else:
        print(f"  {RED('✗ No deal reached')}  after {len(transcript)} negotiation turns.")
        last = transcript[-1] if transcript else {}
        if last.get("action") in ("reject", "REJECT"):
            last_role  = last["role"]
            last_price = last.get("price", 0)
            print(f"  {DIM(f'Last action: {last_role} rejected at ${last_price:,.2f}')}")

    print()
    divider()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"  {DIM(f'Completed in {elapsed:.1f}s  |  {ts}  |  {base_url}')}"
    )
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DealProof — Verifiable AI Negotiation Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Scenarios:  vision (default), medical, lidar, finance, nlp
        Examples:
          python demo.py
          python demo.py --scenario medical
          python demo.py --url https://your-cvm.phala.network --scenario lidar
          python demo.py --two-step
          python demo.py --no-proof
        """),
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the DealProof API server (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default="vision",
        help="Demo scenario to run (default: vision)",
    )
    parser.add_argument(
        "--two-step",
        action="store_true",
        help="Use the two-step flow: POST /api/deals then POST /api/deals/{id}/negotiate",
    )
    parser.add_argument(
        "--no-proof",
        action="store_true",
        help="Skip Props verification (omit seller_proof — Phase 2 backward-compat mode)",
    )
    args = parser.parse_args()

    run_demo(
        base_url=args.url.rstrip("/"),
        scenario_key=args.scenario,
        two_step=args.two_step,
        include_proof=not args.no_proof,
    )


if __name__ == "__main__":
    main()
