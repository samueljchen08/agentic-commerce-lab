"""Intervention definitions, each paired with its economic declaration.

An intervention has two halves that must stay together:
  * the *patch* — which catalog fields change (verified by the diff checker)
  * the *economics* — channel scope, per-order cost, conversion and return
    response, operational requirements

Splitting them is how you end up with a free-shipping arm that changes the
catalog but forgets the $14 subsidy.

Price points come from a merchant-approved grid. An LLM never invents one.
"""
from __future__ import annotations

from .domain import Intervention, InterventionType, ProductState
from .economics import ChannelScope, InterventionEconomics

Arm = tuple[Intervention, InterventionEconomics]


def release_0_set(focal: ProductState) -> list[Arm]:
    """The Release 0 arms.

    Deliberately spans all three channel scopes so the economic engine can
    demonstrate a ranking inversion:
        global + costly        -> free shipping
        agent-only + free      -> SLA exposure, attribute completion
        global + margin cut    -> price reduction
    """
    fid = focal.product_id
    arms: list[Arm] = []

    # --- 1. Global free shipping -------------------------------------------
    arms.append((
        Intervention(
            intervention_id="int_free_shipping",
            type=InterventionType.SHIPPING,
            label="Free standard shipping (all channels)",
            target_product_ids=[fid],
            patch={"shipping.price_cents": 0},
        ),
        InterventionEconomics(
            channel_scope=ChannelScope.GLOBAL,
            direct_cost_cents_per_order=focal.shipping.price_cents,
            # Free shipping raises checkout conversion. Holding this at 1.0
            # would under-credit the global lever and flatter our own thesis.
            conversion_multiplier=1.08,
            operational_requirements=("absorb shipping cost on every order",),
        ),
    ))

    # --- 2. Expose an already-true delivery SLA to agent feeds --------------
    # NOTE: this arm is only legitimate if the merchant can actually fulfil at
    # this speed. Exposing an SLA you cannot honour is lying to an agent
    # surface, and the product must never recommend it.
    arms.append((
        Intervention(
            intervention_id="int_agent_sla",
            type=InterventionType.SHIPPING,
            label="Expose existing 7-day delivery SLA in agent feed",
            target_product_ids=[fid],
            patch={"shipping.eta_min_days": 5, "shipping.eta_max_days": 7},
        ),
        InterventionEconomics(
            channel_scope=ChannelScope.AGENT_ONLY,
            # ZERO. This arm exposes an SLA the merchant ALREADY meets; the
            # feed simply understates it. Charging a freight-upgrade cost here
            # would be modelling a different intervention (buying faster
            # fulfilment), which belongs in its own arm.
            direct_cost_cents_per_order=0,
            conversion_multiplier=1.0,
            operational_requirements=(
                "fulfilment must genuinely meet a 5-7 day SLA for agent-sourced orders",
                "SLA must already be true — never publish a delivery promise you cannot keep",
            ),
        ),
    ))

    # --- 3. Structured attribute completion --------------------------------
    # Only exposes facts already true of the product. Never fabricate.
    completed = dict(focal.attributes)
    for k in ("presets", "cable_management", "noise_db", "leg_stages"):
        completed.setdefault(k, focal.attributes.get(k))
    arms.append((
        Intervention(
            intervention_id="int_feed_attributes",
            type=InterventionType.ATTRIBUTE_DATA,
            label="Complete structured attributes in agent feed",
            target_product_ids=[fid],
            patch={"attributes": completed},
        ),
        InterventionEconomics(
            channel_scope=ChannelScope.AGENT_ONLY,
            direct_cost_cents_per_order=0,
            conversion_multiplier=1.0,
            operational_requirements=("attributes must be source-verified, never invented",),
        ),
    ))

    # --- 4. 5% price reduction ---------------------------------------------
    new_price = int(round(focal.price_cents * 0.95, -2))
    arms.append((
        Intervention(
            intervention_id="int_price_5",
            type=InterventionType.PRICE,
            label=f"Cut list price 5% (${new_price/100:.0f})",
            target_product_ids=[fid],
            patch={"price_cents": new_price},
        ),
        InterventionEconomics(
            channel_scope=ChannelScope.GLOBAL,
            direct_cost_cents_per_order=0,
            # A price cut plausibly lifts checkout conversion too.
            conversion_multiplier=1.05,
            operational_requirements=("respect MAP and margin floor",),
        ),
    ))

    return arms


def representation_arms(focal: ProductState) -> list[Arm]:
    """The construct-validity study (v2.1 §19).

    Same commercial truth, three encodings. If structured >> text ≈ absent,
    the measured lift is mostly schema salience and the report must say so.
    This matters more than adding another commercial arm.
    """
    fid = focal.product_id
    econ = InterventionEconomics(
        channel_scope=ChannelScope.AGENT_ONLY,
        direct_cost_cents_per_order=0,
        operational_requirements=("SLA must already be true",),
    )
    return [
        (
            Intervention(
                intervention_id="rep_structured",
                type=InterventionType.ATTRIBUTE_DATA,
                label="SLA in structured shipping field",
                target_product_ids=[fid],
                patch={"shipping.eta_min_days": 5, "shipping.eta_max_days": 7},
            ),
            econ,
        ),
        (
            Intervention(
                intervention_id="rep_text",
                type=InterventionType.CONTENT,
                label="SLA in product copy only",
                target_product_ids=[fid],
                patch={"attributes": {**focal.attributes,
                                      "shipping_note": "Ships in 5-7 business days"}},
            ),
            econ,
        ),
        # 'absent' is the control arm; no patch needed.
    ]
