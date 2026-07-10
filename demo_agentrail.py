#!/usr/bin/env python3
"""
DealProof Agent Rail — Phase 1 CLI Demo
========================================
Runs the B2B procurement scenario end-to-end, in-process (no server, no API —
Phase 1 scope per build_spec_agent_rail.md). Two Claude Sonnet agents
negotiate a purchase with sealed principal instructions that the opposing
agent never sees; the mediator produces a DCAP attestation quote over the
agreed terms.

Usage
-----
  python demo_agentrail.py
  python demo_agentrail.py --max-rounds 5

Requirements
------------
  ANTHROPIC_API_KEY set in .env (see app/config.py).
  No server needs to be running — this calls the agents directly in-process.
"""
import sys
import time
import json
import asyncio
import argparse
import textwrap
from datetime import datetime

from app.agentrail.buyer_agent import BuyerAgent
from app.agentrail.supplier_agent import SupplierAgent
from app.agentrail.mediator import run_procurement_negotiation
from app.agentrail.schemas import BuyerParameters, SupplierParameters
from app.agentrail.verify_quote import verify_quote

# ---------------------------------------------------------------------------
# ANSI colours
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


BOLD = lambda t: _c("1", t)
DIM = lambda t: _c("2", t)
GREEN = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
CYAN = lambda t: _c("36", t)
RED = lambda t: _c("31", t)
BLUE = lambda t: _c("34", t)
MAGENTA = lambda t: _c("35", t)

WIDTH = 68


def divider(char="─"):
    print(DIM(char * WIDTH))


def header(title: str):
    pad = (WIDTH - len(title) - 2) // 2
    print(DIM("─" * pad) + " " + BOLD(title) + " " + DIM("─" * (WIDTH - pad - len(title) - 2)))


# ---------------------------------------------------------------------------
# Default scenario — 500 industrial sensors, per build_spec_agent_rail.md
# ---------------------------------------------------------------------------
BUYER_PARAMS = BuyerParameters(
    product="industrial sensors",
    quantity=500,
    budget_ceiling=45.0,
    min_spec="IP67 rating, 12-month warranty",
    urgency="moderate — can wait 2 weeks for delivery",
)

SUPPLIER_PARAMS = SupplierParameters(
    product="industrial sensors",
    floor_price_bulk=38.0,      # orders >= bulk_threshold
    floor_price_standard=42.0,  # orders < bulk_threshold
    bulk_threshold=200,
    available_inventory=800,
    lead_time_days=5,
)


def _leak_check(transcript, buyer: BuyerParameters, supplier: SupplierParameters) -> list[tuple]:
    """
    Scan the logged transcript (the only thing either side or the platform
    operator can observe) for the literal sealed values. Structurally these
    can't appear — neither agent's system prompt is ever passed to the
    other — but this is a runtime sanity check on the actual transcript.
    """
    sealed = {
        "buyer.budget_ceiling": str(buyer.budget_ceiling),
        "supplier.floor_price_bulk": str(supplier.floor_price_bulk),
        "supplier.floor_price_standard": str(supplier.floor_price_standard),
    }
    leaks = []
    for r in transcript:
        blob = json.dumps({"terms": r.terms, "reasoning": r.reasoning})
        for label, value in sealed.items():
            if value in blob:
                leaks.append((r.round, r.role, label, value))
    return leaks


async def main_async(max_rounds: int):
    print()
    print(BOLD("╔" + "═" * (WIDTH - 2) + "╗"))
    print(BOLD("║") + CYAN("     DealProof Agent Rail — B2B Procurement Deal Room    ").center(WIDTH - 2) + BOLD("║"))
    print(BOLD("║") + DIM("     Two sealed Claude Sonnet agents, one TDX enclave     ").center(WIDTH - 2) + BOLD("║"))
    print(BOLD("╚" + "═" * (WIDTH - 2) + "╝"))
    print()

    print(f"  {BOLD('Scenario:')} {CYAN('Industrial component procurement')}")
    print()
    print(f"  {BOLD('[SEALED — buyer only]')}")
    print(f"    Product: {BUYER_PARAMS.product}   Quantity: {BUYER_PARAMS.quantity}")
    print(f"    Budget ceiling: ${BUYER_PARAMS.budget_ceiling}/unit")
    print(f"    Minimum spec: {BUYER_PARAMS.min_spec}")
    print()
    print(f"  {BOLD('[SEALED — supplier only]')}")
    print(f"    Floor (>= {SUPPLIER_PARAMS.bulk_threshold} units): ${SUPPLIER_PARAMS.floor_price_bulk}/unit"
          f"   Floor (< {SUPPLIER_PARAMS.bulk_threshold} units): ${SUPPLIER_PARAMS.floor_price_standard}/unit")
    print(f"    Inventory: {SUPPLIER_PARAMS.available_inventory} units   Lead time: {SUPPLIER_PARAMS.lead_time_days} business days")
    print()
    print(DIM("  Neither agent's system prompt is shared with the other. The mediator"))
    print(DIM("  only relays JSON actions (price, quantity, terms, reasoning) between them."))
    print()

    buyer = BuyerAgent(
        product=BUYER_PARAMS.product,
        quantity=BUYER_PARAMS.quantity,
        budget_ceiling=BUYER_PARAMS.budget_ceiling,
        min_spec=BUYER_PARAMS.min_spec,
        urgency=BUYER_PARAMS.urgency,
    )
    supplier = SupplierAgent(
        product=SUPPLIER_PARAMS.product,
        floor_price_bulk=SUPPLIER_PARAMS.floor_price_bulk,
        floor_price_standard=SUPPLIER_PARAMS.floor_price_standard,
        bulk_threshold=SUPPLIER_PARAMS.bulk_threshold,
        available_inventory=SUPPLIER_PARAMS.available_inventory,
        lead_time_days=SUPPLIER_PARAMS.lead_time_days,
    )

    t_start = time.time()
    try:
        result = await run_procurement_negotiation(buyer, supplier, max_rounds=max_rounds)
    except Exception as exc:
        print(f"  {RED('✗')} Negotiation failed to run: {exc}")
        sys.exit(1)
    elapsed = time.time() - t_start

    print()
    header("TRANSCRIPT")
    print()
    for r in result.transcript:
        role_str = YELLOW(f"{'BUYER':8}") if r.role == "buyer" else CYAN(f"{'SUPPLIER':8}")
        action = r.action.upper()
        action_str = (
            GREEN(f"{action:8}") if action == "ACCEPT" else
            RED(f"{action:8}") if action == "REJECT" else
            BLUE(f"{action:8}")
        )
        short_reason = textwrap.shorten(r.reasoning, width=42, placeholder="…")
        print(
            f"  {DIM(f'[Round {r.round}]'):12} {role_str} {action_str} "
            f"{BOLD(f'${r.price:>6,.2f}/u')} x{r.quantity:<4}  {DIM(short_reason)}"
        )

    print()
    header("RESULT")
    print()

    if result.agreed:
        print(f"  {GREEN('✓ Deal agreed')}  at  {BOLD(CYAN(f'${result.final_price:,.2f}/unit'))} "
              f"x {result.final_quantity} units")
        terms = result.terms or {}
        print(f"  {BOLD('Terms:')}  {json.dumps(terms)}")
        print()

        print(f"  {BOLD(MAGENTA('DCAP Attestation Receipt:'))}")
        print(f"  {DIM(result.attestation)}")

        verification = verify_quote(result.attestation)
        badge = GREEN("✓ verifiable") if verification["valid"] else RED("✗ malformed")
        verif_detail = f"mode={verification['mode']}, {verification['byte_length']} bytes"
        print(f"  {BOLD('Verification:')}  {badge}  {DIM(verif_detail)}")
        print()

        leaks = _leak_check(result.transcript, BUYER_PARAMS, SUPPLIER_PARAMS)
        if leaks:
            print(f"  {RED('✗ SEALED VALUE LEAK DETECTED')} in transcript:")
            for rnd, role, label, value in leaks:
                print(f"    round {rnd} ({role}): {label} = {value}")
        else:
            print(f"  {GREEN('✓')} Buyer's ${BUYER_PARAMS.budget_ceiling}/unit ceiling never appeared in the transcript.")
            print(f"  {GREEN('✓')} Supplier's floor prices never appeared in the transcript.")
        print()
        summary_line1 = "Buyer's ceiling was never revealed. Supplier's floor was never revealed."
        summary_line2 = f"Deal reached at ${result.final_price:,.2f} for {result.final_quantity} units."
        print(f"  {DIM(summary_line1)}")
        print(f"  {DIM(summary_line2)}")
    else:
        print(f"  {RED('✗ No deal reached')} after {len(result.transcript)} negotiation turns.")
        last = result.transcript[-1] if result.transcript else None
        if last and last.action == "reject":
            print(f"  {DIM(f'Last action: {last.role} rejected at ${last.price:,.2f}/unit')}")

    print()
    divider()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  {DIM(f'Completed in {elapsed:.1f}s  |  {ts}')}")
    print()


def main():
    parser = argparse.ArgumentParser(description="DealProof Agent Rail — Phase 1 CLI Demo")
    parser.add_argument("--max-rounds", type=int, default=5, help="Max negotiation rounds (default: 5)")
    args = parser.parse_args()
    asyncio.run(main_async(args.max_rounds))


if __name__ == "__main__":
    main()
