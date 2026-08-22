"""Vertical slice — real probes against a real model.

    python -m scripts.run_vertical_slice --smoke          # 20 mandates, control only, ~$1
    python -m scripts.run_vertical_slice --mandates 60    # control + 4 arms
    python -m scripts.run_vertical_slice --dry-run        # cost preflight, dispatch nothing

THIS COSTS MONEY. Every run does a cost preflight first and refuses to dispatch
above MAX_RUN_COST_USD.

Start with --smoke. Its only job is to answer one question: what is the focal
product's baseline selection rate? Everything downstream depends on that number
landing between roughly 0.10 and 0.20, and finding out it is 0.02 after a full
run is an expensive way to learn it.
"""
from __future__ import annotations

import os

import argparse
import sys
from pathlib import Path

from acop.adapters.anthropic_adapter import AnthropicBuyerAdapter, ProviderPricing
from acop.adapters.resumable import ResumableAdapter
from acop.catalog_v1 import FOCAL_ID, build_catalog, verification_report
from acop.economics import MerchantEconomics
from acop.interventions import release_0_set
from acop.mandates import build_mandate_set, segment_summary
from acop.manifest import ArtifactStore
from acop.pipeline import print_summary, run_pipeline
from acop.preflight import estimate_cost, load_env, require_env
from scripts.run_simulated import demo_economics

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run real probes against a provider.")
    p.add_argument("--mandates", type=int, default=None,
                   help="Default 60 (full run) or 20 (--smoke). Explicit values "
                        "override the --smoke default too.")
    p.add_argument("--reps", type=int, default=None,
                   help="Replications per mandate. Breadth beats depth — "
                        "extra reps of the same mandate buy very little power for "
                        "the main design, but multiple reps are what let ICC "
                        "actually be measured (see --smoke --reps N). Default 1 "
                        "(full run) or 1 (--smoke); explicit values override "
                        "--smoke's default too.")
    p.add_argument("--prompt-variants", type=int, default=1)
    p.add_argument("--smoke", action="store_true",
                   help="20 mandates, control arm only. Reads the baseline rate.")
    p.add_argument("--dry-run", action="store_true", help="Preflight only, dispatch nothing.")
    p.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    p.add_argument("--force-reparse", action="store_true",
                   help="Re-parse stored raw artifacts; dispatch nothing new.")
    p.add_argument("--allow-unverified", action="store_true",
                   help="Run against a catalog with unfilled checkout fields. "
                        "Shipping and lead-time arms will be meaningless.")
    p.add_argument("--experiment-id", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    load_env()

    # ---- catalog, with the verification gate front and centre
    report = verification_report()
    if not report["ready_for_real_run"]:
        print(f"\n  CATALOG NOT VERIFIED: {report['total_unverified_fields']} fields "
              f"across {report['products_with_gaps']} products still need checkout data.")
        if not args.allow_unverified:
            print("  See fixtures/VERIFY_CHECKOUT_FIELDS.md. "
                  "Pass --allow-unverified to proceed anyway.\n")
            return 1
        print("  Proceeding with --allow-unverified. Shipping and SLA arms are NOT "
              "measuring anything real in this run.\n")

    catalog = build_catalog(allow_unverified=args.allow_unverified)
    focal = next(p for p in catalog if p.product_id == FOCAL_ID)

    # ---- design
    n_mandates = args.mandates if args.mandates is not None else (20 if args.smoke else 60)
    reps = args.reps if args.reps is not None else 1
    mandates = build_mandate_set(n=n_mandates)
    arms = [] if args.smoke else release_0_set(focal)
    n_arms = len(arms) + 1
    n_probes = n_mandates * reps * n_arms

    model = require_env("PROVIDER_A_MODEL",
                        "Set it to the exact model ID from Anthropic's current docs.")
    in_price = float(require_env("PROVIDER_A_INPUT_PER_MTOK"))
    out_price = float(require_env("PROVIDER_A_OUTPUT_PER_MTOK"))
    budget = float(os.environ.get("MAX_RUN_COST_USD", "25"))

    print(f"\n  catalog   {len(catalog)} products, focal {focal.brand} {focal.title}")
    print(f"  mandates  {n_mandates} across {len(segment_summary(mandates))} segments")
    print(f"  design    {n_arms} arm(s) x {reps} rep(s) = {n_probes:,} probes")
    print(f"  model     {model}")

    # ---- cost gate
    est = estimate_cost(
        mandate=mandates[0], candidates=catalog, n_probes=n_probes,
        input_per_mtok=in_price, output_per_mtok=out_price, budget_usd=budget,
    )
    print(est.render())

    if not est.within_budget:
        print(f"\n  REFUSING TO DISPATCH. Projected ${est.total_usd:,.2f} exceeds "
              f"MAX_RUN_COST_USD=${budget:,.2f}.")
        print("  Lower --mandates, or raise the budget in .env if this is intended.\n")
        return 1

    if args.dry_run:
        print("\n  --dry-run: nothing dispatched.\n")
        return 0

    if not args.yes:
        reply = input(f"\n  Dispatch {n_probes:,} probes for ~${est.total_usd:,.2f}? [y/N] ")
        if reply.strip().lower() not in ("y", "yes"):
            print("  Aborted.\n")
            return 1

    # ---- adapters
    require_env("ANTHROPIC_API_KEY")
    store = ArtifactStore(ROOT / "artifacts")
    inner = AnthropicBuyerAdapter(
        model=model,
        pricing=ProviderPricing(input_per_mtok=in_price, output_per_mtok=out_price),
        store=store,
        temperature=1.0,
        diagnostic_rate=0.07,
    )
    adapter = ResumableAdapter(inner=inner, store=store, force_reparse=args.force_reparse)

    exp_id = args.experiment_id or (
        "slice_smoke_001" if args.smoke else f"slice_release0_{n_mandates}m"
    )

    out = run_pipeline(
        experiment_id=exp_id,
        catalog=catalog,
        focal_product_id=FOCAL_ID,
        mandates=mandates,
        arms=arms,
        merchant_economics=demo_economics(focal.price_cents),
        adapter=adapter,
        artifacts_dir=ROOT / "artifacts",
        replications=reps,
        prompt_variants=args.prompt_variants,
        evidence_class="E1a_CONTROLLED_LAB_SINGLE_PROVIDER",
    )

    usage = adapter.usage_summary()
    print(f"\n  dispatched {usage['probes_dispatched']:,} | "
          f"reused from disk {usage['probes_reused_from_disk']:,} | "
          f"actual cost ${usage.get('estimated_cost_usd', 0):.2f} "
          f"(projected ${est.total_usd:.2f})")

    if args.smoke:
        _smoke_verdict(out)
    else:
        print_summary(out)
    return 0


def _smoke_verdict(out: dict) -> None:
    """The smoke run has one job: read the baseline and say what it means."""
    import json

    effects = json.loads((Path(out["artifacts_dir"]) / "effects.json").read_text())
    rate = effects["control_selection_rate"]
    fair = 1 / 12

    print("\n" + "=" * 66)
    print("  SMOKE VERDICT")
    print("=" * 66)
    print(f"  baseline selection rate : {rate:.3f}   (1/12 = {fair:.3f})")
    print(f"  parser quality pass     : {effects['validity']['parser_quality_pass']}")
    print(f"  low-confidence parses   : {effects['validity']['low_confidence_parses']}")

    if rate < 0.05:
        print("\n  TOO LOW. The focal is uncompetitive — treatment effects will not")
        print("  resolve at any sane probe budget. Strengthen the focal's specs or")
        print("  price before spending on a full run.")
    elif rate > 0.35:
        print("\n  TOO HIGH. The focal is saturating — interventions have no room to")
        print("  move it. Weaken the focal or strengthen competitors.")
    else:
        print("\n  IN BAND. Proceed to the full run:")
        print("      python -m scripts.run_vertical_slice --mandates 60")
    print()


if __name__ == "__main__":
    sys.exit(main())
