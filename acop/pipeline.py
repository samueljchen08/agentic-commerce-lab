"""The pipeline. One function, adapter-agnostic.

    catalog + mandates + arms + adapter
        -> probes -> raw artifacts -> choice records
        -> paired effects (mandate-clustered posterior)
        -> economics bridge -> ranked actions
        -> artifacts/ + manifest

The simulated oracle and a real provider run through exactly this path, which
is what makes free structural debugging possible: everything except the
adapter is identical.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np

from .adapters.base import BuyerSurfaceAdapter
from .domain import BuyerMandate, ProductState
from .economics import (
    ActionResult,
    InterventionEconomics,
    MerchantEconomics,
    classify,
    do_nothing,
    rank,
)
from .economics import evaluate_action as eval_econ
from .experiment import Arm as ExpArm
from .experiment import ExperimentDefinition, apply_intervention, run_experiment
from .interventions import Arm
from .manifest import ArtifactStore, RunManifest, content_hash
from .stats import estimate_effect, position_effect, prompt_sensitivity, validity_report


def run_pipeline(
    *,
    experiment_id: str,
    catalog: list[ProductState],
    focal_product_id: str,
    mandates: list[BuyerMandate],
    arms: list[Arm],
    merchant_economics: MerchantEconomics,
    adapter: BuyerSurfaceAdapter,
    artifacts_dir: Path,
    replications: int = 1,
    prompt_variants: int = 1,
    evidence_class: str = "E0_SYNTHETIC_SYSTEM_CHECK",
    seed: int = 42,
    progress: bool = True,
) -> dict:
    store = ArtifactStore(artifacts_dir)
    focal = next(p for p in catalog if p.product_id == focal_product_id)
    econ_by_id: dict[str, InterventionEconomics] = {iv.intervention_id: ie for iv, ie in arms}

    manifest = RunManifest(
        experiment_id=experiment_id,
        evidence_class=evidence_class,
        catalog_hash=content_hash([p.model_dump() for p in catalog]),
        mandate_set_hash=content_hash([m.model_dump() for m in mandates]),
        intervention_versions={iv.intervention_id: iv.type.value for iv, _ in arms},
        adapter_name=adapter.name,
        adapter_version=adapter.version,
        randomization_seed=seed,
        replications=replications,
        prompt_template_variants=prompt_variants,
        n_mandates=len(mandates),
        n_arms=len(arms) + 1,
    )

    defn = ExperimentDefinition(
        experiment_id=experiment_id,
        hypothesis="Which merchant-controlled lever most raises agent selection of the focal product?",
        primary_outcome="selected",
        focal_product_id=focal_product_id,
        arms=[ExpArm("control", "Baseline")]
        + [ExpArm(iv.intervention_id, iv.label, iv) for iv, _ in arms],
        replications=replications,
        randomize_positions=True,
        prompt_template_variants=prompt_variants,
        seed=seed,
    )

    mandates_by_id = {m.mandate_id: m for m in mandates}
    manifest.n_cells = len(mandates) * replications * (len(arms) + 1)
    if progress:
        print(f"  dispatching {manifest.n_cells:,} probes via {adapter.name}...")

    run = run_experiment(defn, catalog, mandates_by_id, adapter, progress=progress)

    # ---- provenance from whichever adapter ran
    sample = next(iter(run.records.values()))
    manifest.provider_name = sample.provider_name
    manifest.model_id = sample.model_id
    manifest.parser_version = sample.parser_version
    manifest.prompt_version = sample.prompt_version
    manifest.probes_completed = len(run.records)
    if hasattr(adapter, "usage_summary"):
        u = adapter.usage_summary()
        manifest.input_tokens = u.get("input_tokens", 0)
        manifest.output_tokens = u.get("output_tokens", 0)
        manifest.estimated_cost_usd = u.get("estimated_cost_usd", 0.0)
        manifest.probes_failed = u.get("failures", 0)

    # ---- diagnostics
    validity = validity_report(run)
    positions = position_effect(run)

    # ---- effects
    rng = np.random.default_rng(seed + 1)
    estimates = {}
    for iv, _ in arms:
        estimates[iv.intervention_id] = estimate_effect(
            run, "control", iv.intervention_id, iv.label, rng=rng
        )
    # Control-only (smoke) runs have zero arms. Baseline diagnostics — selection
    # rate, ICC, effective n — must still be reportable, so fall back to a
    # control-vs-control comparison purely for those shared fields.
    any_e = next(iter(estimates.values())) if estimates else estimate_effect(
        run, "control", "control", "control", rng=rng
    )

    top_id = max(estimates, key=lambda k: estimates[k].effect_pp) if estimates else None
    sensitivity = (
        prompt_sensitivity(run, "control", top_id) if prompt_variants > 1 and top_id else {}
    )

    # ---- economics
    actions: list[ActionResult] = [do_nothing()]
    for iv, ie in arms:
        treated_catalog = apply_intervention(catalog, iv)
        treated = next(p for p in treated_catalog if p.product_id == focal_product_id)
        e = estimates[iv.intervention_id]
        result = eval_econ(
            iv, ie, focal, treated, merchant_economics, e.posterior, e.control_rate, rng
        )
        actions.append(classify(result, ie))
    ranked = rank(actions)

    # ---- persist
    store.write_jsonl(
        "choices.jsonl",
        [
            {**run.records[c.cell_id].model_dump(), "arm_id": c.arm_id,
             "mandate_id": c.mandate_id, "replication_no": c.replication_no,
             "pair_id": c.pair_id}
            for c in run.cells
        ],
    )
    store.write_json(
        "effects.json",
        {
            "control_selection_rate": round(any_e.control_rate, 5),
            "icc": round(any_e.icc, 4),
            "design_effect": round(any_e.design_effect, 3),
            "probes_per_arm": any_e.n_probes_per_arm,
            "effective_n": round(any_e.effective_n, 1),
            "n_mandates": any_e.n_mandates,
            "validity": validity,
            "position_diagnostic": positions,
            "prompt_sensitivity": {str(k): round(v, 4) for k, v in sensitivity.items()},
            "effects": [
                {
                    "intervention_id": k,
                    "label": e.label,
                    "effect_pp": round(e.effect_pp, 5),
                    "ci90": [round(e.ci90[0], 5), round(e.ci90[1], 5)],
                    "ci95": [round(e.ci95[0], 5), round(e.ci95[1], 5)],
                    "p_positive": round(e.p_positive, 4),
                }
                for k, e in estimates.items()
            ],
        },
    )
    store.write_json(
        "economics.json",
        {
            "merchant_economics": asdict(merchant_economics)
            if hasattr(merchant_economics, "__dataclass_fields__")
            else merchant_economics.__dict__,
            "assumptions_ledger": [asdict(x) for x in merchant_economics.ledger()],
            "actions": [
                {
                    **{k: v for k, v in asdict(a).items() if k != "breakevens"},
                    "channel_scope": a.channel_scope.value,
                    "status": a.status.value,
                    "operational_requirements": list(
                        econ_by_id[a.intervention_id].operational_requirements
                    )
                    if a.intervention_id in econ_by_id
                    else [],
                }
                for a in ranked
            ],
        },
    )
    manifest.finish()
    store.write_json("run_manifest.json", manifest.to_dict())

    return {
        "manifest": manifest,
        "estimates": estimates,
        "actions": ranked,
        "validity": validity,
        "positions": positions,
        "prompt_sensitivity": sensitivity,
        "artifacts_dir": str(artifacts_dir),
    }


def print_summary(out: dict) -> None:
    m = out["manifest"]
    print("\n" + "=" * 78)
    print(f"  {m.experiment_id}   [{m.evidence_class}]")
    print("=" * 78)
    print(f"  provider {m.provider_name} / {m.model_id}")
    print(f"  {m.n_mandates} mandates x {m.replications} reps x {m.n_arms} arms "
          f"= {m.n_cells:,} probes")
    if m.estimated_cost_usd:
        print(f"  cost ${m.estimated_cost_usd:.2f}  "
              f"({m.input_tokens:,} in / {m.output_tokens:,} out tokens)")

    print("\n  SELECTION EFFECTS")
    for e in out["estimates"].values():
        print(f"    {e.label:<48} {e.effect_pp*100:+6.2f} pp "
              f"[{e.ci95[0]*100:+6.2f}, {e.ci95[1]*100:+6.2f}]  P(>0)={e.p_positive:.3f}")
    any_e = next(iter(out["estimates"].values()))
    print(f"\n    baseline selection rate : {any_e.control_rate:.3f}")
    print(f"    ICC / design effect     : {any_e.icc:.3f} / {any_e.design_effect:.2f}")
    print(f"    effective n per arm     : {any_e.effective_n:,.0f} "
          f"(of {any_e.n_probes_per_arm:,} probes)")

    print("\n  RANKED ACTIONS  (modeled contribution, all channels)")
    for a in out["actions"]:
        print(f"    [{a.status.value:<22}] {a.label:<46} "
              f"${a.delta_total_cents/100:>12,.0f}")
        if a.intervention_id != "int_do_nothing":
            print(f"         agent gain ${a.agent_channel_gain_cents/100:,.0f}"
                  f"  cannibalized ${a.cannibalization_cents/100:,.0f}"
                  f"  non-agent ${a.non_agent_effect_cents/100:,.0f}"
                  f"  P(>0) {a.p_profit_positive:.2f}")
    print(f"\n  artifacts -> {out['artifacts_dir']}\n")
