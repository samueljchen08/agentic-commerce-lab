"""Simulated choice oracle.

A latent-utility model with KNOWN coefficients. Its purpose is to validate the
machinery against ground truth we control -- NOT to imitate a real agent. A
number produced by this adapter is evidence class E0 and must always carry that
label in any output a human sees.

It deliberately encodes three realistic pathologies so they stay visible during
development:
  * free_shipping_salience -- responds to a boolean flag, not the dollar amount
  * position_bias          -- a layout confound larger than most real effects
  * mandate_taste          -- persistent per-(mandate, product) affinity, which
                              is what generates within-mandate correlation
"""
from __future__ import annotations

import hashlib
import math
import random

from ..domain import BuyerMandate, ChoiceRecord, ProductState
from .base import ProbeRequest

BRAND_TIER = {
    "Orion": 0.95, "Apex": 0.90, "Voyage": 0.85, "Pathfinder": 0.75,
    "Granite": 0.72, "Meridian": 0.70, "Stratus": 0.68, "Summit": 0.66,
    "Halcyon": 0.60, "Northbound": 0.58, "Atlas": 0.55, "Nomadica": 0.52,
    "Cirrus": 0.50, "Aeris": 0.45, "Lumen": 0.42, "Kestrel": 0.40,
    "Drift": 0.35, "Terra": 0.32, "Wayfare": 0.28, "Baseline": 0.20,
}
SHELL_DURABILITY = {"aluminum": 1.0, "polycarbonate": 0.75, "abs": 0.45, "ballistic_nylon": 0.55}

# Ground-truth structural coefficients. The estimator must recover treatment
# effects induced by changing product state under these, without seeing them.
TRUE_COEFS = {
    "price": -3.2,            # on price / budget ratio
    "over_budget": -2.6,      # additional penalty past a hard ceiling
    "delivery_speed": 1.9,
    "weight": 0.9,
    "capacity": 0.7,
    "durability": 1.4,
    "aesthetics": 1.1,
    "warranty": 1.0,
    "free_shipping_salience": 0.45,   # agents over-weight a "free shipping" flag
    "position_bias": 0.06,            # per-rank advantage of appearing earlier
    "mandate_taste": 0.85,            # persistent per-(mandate, product) affinity
    "abstain_utility": -2.4,
}


class SimulatedAgentAdapter:
    name = "simulated_choice_oracle"
    version = "0.3.0"

    def __init__(self, temperature: float = 1.0, position_bias: bool = True):
        self.temperature = temperature
        self.position_bias = position_bias

    # ---- feature construction (mandate x product) ----
    @staticmethod
    def _features(m: BuyerMandate, p: ProductState, rank: int) -> dict[str, float]:
        budget = m.budget_max_cents or 45000
        effective = p.price_cents + p.shipping.price_cents
        price_ratio = effective / budget
        over = max(0.0, price_ratio - 1.0)
        if over > 0:
            over *= (1.0 - m.budget_softness)

        eta_mid = (p.shipping.eta_min_days + p.shipping.eta_max_days) / 2
        if m.need_by_days:
            speed = max(-1.0, min(1.0, (m.need_by_days - eta_mid) / max(m.need_by_days, 1)))
        else:
            speed = (7 - eta_mid) / 7 * 0.4

        w = float(p.attributes.get("weight_lb", 8.0))
        cap = float(p.attributes.get("capacity_l", 38.0))
        shell = str(p.attributes.get("shell_material", "abs"))

        return {
            "price": price_ratio,
            "over_budget": over,
            "delivery_speed": speed,
            "weight": (9.0 - w) / 4.0,
            "capacity": (cap - 34.0) / 10.0,
            "durability": SHELL_DURABILITY.get(shell, 0.4),
            "aesthetics": BRAND_TIER.get(p.brand, 0.4),
            "warranty": min(p.warranty.duration_months, 120) / 120.0,
            "free_shipping_salience": 1.0 if p.shipping.price_cents == 0 else 0.0,
            "position_bias": -float(rank),
        }

    def _utility(self, m: BuyerMandate, p: ProductState, rank: int) -> float:
        f = self._features(m, p, rank)
        w = m.preference_weights
        u = 0.0
        u += TRUE_COEFS["price"] * f["price"] * (0.6 + 1.4 * w.get("price", 0.2))
        u += TRUE_COEFS["over_budget"] * f["over_budget"]
        u += TRUE_COEFS["delivery_speed"] * f["delivery_speed"] * (0.4 + 1.6 * w.get("delivery_speed", 0.15))
        u += TRUE_COEFS["weight"] * f["weight"] * (0.4 + 1.6 * w.get("weight", 0.15))
        u += TRUE_COEFS["capacity"] * f["capacity"] * (0.4 + 1.6 * w.get("capacity", 0.15))
        u += TRUE_COEFS["durability"] * f["durability"] * (0.4 + 1.6 * w.get("durability", 0.20))
        u += TRUE_COEFS["aesthetics"] * f["aesthetics"] * (0.4 + 1.6 * w.get("aesthetics", 0.10))
        u += TRUE_COEFS["warranty"] * f["warranty"] * (0.4 + 1.6 * w.get("warranty", 0.10))
        u += TRUE_COEFS["free_shipping_salience"] * f["free_shipping_salience"]
        if self.position_bias:
            u += TRUE_COEFS["position_bias"] * f["position_bias"]
        # Persistent taste shock, constant across replications of the same
        # mandate. This is what makes an LLM give nearly the same answer to
        # the same prompt twice, and it is the source of within-mandate
        # correlation that inflates the design effect.
        h = int(hashlib.sha1(f"{m.mandate_id}|{p.product_id}".encode()).hexdigest()[:8], 16)
        u += TRUE_COEFS["mandate_taste"] * ((h / 0xFFFFFFFF) * 2.0 - 1.0)
        if p.availability != "in_stock":
            u -= 2.5
        return u

    def run(self, request: ProbeRequest) -> ChoiceRecord:
        rng = random.Random(request.seed)
        utils = [
            self._utility(request.mandate, p, rank)
            for rank, p in enumerate(request.candidates)
        ]
        options = utils + [TRUE_COEFS["abstain_utility"]]

        # Gumbel-max sampling == softmax choice, with a real stochastic draw.
        gumbels = [u / self.temperature - math.log(-math.log(rng.random())) for u in options]
        idx = max(range(len(gumbels)), key=lambda i: gumbels[i])
        abstained = idx == len(request.candidates)

        order = sorted(range(len(utils)), key=lambda i: utils[i], reverse=True)
        ranked = [request.candidates[i].product_id for i in order[:5]]
        considered = [request.candidates[i].product_id for i in order[:8]]

        return ChoiceRecord(
            probe_id=request.probe_id,
            cell_id=request.cell_id,
            discovered_product_ids=[p.product_id for p in request.candidates],
            considered_product_ids=considered,
            ranked_product_ids=ranked,
            selected_product_id=None if abstained else request.candidates[idx].product_id,
            abstained=abstained,
            presented_order=[p.product_id for p in request.candidates],
            parser_version="oracle@0.3.0",
            parser_confidence=1.0,
            provider_name="simulated",
            model_id="choice_oracle@0.3.0",
            adapter_version=self.version,
            prompt_version="n/a",
        )
