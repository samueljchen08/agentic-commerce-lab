"""Buyer mandate population.

Mandates are structured objects first, natural language second. The renderer
is deterministic given (mandate_id, template_index) so an experiment is
reproducible. preference_weights are held back from the rendered text.
"""
from __future__ import annotations

import itertools
import random

from .domain import BuyerMandate, Constraint, cents

SEGMENTS = {
    "business_frequent": dict(
        use_case="frequent short business trips, mostly overhead bin",
        weights={"durability": 0.30, "weight": 0.25, "delivery_speed": 0.20, "price": 0.15, "aesthetics": 0.10},
        pop=0.24,
    ),
    "leisure_value": dict(
        use_case="two or three leisure trips a year with family",
        weights={"price": 0.45, "capacity": 0.20, "durability": 0.20, "weight": 0.10, "delivery_speed": 0.05},
        pop=0.31,
    ),
    "premium_design": dict(
        use_case="wants a piece that looks and feels premium",
        weights={"aesthetics": 0.35, "durability": 0.25, "warranty": 0.20, "weight": 0.15, "price": 0.05},
        pop=0.14,
    ),
    "urgent_replacement": dict(
        use_case="current bag broke, travelling again very soon",
        weights={"delivery_speed": 0.45, "price": 0.20, "durability": 0.20, "capacity": 0.15},
        pop=0.16,
    ),
    "warranty_seeker": dict(
        use_case="burned by a bag that failed, wants long-term coverage",
        weights={"warranty": 0.40, "durability": 0.30, "price": 0.20, "weight": 0.10},
        pop=0.15,
    ),
}

BUDGET_BANDS = [
    (None, 17500, 0.0),
    (None, 25000, 0.15),
    (None, 32500, 0.25),
    (None, 45000, 0.40),
]

URGENCY = [None, 14, 5, 2]

_TEMPLATES = [
    "I need {use_case}. {budget} {urgency} {constraint} What should I buy?",
    "Looking for a carry-on. Context: {use_case}. {budget} {urgency} {constraint}",
    "Help me pick a cabin bag — {use_case}. {budget} {urgency} {constraint}",
]


def build_mandate_set(n: int = 240, seed: int = 7) -> list[BuyerMandate]:
    """Stratified across segment x budget x urgency, then filled to n."""
    rng = random.Random(seed)
    strata = list(itertools.product(SEGMENTS.keys(), range(len(BUDGET_BANDS)), range(len(URGENCY))))
    rng.shuffle(strata)

    mandates: list[BuyerMandate] = []
    i = 0
    while len(mandates) < n:
        seg, b_i, u_i = strata[i % len(strata)]
        i += 1
        spec = SEGMENTS[seg]
        _, bmax, softness = BUDGET_BANDS[b_i]
        need_by = URGENCY[u_i]

        constraints: list[Constraint] = []
        if seg in ("business_frequent", "premium_design") and rng.random() < 0.45:
            constraints.append(Constraint(field="weight_lb", op="<=", value=8.0, hard=False))
        if seg == "leisure_value" and rng.random() < 0.35:
            constraints.append(Constraint(field="capacity_l", op=">=", value=38.0, hard=False))
        if rng.random() < 0.30:
            constraints.append(Constraint(field="tsa_lock", op="==", value=True, hard=False))

        mandates.append(
            BuyerMandate(
                mandate_id=f"m_{len(mandates):04d}",
                category="carry_on_luggage",
                segment=seg,
                budget_max_cents=bmax,
                budget_softness=softness,
                use_case=str(spec["use_case"]),
                constraints=constraints,
                preference_weights=dict(spec["weights"]),  # type: ignore[arg-type]
                need_by_days=need_by,
                population_weight=float(spec["pop"]) / (len(BUDGET_BANDS) * len(URGENCY)),
            )
        )
    return mandates


def render(m: BuyerMandate, template_index: int = 0) -> str:
    """Deterministic natural-language rendering. Never leaks preference_weights."""
    budget = f"My budget is up to ${m.budget_max_cents // 100}." if m.budget_max_cents else ""
    if m.need_by_days is None:
        urgency = ""
    elif m.need_by_days <= 2:
        urgency = "I need it delivered within two days."
    elif m.need_by_days <= 5:
        urgency = "I need it within about five days."
    else:
        urgency = "No real rush on delivery."

    parts = []
    for c in m.constraints:
        if c.field == "weight_lb":
            parts.append(f"it should be under {c.value} lb")
        elif c.field == "capacity_l":
            parts.append(f"at least {c.value} litres of packing space")
        elif c.field == "tsa_lock":
            parts.append("a TSA-approved lock matters to me")
    constraint = ("Also, " + ", and ".join(parts) + ".") if parts else ""

    return " ".join(
        _TEMPLATES[template_index % len(_TEMPLATES)]
        .format(use_case=m.use_case, budget=budget, urgency=urgency, constraint=constraint)
        .split()
    )


def normalized_population_weights(mandates: list[BuyerMandate]) -> dict[str, float]:
    total = sum(m.population_weight for m in mandates)
    return {m.mandate_id: m.population_weight / total for m in mandates}
