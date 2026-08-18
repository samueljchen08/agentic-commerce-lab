"""Experiment engine.

Invariants enforced here:
  * treatment arms differ from control ONLY in declared fields (checked)
  * every (mandate, replication) is evaluated under every arm -> paired design
  * candidate presentation order is randomized per pair and held constant
    across arms within that pair, so position is balanced but not confounded
  * execution order is shuffled so provider drift cannot favour one arm
"""
from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import dataclass, field

from .adapters.base import BuyerSurfaceAdapter, ProbeRequest
from .domain import ChoiceRecord, ExperimentCell, Intervention, InterventionType, ProductState


class UndeclaredTreatmentDiff(Exception):
    pass


# ----------------------------------------------------------------- arms


@dataclass
class Arm:
    arm_id: str
    label: str
    intervention: Intervention | None = None   # None == control


def apply_intervention(
    catalog: list[ProductState], intervention: Intervention | None
) -> list[ProductState]:
    """Apply a declared patch. Returns a new catalog; never mutates the input."""
    out = [p.model_copy(deep=True) for p in catalog]
    if intervention is None:
        return out

    targets = set(intervention.target_product_ids)
    for p in out:
        if p.product_id not in targets:
            continue
        for path, value in intervention.patch.items():
            obj, *rest = path.split(".")
            if rest:
                sub = getattr(p, obj)
                setattr(sub, rest[0], value)
            else:
                setattr(p, obj, value)
    return out


def declared_paths(intervention: Intervention | None) -> set[tuple[str, str]]:
    if intervention is None:
        return set()
    return {(pid, path) for pid in intervention.target_product_ids for path in intervention.patch}


def assert_only_declared_changes(
    control: list[ProductState], treated: list[ProductState], intervention: Intervention | None
) -> None:
    """P0-13. The single most important validity guard in the system:
    if an arm differs in an undeclared field, the measured effect is garbage."""
    allowed = declared_paths(intervention)
    c_by_id = {p.product_id: p for p in control}

    for t in treated:
        c = c_by_id[t.product_id]
        cd, td = c.model_dump(), t.model_dump()
        for key in cd:
            if isinstance(cd[key], dict):
                for sub in cd[key]:
                    if cd[key][sub] != td[key][sub] and (t.product_id, f"{key}.{sub}") not in allowed:
                        raise UndeclaredTreatmentDiff(
                            f"{t.product_id}.{key}.{sub}: {cd[key][sub]!r} -> {td[key][sub]!r}"
                        )
            elif cd[key] != td[key] and (t.product_id, key) not in allowed:
                raise UndeclaredTreatmentDiff(f"{t.product_id}.{key}: {cd[key]!r} -> {td[key]!r}")


# ----------------------------------------------------------------- design


@dataclass
class ExperimentDefinition:
    experiment_id: str
    hypothesis: str
    primary_outcome: str          # "selected" | "considered" | "ranked_top3"
    focal_product_id: str
    arms: list[Arm]
    replications: int = 3
    randomize_positions: bool = True
    seed: int = 42
    prompt_template_variants: int = 3   # measures prompt sensitivity


@dataclass
class ExperimentRun:
    definition: ExperimentDefinition
    cells: list[ExperimentCell] = field(default_factory=list)
    records: dict[str, ChoiceRecord] = field(default_factory=dict)


def build_cells(defn: ExperimentDefinition, mandate_ids: list[str]) -> list[ExperimentCell]:
    rng = random.Random(defn.seed)
    cells: list[ExperimentCell] = []
    order = 0
    for mid in mandate_ids:
        for rep in range(defn.replications):
            pair_id = hashlib.sha1(f"{defn.experiment_id}|{mid}|{rep}".encode()).hexdigest()[:12]
            # One position seed per PAIR: candidate order is identical across
            # arms within a pair, so position cannot confound the contrast,
            # but varies across pairs so it is balanced overall.
            pos_seed = rng.randrange(1 << 30)
            for arm in defn.arms:
                cells.append(
                    ExperimentCell(
                        cell_id=f"{defn.experiment_id}:{arm.arm_id}:{mid}:{rep}",
                        experiment_id=defn.experiment_id,
                        arm_id=arm.arm_id,
                        mandate_id=mid,
                        replication_no=rep,
                        pair_id=pair_id,
                        position_seed=pos_seed,
                        randomized_order=order,
                    )
                )
                order += 1
    rng.shuffle(cells)
    for i, c in enumerate(cells):
        c.randomized_order = i
    return cells


def present(catalog: list[ProductState], position_seed: int, randomize: bool) -> list[ProductState]:
    if not randomize:
        return list(catalog)
    shuffled = list(catalog)
    random.Random(position_seed).shuffle(shuffled)
    return shuffled


def run_experiment(
    defn: ExperimentDefinition,
    catalog: list[ProductState],
    mandates_by_id: dict,
    adapter: BuyerSurfaceAdapter,
    progress: bool = False,
) -> ExperimentRun:
    arms_by_id = {a.arm_id: a for a in defn.arms}

    # Freeze one materialized catalog per arm, and validate the diff up front.
    control_arm = next(a for a in defn.arms if a.intervention is None)
    control_catalog = apply_intervention(catalog, None)
    arm_catalogs: dict[str, list[ProductState]] = {control_arm.arm_id: control_catalog}
    for arm in defn.arms:
        if arm.arm_id == control_arm.arm_id:
            continue
        treated = apply_intervention(catalog, arm.intervention)
        assert_only_declared_changes(control_catalog, treated, arm.intervention)
        arm_catalogs[arm.arm_id] = treated

    cells = build_cells(defn, list(mandates_by_id.keys()))
    run = ExperimentRun(definition=defn, cells=cells)

    for i, cell in enumerate(cells):
        arm = arms_by_id[cell.arm_id]
        ordered = present(arm_catalogs[cell.arm_id], cell.position_seed, defn.randomize_positions)
        template_index = (
            int(hashlib.sha1(cell.pair_id.encode()).hexdigest(), 16) % defn.prompt_template_variants
        )
        req = ProbeRequest(
            probe_id=f"pr_{cell.cell_id}",
            cell_id=cell.cell_id,
            mandate=mandates_by_id[cell.mandate_id],
            candidates=ordered,
            template_index=template_index,
            # seed varies by cell so replications are genuinely stochastic
            seed=int(hashlib.sha1(cell.cell_id.encode()).hexdigest()[:8], 16),
        )
        run.records[cell.cell_id] = adapter.run(req)
        if progress and i % 500 == 0:
            print(f"    ... {i}/{len(cells)} probes", flush=True)
    return run


# ------------------------------------------------------------- outcomes


def outcome_value(rec: ChoiceRecord, outcome: str, focal: str) -> int:
    if outcome == "selected":
        return int(rec.selected_product_id == focal)
    if outcome == "considered":
        return int(focal in rec.considered_product_ids)
    if outcome == "ranked_top3":
        return int(focal in rec.ranked_product_ids[:3])
    raise ValueError(outcome)


# ---------------------------------------------------------- interventions


def enumerate_interventions(focal: ProductState) -> list[Intervention]:
    """Merchant-approved grid. An LLM never invents price points here.

    `channel_isolable` marks whether the lever can be applied to agent
    surfaces only (feed / structured data) or hits every channel.
    """
    out: list[Intervention] = []

    for pct in (5, 10):
        new_price = int(round(focal.price_cents * (100 - pct) / 100, -2))
        out.append(
            Intervention(
                intervention_id=f"int_price_{pct}",
                type=InterventionType.PRICE,
                label=f"Cut list price {pct}% (${new_price/100:.0f})",
                target_product_ids=[focal.product_id],
                patch={"price_cents": new_price},
                channel_isolable=False,
                risk_level="medium" if pct == 5 else "high",
            )
        )

    out.append(
        Intervention(
            intervention_id="int_free_standard",
            type=InterventionType.SHIPPING,
            label="Free standard shipping",
            target_product_ids=[focal.product_id],
            patch={"shipping.price_cents": 0},
            channel_isolable=False,
            direct_cost_cents_per_order=focal.shipping.price_cents,
        )
    )
    out.append(
        Intervention(
            intervention_id="int_free_expedited",
            type=InterventionType.SHIPPING,
            label="Free expedited shipping (2 days)",
            target_product_ids=[focal.product_id],
            patch={"shipping.price_cents": 0, "shipping.eta_min_days": 1, "shipping.eta_max_days": 2},
            channel_isolable=False,
            direct_cost_cents_per_order=focal.shipping.price_cents + 900,
        )
    )
    out.append(
        Intervention(
            intervention_id="int_agent_expedited_sla",
            type=InterventionType.SHIPPING,
            label="Publish 2-day SLA to agent feeds only",
            target_product_ids=[focal.product_id],
            patch={"shipping.eta_min_days": 1, "shipping.eta_max_days": 2},
            channel_isolable=True,
            direct_cost_cents_per_order=900,
        )
    )
    out.append(
        Intervention(
            intervention_id="int_warranty_120",
            type=InterventionType.WARRANTY,
            label="Extend warranty to 10 years",
            target_product_ids=[focal.product_id],
            patch={"warranty.duration_months": 120},
            channel_isolable=False,
            direct_cost_cents_per_order=650,
        )
    )
    out.append(
        Intervention(
            intervention_id="int_returns_60",
            type=InterventionType.RETURNS,
            label="Extend return window to 60 days",
            target_product_ids=[focal.product_id],
            patch={"returns.window_days": 60},
            channel_isolable=False,
        )
    )
    out.append(
        Intervention(
            intervention_id="int_feed_attributes",
            type=InterventionType.ATTRIBUTE_DATA,
            label="Complete structured attributes in agent feed",
            target_product_ids=[focal.product_id],
            patch={"attributes": {**focal.attributes, "weight_lb": focal.attributes["weight_lb"]}},
            channel_isolable=True,
            direct_cost_cents_per_order=0,
            risk_level="low",
        )
    )
    return out
