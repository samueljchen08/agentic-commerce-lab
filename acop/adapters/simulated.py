"""Simulated choice oracle — standing desks.

A latent-utility model with KNOWN coefficients. Its purpose is to validate the
machinery against ground truth we control -- NOT to imitate a real agent. A
number produced by this adapter is evidence class E0 and must always carry that
label in any output a human sees.

It deliberately encodes four pathologies so they stay visible during development:
  * free_shipping_salience -- responds to a boolean flag, not the dollar amount
  * position_bias          -- a layout confound larger than most real effects
  * mandate_taste          -- persistent per-(mandate, product) affinity, the
                              source of within-mandate correlation
  * hard constraints       -- eliminate products outright, as they do in reality
"""
from __future__ import annotations

import hashlib
import math
import random

from ..domain import BuyerMandate, ChoiceRecord, ProductState
from .base import ProbeRequest

TOP_APPEAL = {
    "solid_oak": 1.00, "solid_ash": 0.96, "bamboo": 0.72,
    "laminate": 0.34, "mdf": 0.20,
}

TRUE_COEFS = {
    "price": -3.4,
    "over_budget": -3.0,
    "delivery_speed": 2.1,
    "stability": 1.6,
    "capacity": 1.1,
    "height_range": 1.0,
    "footprint": 0.9,
    "aesthetics": 1.2,
    "warranty": 1.1,
    "noise": 0.5,
    "return_friction": -0.6,
    "free_shipping_salience": 0.40,
    "position_bias": 0.06,
    "mandate_taste": 0.85,
    "hard_violation": -4.5,
    "abstain_utility": -2.8,
}


class SimulatedAgentAdapter:
    name = "simulated_choice_oracle"
    version = "1.0.0-desk"

    def __init__(self, temperature: float = 1.0, position_bias: bool = True):
        self.temperature = temperature
        self.position_bias = position_bias

    @staticmethod
    def _violates_hard(m: BuyerMandate, p: ProductState) -> int:
        n = 0
        for c in m.constraints:
            if not c.hard:
                continue
            v = p.attributes.get(c.field)
            if v is None:
                continue
            v = float(v)
            t = float(c.value)
            if (c.op == ">=" and v < t) or (c.op == "<=" and v > t):
                n += 1
        return n

    @staticmethod
    def _features(m: BuyerMandate, p: ProductState, rank: int) -> dict[str, float]:
        a = p.attributes
        budget = m.budget_max_cents or 140_000
        landed = p.price_cents + p.shipping.price_cents
        price_ratio = landed / budget
        over = max(0.0, price_ratio - 1.0) * (1.0 - m.budget_softness)

        eta_mid = (p.shipping.eta_min_days + p.shipping.eta_max_days) / 2
        if m.need_by_days:
            speed = max(-1.0, min(1.0, (m.need_by_days - eta_mid) / max(m.need_by_days, 1)))
        else:
            speed = (21 - eta_mid) / 21 * 0.35

        motors = float(a.get("motors", 1))
        stages = float(a.get("leg_stages", 2))
        cap = float(a.get("weight_capacity_lb", 150))
        stability = (motors - 1.0) * 0.5 + (stages - 2.0) * 0.3 + min(cap, 400) / 400 * 0.4

        return {
            "price": price_ratio,
            "over_budget": over,
            "delivery_speed": speed,
            "stability": stability,
            "capacity": (cap - 130.0) / 270.0,
            "height_range": (float(a.get("height_max_in", 48)) - float(a.get("height_min_in", 28))) / 28.0,
            "footprint": (72.0 - float(a.get("width_in", 55))) / 32.0,
            "aesthetics": TOP_APPEAL.get(str(a.get("top_material", "laminate")), 0.3),
            "warranty": min(float(a.get("warranty_years", 2)), 12) / 12.0,
            "noise": (60.0 - float(a.get("noise_db", 55))) / 16.0,
            "return_friction": p.returns.fee_cents / 20_000,
            "free_shipping_salience": 1.0 if p.shipping.price_cents == 0 else 0.0,
            "position_bias": -float(rank),
        }

    def _utility(self, m: BuyerMandate, p: ProductState, rank: int) -> float:
        f = self._features(m, p, rank)
        w = m.preference_weights
        C = TRUE_COEFS

        def imp(key: str, default: float) -> float:
            return 0.4 + 1.6 * w.get(key, default)

        u = 0.0
        u += C["price"] * f["price"] * (0.6 + 1.4 * w.get("price", 0.2))
        u += C["over_budget"] * f["over_budget"]
        u += C["delivery_speed"] * f["delivery_speed"] * imp("delivery_speed", 0.10)
        u += C["stability"] * f["stability"] * imp("stability", 0.18)
        u += C["capacity"] * f["capacity"] * imp("capacity", 0.12)
        u += C["height_range"] * f["height_range"] * imp("height_range", 0.10)
        u += C["footprint"] * f["footprint"] * imp("footprint", 0.12)
        u += C["aesthetics"] * f["aesthetics"] * imp("aesthetics", 0.10)
        u += C["warranty"] * f["warranty"] * imp("warranty", 0.12)
        u += C["noise"] * f["noise"] * imp("noise", 0.06)
        u += C["return_friction"] * f["return_friction"]
        u += C["free_shipping_salience"] * f["free_shipping_salience"]
        u += C["hard_violation"] * self._violates_hard(m, p)

        if self.position_bias:
            u += C["position_bias"] * f["position_bias"]

        # Persistent taste shock, constant across replications of one mandate.
        # This is what makes an LLM give nearly the same answer to the same
        # prompt twice, and it is the source of within-mandate correlation.
        h = int(hashlib.sha1(f"{m.mandate_id}|{p.product_id}".encode()).hexdigest()[:8], 16)
        u += C["mandate_taste"] * ((h / 0xFFFFFFFF) * 2.0 - 1.0)

        if p.availability != "in_stock":
            u -= 2.5
        return u

    def run(self, request: ProbeRequest) -> ChoiceRecord:
        rng = random.Random(request.seed)
        utils = [self._utility(request.mandate, p, i) for i, p in enumerate(request.candidates)]
        options = utils + [TRUE_COEFS["abstain_utility"]]

        gumbels = [u / self.temperature - math.log(-math.log(rng.random())) for u in options]
        idx = max(range(len(gumbels)), key=lambda i: gumbels[i])
        abstained = idx == len(request.candidates)

        order = sorted(range(len(utils)), key=lambda i: utils[i], reverse=True)
        return ChoiceRecord(
            probe_id=request.probe_id,
            cell_id=request.cell_id,
            discovered_product_ids=[p.product_id for p in request.candidates],
            considered_product_ids=[request.candidates[i].product_id for i in order[:6]],
            ranked_product_ids=[request.candidates[i].product_id for i in order[:4]],
            selected_product_id=None if abstained else request.candidates[idx].product_id,
            abstained=abstained,
            presented_order=[p.product_id for p in request.candidates],
            parser_version="oracle@1.0.0",
            parser_confidence=1.0,
            provider_name="simulated",
            model_id="choice_oracle@1.0.0-desk",
            adapter_version=self.version,
            prompt_version="n/a",
        )
