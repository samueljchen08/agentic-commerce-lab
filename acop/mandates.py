"""Buyer mandate population — standing desks.

Segments are built from how the category is actually shopped, not from generic
persona templates. Three structural facts drive the design:

1. **Several constraints are genuinely hard.** Height range, weight capacity,
   and desktop width eliminate products outright rather than merely
   disfavouring them. This is what makes agent choice measurable: without hard
   constraints every mandate converges on the same "best" desk and there is no
   variance to explain.

2. **Lead times are long and vary enormously** — 2 days to 8 weeks across
   brands. Urgency is therefore a real discriminator, which is what gives the
   delivery-SLA lever something to bite into.

3. **Returns are expensive.** A 100 lb desk costs $150+ in return freight, so
   return terms are a genuine commercial lever, not a footnote.

Population weights are informed estimates, not measured data. They are tagged
SYNTHETIC in the assumptions ledger and should be replaced with merchant search
and support data at the first opportunity.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass

from .domain import BuyerMandate, Constraint, cents

CATEGORY = "standing_desk"


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    population_weight: float
    use_case: str
    # relative importance across the attributes an agent can actually reason over
    weights: dict[str, float]
    # constraints that are HARD for this segment (eliminate products)
    hard_constraints: tuple[tuple[str, str, float], ...] = ()
    # constraints that are preferences (disfavour but do not eliminate)
    soft_constraints: tuple[tuple[str, str, float], ...] = ()


SEGMENTS: tuple[Segment, ...] = (
    Segment(
        key="budget_first_desk",
        label="First standing desk, working from home",
        population_weight=0.30,
        use_case=(
            "working from a kitchen table or a cheap desk, back is starting to hurt, "
            "buying a first sit-stand desk"
        ),
        weights={"price": 0.42, "stability": 0.18, "footprint": 0.14,
                 "warranty": 0.10, "delivery_speed": 0.10, "aesthetics": 0.06},
    ),
    Segment(
        key="ergonomics_enthusiast",
        label="Researched buyer, knows the specs",
        population_weight=0.16,
        use_case=(
            "has read reviews and comparison threads, wants a dual-motor three-stage "
            "frame that does not wobble at standing height"
        ),
        weights={"stability": 0.30, "capacity": 0.20, "warranty": 0.20,
                 "height_range": 0.12, "price": 0.10, "noise": 0.08},
        soft_constraints=(("motors", ">=", 2), ("leg_stages", ">=", 3)),
    ),
    Segment(
        key="heavy_setup",
        label="Multi-monitor or gaming setup",
        population_weight=0.13,
        use_case=(
            "running three monitors, a tower and an audio interface, needs the desk "
            "to actually hold the weight without sagging or straining the motors"
        ),
        weights={"capacity": 0.38, "stability": 0.26, "price": 0.14,
                 "warranty": 0.12, "footprint": 0.10},
        hard_constraints=(("weight_capacity_lb", ">=", 250),),
    ),
    Segment(
        key="small_space",
        label="Apartment or shared room, space constrained",
        population_weight=0.15,
        use_case=(
            "fitting a desk into a small apartment or a corner of a shared room, "
            "the wall space available is fixed"
        ),
        weights={"footprint": 0.36, "price": 0.26, "aesthetics": 0.16,
                 "stability": 0.12, "delivery_speed": 0.10},
        hard_constraints=(("width_in", "<=", 48),),
    ),
    Segment(
        key="height_outlier",
        label="Unusually tall or short user",
        population_weight=0.09,
        use_case=(
            "taller than most desks are built for, standard sit-stand desks do not "
            "raise high enough to stand comfortably"
        ),
        weights={"height_range": 0.40, "stability": 0.22, "capacity": 0.14,
                 "price": 0.14, "warranty": 0.10},
        # 50.5in, not 51in. Against the real catalog a 51in threshold is met by
        # exactly one desk, which would make that product the forced answer for
        # this entire segment and inflate its baseline. Real frame heights top
        # out around 50.5-50.9. This threshold was corrected by sourced data.
        hard_constraints=(("height_max_in", ">=", 50.5),),
    ),
    Segment(
        key="design_led",
        label="Desk is visible, looks matter",
        population_weight=0.10,
        use_case=(
            "the desk sits in a studio apartment and appears on video calls, so the "
            "top material and cable management matter as much as the mechanism"
        ),
        weights={"aesthetics": 0.34, "footprint": 0.18, "stability": 0.16,
                 "warranty": 0.12, "noise": 0.10, "price": 0.10},
    ),
    Segment(
        key="burned_replacement",
        label="Replacing a desk that failed",
        population_weight=0.07,
        use_case=(
            "the last standing desk failed inside two years — motor died or the frame "
            "developed a wobble — and this one needs to last"
        ),
        weights={"warranty": 0.36, "stability": 0.26, "capacity": 0.14,
                 "price": 0.14, "delivery_speed": 0.10},
        soft_constraints=(("warranty_years", ">=", 7),),
    ),
)

# Budget bands reflect real price tiers in the category.
BUDGET_BANDS: tuple[tuple[int | None, float, str], ...] = (
    (40_000, 0.00, "tight"),      # entry frames
    (65_000, 0.15, "mid"),        # the volume band
    (95_000, 0.25, "premium"),    # dual-motor, better tops
    (140_000, 0.40, "open"),      # solid wood / contract grade
)

# Lead times here run 2 days to 8 weeks, so urgency genuinely discriminates.
URGENCY: tuple[tuple[int | None, str], ...] = (
    (None, "none"),
    (28, "flexible"),
    (10, "soon"),
    (4, "urgent"),
)

_TEMPLATES = (
    # plain, how someone actually types it
    "{use_case_sentence} {budget} {urgency} {constraints} Which one should I get?",
    # context-first
    "Looking for a sit-stand desk. {use_case_sentence} {constraints} {budget} {urgency}",
    # constraint-first, the way a researched buyer writes
    "{constraints} {use_case_sentence} {budget} {urgency} What would you recommend?",
)


def _budget_phrase(budget_cents: int, band: str) -> str:
    dollars = budget_cents // 100
    return {
        "tight": f"I really can't go over ${dollars}.",
        "mid": f"Trying to stay around ${dollars}.",
        "premium": f"Budget is up to about ${dollars}.",
        "open": f"I can spend up to ${dollars} if it's worth it.",
    }[band]


def _urgency_phrase(days: int | None, band: str) -> str:
    return {
        "none": "",
        "flexible": "No particular rush on delivery.",
        "soon": f"I'd like it within about {days} days.",
        "urgent": f"I need it delivered within {days} days.",
    }[band]


def _constraint_phrase(c: Constraint) -> str:
    v = c.value
    return {
        "weight_capacity_lb": f"it has to hold at least {int(v)} lb",
        "width_in": f"the top can't be wider than {int(v)} inches",
        "height_max_in": f"it needs to raise to at least {v} inches",
        "height_min_in": f"it needs to go down to {v} inches or lower",
        "motors": "I want a dual-motor frame",
        "leg_stages": "three-stage legs preferably",
        "warranty_years": f"at least a {int(v)}-year warranty",
    }.get(c.field, "")


def build_mandate_set(n: int = 150, seed: int = 7) -> list[BuyerMandate]:
    """Stratified across segment x budget x urgency, then filled to n.

    Stratification matters more than raw count: a set of 150 covering every
    cell beats 400 clustered in one segment, because the paired estimator
    clusters on mandate and correlated mandates buy almost no information.
    """
    rng = random.Random(seed)
    strata = list(itertools.product(range(len(SEGMENTS)), range(len(BUDGET_BANDS)), range(len(URGENCY))))
    rng.shuffle(strata)

    mandates: list[BuyerMandate] = []
    i = 0
    while len(mandates) < n:
        s_i, b_i, u_i = strata[i % len(strata)]
        i += 1
        seg = SEGMENTS[s_i]
        budget_cents, softness, band = BUDGET_BANDS[b_i]
        need_by, u_band = URGENCY[u_i]

        constraints: list[Constraint] = [
            Constraint(field=f, op=op, value=v, hard=True) for f, op, v in seg.hard_constraints
        ]
        # soft constraints appear on roughly half of mandates in the segment,
        # so the segment is not perfectly collinear with a single attribute
        for f, op, v in seg.soft_constraints:
            if rng.random() < 0.55:
                constraints.append(Constraint(field=f, op=op, value=v, hard=False))

        # a minority of every segment cares about a quiet motor
        if rng.random() < 0.18:
            constraints.append(Constraint(field="noise_db", op="<=", value=50, hard=False))

        mandates.append(
            BuyerMandate(
                mandate_id=f"m_{len(mandates):04d}",
                category=CATEGORY,
                segment=seg.key,
                budget_max_cents=budget_cents,
                budget_softness=softness,
                use_case=seg.use_case,
                constraints=constraints,
                preference_weights=dict(seg.weights),
                need_by_days=need_by,
                population_weight=seg.population_weight / (len(BUDGET_BANDS) * len(URGENCY)),
                source="synthetic",
            )
        )
    return mandates


def render(m: BuyerMandate, template_index: int = 0) -> str:
    """Deterministic natural-language rendering.

    Never leaks preference_weights — rendering the weights would tell the agent
    the answer and the measured effect would be an artifact of the prompt.
    """
    band = next((b for c, _, b in BUDGET_BANDS if c == m.budget_max_cents), "mid")
    budget = _budget_phrase(m.budget_max_cents, band) if m.budget_max_cents else ""

    u_band = next((b for d, b in URGENCY if d == m.need_by_days), "none")
    urgency = _urgency_phrase(m.need_by_days, u_band)

    phrases = [p for p in (_constraint_phrase(c) for c in m.constraints) if p]
    if phrases:
        joined = phrases[0] if len(phrases) == 1 else ", and ".join(
            [", ".join(phrases[:-1]), phrases[-1]]
        )
        constraints = joined[0].upper() + joined[1:] + "."
    else:
        constraints = ""

    use_case_sentence = m.use_case[0].upper() + m.use_case[1:] + "."

    text = _TEMPLATES[template_index % len(_TEMPLATES)].format(
        use_case_sentence=use_case_sentence,
        budget=budget,
        urgency=urgency,
        constraints=constraints,
    )
    return " ".join(text.split())


def normalized_population_weights(mandates: list[BuyerMandate]) -> dict[str, float]:
    total = sum(m.population_weight for m in mandates)
    return {m.mandate_id: m.population_weight / total for m in mandates}


def segment_summary(mandates: list[BuyerMandate]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in mandates:
        out[m.segment] = out.get(m.segment, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
