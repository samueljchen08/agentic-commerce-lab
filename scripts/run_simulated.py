"""Full loop on the simulated oracle. Free, no API calls, seconds to run.

This is E0: it proves the SOFTWARE behaves correctly under known assumptions.
It says nothing about how a real model behaves. Use it for every structural
change, every economics change, and all report development.
"""
from __future__ import annotations

from pathlib import Path

from acop._seed_catalog import MERCHANT_PRODUCT_ID, build_catalog, merchant_economics
from acop.adapters import SimulatedAgentAdapter
from acop.domain import cents
from acop.economics import MerchantEconomics
from acop.interventions import release_0_set
from acop.mandates import build_mandate_set
from acop.pipeline import print_summary, run_pipeline

ROOT = Path(__file__).resolve().parent.parent


def demo_economics() -> MerchantEconomics:
    """ALL SYNTHETIC. Illustrative only — never call this merchant economics."""
    return MerchantEconomics(
        annual_agent_comparison_events=38_000,
        annual_non_agent_orders=13_800,
        baseline_post_selection_conversion=0.60,
        cannibalization_rate=0.30,
        displaced_channel_cm_cents=cents(96),
        cogs_cents=cents(148),
        fulfillment_cost_cents=cents(41),
        payment_bps=290,
        baseline_return_rate=0.09,
        return_cost_cents=cents(22),
        conversion_prior=(0.45, 0.75),
        cannibalization_prior=(0.0, 0.55),
        elasticity_prior=(0.0, 1.5),
    )


def main() -> None:
    catalog = build_catalog()
    focal = next(p for p in catalog if p.product_id == MERCHANT_PRODUCT_ID)
    out = run_pipeline(
        experiment_id="sim_release0_001",
        catalog=catalog,
        focal_product_id=MERCHANT_PRODUCT_ID,
        mandates=build_mandate_set(n=150),
        arms=release_0_set(focal),
        merchant_economics=demo_economics(),
        adapter=SimulatedAgentAdapter(temperature=1.0, position_bias=True),
        artifacts_dir=ROOT / "artifacts",
        replications=3,
        prompt_variants=3,
        evidence_class="E0_SYNTHETIC_SYSTEM_CHECK",
    )
    print_summary(out)


if __name__ == "__main__":
    main()
