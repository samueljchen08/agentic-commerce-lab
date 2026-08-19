"""Full loop on the simulated oracle. Free, no API calls, seconds to run.

This is E0: it proves the SOFTWARE behaves correctly under known assumptions.
It says nothing about how a real model behaves. Use it for every structural
change, every economics change, and all report development.
"""
from __future__ import annotations

from pathlib import Path

from acop.adapters import SimulatedAgentAdapter
from acop.catalog import PLACEHOLDER_FOCAL_ID, catalog_shape_report, placeholder_catalog
from acop.domain import cents
from acop.economics import MerchantEconomics
from acop.interventions import release_0_set
from acop.mandates import build_mandate_set, render, segment_summary
from acop.pipeline import print_summary, run_pipeline

ROOT = Path(__file__).resolve().parent.parent


def demo_economics(focal_price_cents: int) -> MerchantEconomics:
    """ALL SYNTHETIC. Illustrative only — never call this merchant economics.

    Shaped for a mid-market DTC desk brand: ~$629 ASP, hardware gross margin
    around 45%, freight a large and real line item, meaningful return cost
    because the product weighs 100 lb.
    """
    return MerchantEconomics(
        annual_agent_comparison_events=52_000,
        annual_non_agent_orders=9_400,
        baseline_post_selection_conversion=0.55,
        cannibalization_rate=0.30,
        # The displaced order is the SAME product bought through another
        # channel, so its contribution cannot exceed the control-arm CM
        # (~$171). Setting it above that makes every incremental agent
        # order value-destroying by construction.
        displaced_channel_cm_cents=cents(171),
        cogs_cents=cents(305),
        fulfillment_cost_cents=cents(74),
        payment_bps=290,
        baseline_return_rate=0.06,
        return_cost_cents=cents(210),
        conversion_prior=(0.42, 0.68),
        cannibalization_prior=(0.0, 0.55),
        elasticity_prior=(0.0, 1.5),
    )


def main() -> None:
    catalog = placeholder_catalog()
    focal = next(p for p in catalog if p.product_id == PLACEHOLDER_FOCAL_ID)

    shape = catalog_shape_report(catalog)
    print("\n  CATALOG SHAPE CHECK (run this on your real fixture too)")
    for k, v in shape.items():
        if k != "warnings":
            print(f"    {k:<26} {v}")
    for w in shape["warnings"]:
        print(f"    WARNING: {w}")

    mandates = build_mandate_set(n=150)
    print("\n  MANDATE SEGMENTS")
    for seg, n in segment_summary(mandates).items():
        print(f"    {seg:<26} {n}")
    print("\n  SAMPLE MANDATES")
    for m in mandates[:3]:
        for t in range(3):
            print(f"    [{m.mandate_id} t{t}] {render(m, t)}")
        print()

    out = run_pipeline(
        experiment_id="sim_desk_release0_001",
        catalog=catalog,
        focal_product_id=PLACEHOLDER_FOCAL_ID,
        mandates=mandates,
        arms=release_0_set(focal),
        merchant_economics=demo_economics(focal.price_cents),
        adapter=SimulatedAgentAdapter(temperature=1.0, position_bias=True),
        artifacts_dir=ROOT / "artifacts",
        replications=3,
        prompt_variants=3,
        evidence_class="E0_SYNTHETIC_SYSTEM_CHECK",
    )
    print_summary(out)


if __name__ == "__main__":
    main()
