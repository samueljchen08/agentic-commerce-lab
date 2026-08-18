"""Treatment effect estimation.

Design: paired by (mandate, replication). Inference clusters on MANDATE, not
on individual probes -- replications within a mandate are strongly dependent
and treating them as independent overstates precision, often by 2-4x.

We use a Bayesian bootstrap (Dirichlet weights over mandate clusters). It
gives a genuine posterior over the effect, so:
  * P(effect > 0) is a real probability, not a p-value read backwards
  * optional stopping is valid -- you may look whenever you like
  * the posterior draws feed the economic optimizer directly, so the profit
    distribution and the effect distribution are coherent with each other

That last point matters: bolting a Monte Carlo profit simulation onto
frequentist bootstrap CIs produces numbers that look like probabilities but
are not.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .experiment import ExperimentRun, outcome_value


@dataclass
class ArmSummary:
    arm_id: str
    label: str
    n_probes: int
    rate: float


@dataclass
class EffectEstimate:
    arm_id: str
    label: str
    control_rate: float
    treatment_rate: float
    effect_pp: float                 # absolute difference in proportion
    ci90: tuple[float, float]
    ci95: tuple[float, float]
    p_positive: float
    posterior: np.ndarray            # draws, for downstream economics
    n_mandates: int
    n_probes_per_arm: int
    icc: float
    design_effect: float
    effective_n: float


def _mandate_matrix(run: ExperimentRun, arm_id: str) -> dict[str, list[int]]:
    defn = run.definition
    by_mandate: dict[str, list[int]] = {}
    for cell in run.cells:
        if cell.arm_id != arm_id:
            continue
        rec = run.records[cell.cell_id]
        y = outcome_value(rec, defn.primary_outcome, defn.focal_product_id)
        by_mandate.setdefault(cell.mandate_id, []).append(y)
    return by_mandate


def intraclass_correlation(by_mandate: dict[str, list[int]]) -> float:
    """One-way random effects ICC. Drives the design effect."""
    groups = [np.asarray(v, dtype=float) for v in by_mandate.values() if len(v) > 1]
    if not groups:
        return 0.0
    k = float(np.mean([len(g) for g in groups]))
    grand = np.mean(np.concatenate(groups))
    n = len(groups)
    msb = k * float(np.sum([(g.mean() - grand) ** 2 for g in groups])) / max(n - 1, 1)
    msw = float(np.sum([np.sum((g - g.mean()) ** 2) for g in groups])) / max(
        sum(len(g) for g in groups) - n, 1
    )
    if msb + (k - 1) * msw == 0:
        return 0.0
    return float(np.clip((msb - msw) / (msb + (k - 1) * msw), 0.0, 1.0))


def estimate_effect(
    run: ExperimentRun,
    control_arm_id: str,
    treatment_arm_id: str,
    label: str,
    draws: int = 4000,
    rng: np.random.Generator | None = None,
) -> EffectEstimate:
    rng = rng or np.random.default_rng(11)

    ctrl = _mandate_matrix(run, control_arm_id)
    trt = _mandate_matrix(run, treatment_arm_id)
    mandates = sorted(set(ctrl) & set(trt))

    c_rate = np.array([np.mean(ctrl[m]) for m in mandates])
    t_rate = np.array([np.mean(trt[m]) for m in mandates])

    # Bayesian bootstrap: Dirichlet(1,...,1) weights over mandate clusters.
    w = rng.dirichlet(np.ones(len(mandates)), size=draws)
    post_c = w @ c_rate
    post_t = w @ t_rate
    post_effect = post_t - post_c

    icc = intraclass_correlation(ctrl)
    k = float(np.mean([len(v) for v in ctrl.values()]))
    deff = 1.0 + (k - 1.0) * icc
    n_probes = int(sum(len(v) for v in ctrl.values()))

    return EffectEstimate(
        arm_id=treatment_arm_id,
        label=label,
        control_rate=float(c_rate.mean()),
        treatment_rate=float(t_rate.mean()),
        effect_pp=float(post_effect.mean()),
        ci90=(float(np.quantile(post_effect, 0.05)), float(np.quantile(post_effect, 0.95))),
        ci95=(float(np.quantile(post_effect, 0.025)), float(np.quantile(post_effect, 0.975))),
        p_positive=float((post_effect > 0).mean()),
        posterior=post_effect,
        n_mandates=len(mandates),
        n_probes_per_arm=n_probes,
        icc=icc,
        design_effect=deff,
        effective_n=n_probes / deff if deff > 0 else float(n_probes),
    )


# ------------------------------------------------------------ diagnostics


def position_effect(run: ExperimentRun) -> dict[str, float]:
    """Selection rate of the focal product by its presented rank.

    If this varies steeply, candidate order is a live confound and any design
    that does not balance position is measuring layout, not merchandising.
    """
    focal = run.definition.focal_product_id
    buckets: dict[int, list[int]] = {}
    for cell in run.cells:
        rec = run.records[cell.cell_id]
        if focal not in rec.presented_order:
            continue
        rank = rec.presented_order.index(focal)
        buckets.setdefault(rank // 5, []).append(int(rec.selected_product_id == focal))
    return {
        f"positions {b*5+1}-{b*5+5}": float(np.mean(v))
        for b, v in sorted(buckets.items())
    }


def prompt_sensitivity(run: ExperimentRun, control_arm_id: str, treatment_arm_id: str) -> dict[int, float]:
    """Effect estimated separately under each prompt phrasing.

    If the sign flips across templates, the instrument is measuring wording,
    not agent preference, and no downstream number is trustworthy.
    """
    import hashlib

    defn = run.definition
    variants = defn.prompt_template_variants
    acc: dict[int, dict[str, list[int]]] = {v: {"c": [], "t": []} for v in range(variants)}
    for cell in run.cells:
        v = int(hashlib.sha1(cell.pair_id.encode()).hexdigest(), 16) % variants
        y = outcome_value(run.records[cell.cell_id], defn.primary_outcome, defn.focal_product_id)
        if cell.arm_id == control_arm_id:
            acc[v]["c"].append(y)
        elif cell.arm_id == treatment_arm_id:
            acc[v]["t"].append(y)
    return {
        v: float(np.mean(d["t"]) - np.mean(d["c"]))
        for v, d in acc.items()
        if d["c"] and d["t"]
    }


def validity_report(run: ExperimentRun) -> dict[str, object]:
    arms: dict[str, int] = {}
    low_conf = 0
    unresolved = 0
    for cell in run.cells:
        arms[cell.arm_id] = arms.get(cell.arm_id, 0) + 1
        rec = run.records[cell.cell_id]
        if rec.parser_confidence < 0.8:
            low_conf += 1
        if rec.selected_product_id is None and not rec.abstained:
            unresolved += 1
    counts = list(arms.values())
    return {
        "balanced": max(counts) == min(counts),
        "cells_per_arm": arms,
        "low_confidence_parses": low_conf,
        "unresolved": unresolved,
        "parser_quality_pass": low_conf / max(len(run.cells), 1) < 0.02,
    }


def recover_known_effect(true_effect: float, n_mandates: int, reps: int, icc_target: float,
                         seed: int = 3, draws: int = 2000) -> tuple[float, bool]:
    """P0-18 acceptance test: simulate data with a KNOWN effect and a known
    cluster structure, and confirm the estimator recovers it with correct
    coverage. Returns (estimate, ci95_covers_truth)."""
    rng = np.random.default_rng(seed)
    base = rng.beta(2, 6, size=n_mandates)                     # mandate-level control rates
    base = np.clip(base * icc_target + 0.25 * (1 - icc_target), 0.01, 0.95)
    c = rng.binomial(reps, base) / reps
    t = rng.binomial(reps, np.clip(base + true_effect, 0.01, 0.99)) / reps
    w = rng.dirichlet(np.ones(n_mandates), size=draws)
    post = w @ t - w @ c
    lo, hi = np.quantile(post, [0.025, 0.975])
    return float(post.mean()), bool(lo <= true_effect <= hi)
