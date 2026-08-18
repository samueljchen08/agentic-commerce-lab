"""Canonical domain models. Provider- and merchant-agnostic.

Money is stored in integer minor units (cents) everywhere. Never floats.
"""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- money


def cents(x: str | int | float) -> int:
    return int((Decimal(str(x)) * 100).quantize(Decimal("1")))


def dollars(c: int) -> Decimal:
    return (Decimal(c) / 100).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- product


class Shipping(BaseModel):
    price_cents: int
    eta_min_days: int
    eta_max_days: int


class Returns(BaseModel):
    window_days: int
    fee_cents: int = 0


class Warranty(BaseModel):
    duration_months: int
    type: Literal["limited", "full", "lifetime"] = "limited"


class ProductState(BaseModel):
    """The exact state of one product inside one experiment snapshot.

    Price / terms / availability are snapshot data, not static product fields.
    """

    product_id: str
    brand: str
    title: str
    category: str
    attributes: dict[str, float | int | str | bool] = Field(default_factory=dict)
    price_cents: int
    availability: Literal["in_stock", "backorder", "out_of_stock"] = "in_stock"
    shipping: Shipping
    returns: Returns
    warranty: Warranty
    promotion: str | None = None
    is_merchant_product: bool = False

    def net_price_cents(self) -> int:
        return self.price_cents + self.shipping.price_cents


class ProductEconomics(BaseModel):
    """Private merchant economics. Never crosses a tenant boundary."""

    product_id: str
    cogs_cents: int
    fulfillment_cents: int
    payment_cost_bps: int = 290           # 2.9%
    baseline_return_rate: float = 0.08
    return_cost_cents: int = 1800         # cost to process + restock a return


# ---------------------------------------------------------------- mandate


class Constraint(BaseModel):
    field: str
    op: Literal["<=", ">=", "==", "!="]
    value: float | int | str
    hard: bool = True


class BuyerMandate(BaseModel):
    """Structured buyer intent. Rendered to natural language at probe time.

    preference_weights are internal metadata used for stratification and
    population weighting. They are NEVER rendered into the agent prompt --
    doing so tells the agent the answer.
    """

    mandate_id: str
    version: str = "1.0"
    category: str
    segment: str
    budget_max_cents: int | None = None
    budget_softness: float = 0.0          # 0 = hard ceiling, 1 = fully soft
    use_case: str
    constraints: list[Constraint] = Field(default_factory=list)
    preference_weights: dict[str, float] = Field(default_factory=dict)
    need_by_days: int | None = None
    population_weight: float = 1.0
    source: Literal["synthetic", "merchant_intent", "support", "search", "manual"] = "synthetic"


# ---------------------------------------------------------------- experiment


class EvidenceClass(StrEnum):
    E0_SYNTHETIC_DESCRIPTIVE = "E0_SYNTHETIC_DESCRIPTIVE"
    E1_CONTROLLED_LAB = "E1_CONTROLLED_LAB"
    E2_EXTERNAL_OBSERVATIONAL = "E2_EXTERNAL_OBSERVATIONAL"
    E3_EXTERNAL_RANDOMIZED = "E3_EXTERNAL_RANDOMIZED"
    E4_REALIZED_ECONOMICS = "E4_REALIZED_ECONOMICS"


class InterventionType(StrEnum):
    PRICE = "price"
    PROMOTION = "promotion"
    SHIPPING = "shipping"
    RETURNS = "returns"
    WARRANTY = "warranty"
    BUNDLE = "bundle"
    CONTENT = "content"
    ATTRIBUTE_DATA = "attribute_data"
    NONE = "none"


class Intervention(BaseModel):
    """A structured, declared change to merchant state.

    `channel_isolable` is the field the spec was missing. A price cut applies
    to every channel; an ACP feed attribute applies only to agent surfaces.
    The optimizer must know the difference or it will recommend actions that
    lose money on non-agent volume.
    """

    intervention_id: str
    type: InterventionType
    label: str
    target_product_ids: list[str]
    patch: dict[str, object] = Field(default_factory=dict)
    channel_isolable: bool = False
    direct_cost_cents_per_order: int = 0
    reversible: bool = True
    risk_level: Literal["low", "medium", "high"] = "low"


class ChoiceRecord(BaseModel):
    """Normalized observed agent behavior. Never model-generated 'weights'."""

    probe_id: str
    cell_id: str
    discovered_product_ids: list[str] = Field(default_factory=list)
    considered_product_ids: list[str] = Field(default_factory=list)
    ranked_product_ids: list[str] = Field(default_factory=list)
    selected_product_id: str | None = None
    abstained: bool = False
    stated_reasons: list[str] = Field(default_factory=list)
    presented_order: list[str] = Field(default_factory=list)
    parser_version: str = "choice_parser@1.0.0"
    parser_confidence: float = 1.0
    # provenance — every record must be traceable back to the exact call
    unresolved_text: str | None = None
    provider_name: str = "unknown"
    model_id: str = "unknown"
    adapter_version: str = "unknown"
    prompt_version: str = "unknown"
    raw_artifact_path: str = ""


class ExperimentCell(BaseModel):
    cell_id: str
    experiment_id: str
    arm_id: str
    mandate_id: str
    replication_no: int
    pair_id: str
    position_seed: int
    randomized_order: int
