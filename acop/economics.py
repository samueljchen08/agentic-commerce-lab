"""Economics engine — v2.1 corrected model.

Changes from the v2.0 implementation, all of which were real errors:

  A. A selection is not an order. v2.0 computed
         N_comparisons x P(select) x CM
     which silently assumed every agent selection converts. The corrected
     chain is comparisons -> selections -> orders -> contribution, with
     post-selection conversion `q` as an explicit, assumed, swept input.

  B. An agent-attributed order is not necessarily an incremental order.
     Some share would have arrived through direct, organic, email, or paid.
     Cannibalization rate `kappa` and the displaced channel's contribution
     margin now enter the bridge.

  C. Channel scope is a trichotomy, not a boolean. `partial` levers (an
     agent-only promo code that leaks) carry a spillover fraction.

Every uncertain input is tagged measured / observed / assumed / synthetic
and swept in the Monte Carlo. Nothing here is a measured merchant fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from .domain import Intervention, ProductState


class ChannelScope(StrEnum):
    AGENT_ONLY = "agent_only"
    GLOBAL = "global"
    PARTIAL = "partial"


class ActionStatus(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    PROMISING = "PROMISING"
    INCONCLUSIVE = "INCONCLUSIVE"
    REJECTED_VALUE = "REJECTED_VALUE"
    REJECTED_RISK = "REJECTED_RISK"
    REJECTED_FEASIBILITY = "REJECTED_FEASIBILITY"


class InputStatus(StrEnum):
    MEASURED = "MEASURED"            # this lab measured it
    OBSERVED = "OBSERVED"            # public, source-verified
    MERCHANT = "MERCHANT-PROVIDED"
    ASSUMED = "ASSUMED"              # a prior we chose
    SYNTHETIC = "SYNTHETIC"          # illustrative, not real


@dataclass(frozen=True)
class LedgerInput:
    """One row of the assumptions ledger. Every number the report shows
    that is not a lab measurement must have one of these."""

    name: str
    value: str
    status: InputStatus
    source: str
    sensitivity: str                 # low | medium | high


@dataclass
class MerchantEconomics:
    # volume
    annual_agent_comparison_events: int
    annual_non_agent_orders: int

    # conversion
    baseline_post_selection_conversion: float

    # incrementality
    cannibalization_rate: float
    displaced_channel_cm_cents: int

    # unit economics
    cogs_cents: int
    fulfillment_cost_cents: int
    payment_bps: int
    baseline_return_rate: float
    return_cost_cents: int

    # priors (min, max) — swept, never point-estimated
    conversion_prior: tuple[float, float] = (0.45, 0.80)
    cannibalization_prior: tuple[float, float] = (0.0, 0.60)
    elasticity_prior: tuple[float, float] = (0.0, 1.5)

    def ledger(self) -> list[LedgerInput]:
        return [
            LedgerInput("Agent comparison events / yr",
                        f"{self.annual_agent_comparison_events:,}",
                        InputStatus.SYNTHETIC, "demo scenario", "high"),
            LedgerInput("Non-agent orders / yr", f"{self.annual_non_agent_orders:,}",
                        InputStatus.SYNTHETIC, "demo scenario", "high"),
            LedgerInput("Post-selection conversion",
                        f"{self.baseline_post_selection_conversion:.0%} "
                        f"(swept {self.conversion_prior[0]:.0%}–{self.conversion_prior[1]:.0%})",
                        InputStatus.ASSUMED, "demo prior", "high"),
            LedgerInput("Cannibalization",
                        f"{self.cannibalization_rate:.0%} "
                        f"(swept {self.cannibalization_prior[0]:.0%}–{self.cannibalization_prior[1]:.0%})",
                        InputStatus.ASSUMED, "demo prior", "high"),
            LedgerInput("COGS", f"${self.cogs_cents/100:,.2f}",
                        InputStatus.SYNTHETIC, "illustrative", "medium"),
            LedgerInput("Fulfillment", f"${self.fulfillment_cost_cents/100:,.2f}",
                        InputStatus.SYNTHETIC, "illustrative", "low"),
            LedgerInput("Return rate", f"{self.baseline_return_rate:.1%}",
                        InputStatus.SYNTHETIC, "illustrative", "low"),
            LedgerInput("Non-agent price elasticity",
                        f"swept {self.elasticity_prior[0]:.1f}–{self.elasticity_prior[1]:.1f}",
                        InputStatus.ASSUMED, "demo prior", "high"),
        ]


@dataclass
class InterventionEconomics:
    """Per-intervention economic declarations. Separate from the patch,
    because these are business facts, not catalog fields."""

    channel_scope: ChannelScope
    direct_cost_cents_per_order: int = 0
    spillover_fraction: float = 0.0          # only for PARTIAL
    conversion_multiplier: float = 1.0       # q_a / q_0, see note below
    return_rate_multiplier: float = 1.0
    operational_requirements: tuple[str, ...] = ()
    feasible: bool = True

    def __post_init__(self) -> None:
        if self.channel_scope is ChannelScope.PARTIAL and self.spillover_fraction <= 0:
            raise ValueError("PARTIAL scope requires a spillover_fraction > 0")
        if self.channel_scope is not ChannelScope.PARTIAL and self.spillover_fraction:
            raise ValueError("spillover_fraction only applies to PARTIAL scope")


# NOTE on conversion_multiplier — this is a known bias vector and must not be
# left at 1.0 by default for price/shipping arms.
#
# The v2.1 spec permits assuming q_a == q_0 unless an intervention plausibly
# changes checkout conversion. But price cuts and free shipping are exactly
# the interventions that DO raise checkout conversion. Holding q constant
# therefore under-credits the global levers, which is the direction that
# flatters this product's central claim. Set it explicitly per arm, sweep it,
# and state the direction of the residual bias in the report.


@dataclass
class ActionResult:
    intervention_id: str
    label: str
    channel_scope: ChannelScope
    status: ActionStatus = ActionStatus.INCONCLUSIVE
    status_reason: str = ""

    selection_rate_control: float = 0.0
    selection_rate_treatment: float = 0.0
    effect_pp: float = 0.0
    p_effect_positive: float = 0.0

    cm_control_cents: int = 0
    cm_treatment_cents: int = 0

    agent_orders_control: float = 0.0
    agent_orders_treatment: float = 0.0
    gross_agent_delta_cents: float = 0.0
    cannibalization_cents: float = 0.0
    agent_channel_gain_cents: float = 0.0
    non_agent_effect_cents: float = 0.0
    delta_total_cents: float = 0.0

    p5_cents: float = 0.0
    p50_cents: float = 0.0
    p95_cents: float = 0.0
    p_profit_positive: float = 0.0

    breakevens: dict[str, float | None] = field(default_factory=dict)


# ------------------------------------------------------------------ margin


def contribution_margin_cents(
    state: ProductState, econ: MerchantEconomics, ie: InterventionEconomics | None
) -> int:
    """Per-order contribution, integer cents. No float ever touches money."""
    price = state.price_cents
    payment = price * econ.payment_bps // 10_000
    subsidy = ie.direct_cost_cents_per_order if ie else 0
    rate_mult = ie.return_rate_multiplier if ie else 1.0
    return_rate = min(0.60, econ.baseline_return_rate * rate_mult)
    expected_return = int(round(return_rate * econ.return_cost_cents))
    return price - econ.cogs_cents - econ.fulfillment_cost_cents - payment - subsidy - expected_return


# ------------------------------------------------------------- the bridge


def _bridge(
    s_ctrl: np.ndarray, s_trt: np.ndarray,
    q_ctrl: np.ndarray, q_trt: np.ndarray,
    kappa: np.ndarray, eps: np.ndarray,
    cm_ctrl: int, cm_trt: int,
    econ: MerchantEconomics, ie: InterventionEconomics,
    price_pct_change: float,
) -> dict[str, np.ndarray]:
    """One vectorized pass of the full value bridge over Monte Carlo draws."""
    n_cmp = econ.annual_agent_comparison_events

    orders_ctrl = n_cmp * s_ctrl * q_ctrl
    orders_trt = n_cmp * s_trt * q_trt

    gross_delta = orders_trt * cm_trt - orders_ctrl * cm_ctrl

    d_orders = orders_trt - orders_ctrl
    cannibal = np.maximum(0.0, d_orders) * kappa * econ.displaced_channel_cm_cents

    agent_gain = gross_delta - cannibal

    n_non = econ.annual_non_agent_orders
    if ie.channel_scope is ChannelScope.AGENT_ONLY:
        non_agent = np.zeros_like(agent_gain)
    else:
        volume_response = -eps * price_pct_change          # cut price -> lift
        after = n_non * (1.0 + volume_response) * cm_trt
        before = n_non * cm_ctrl
        non_agent = after - before
        if ie.channel_scope is ChannelScope.PARTIAL:
            non_agent = non_agent * ie.spillover_fraction

    return {
        "orders_ctrl": orders_ctrl,
        "orders_trt": orders_trt,
        "gross_delta": gross_delta,
        "cannibal": cannibal,
        "agent_gain": agent_gain,
        "non_agent": non_agent,
        "total": agent_gain + non_agent,
    }


def evaluate_action(
    intervention: Intervention,
    ie: InterventionEconomics,
    baseline_state: ProductState,
    treated_state: ProductState,
    econ: MerchantEconomics,
    effect_posterior: np.ndarray,
    control_rate: float,
    rng: np.random.Generator | None = None,
) -> ActionResult:
    rng = rng or np.random.default_rng(23)
    d = len(effect_posterior)

    cm_ctrl = contribution_margin_cents(baseline_state, econ, None)
    cm_trt = contribution_margin_cents(treated_state, econ, ie)

    s_ctrl = np.full(d, control_rate)
    s_trt = np.clip(control_rate + effect_posterior, 0.0, 1.0)

    q0 = rng.uniform(*econ.conversion_prior, size=d)
    q_trt = np.clip(q0 * ie.conversion_multiplier, 0.0, 1.0)
    kappa = rng.uniform(*econ.cannibalization_prior, size=d)
    eps = rng.uniform(*econ.elasticity_prior, size=d)

    price_pct = (treated_state.price_cents - baseline_state.price_cents) / baseline_state.price_cents

    b = _bridge(s_ctrl, s_trt, q0, q_trt, kappa, eps, cm_ctrl, cm_trt, econ, ie, price_pct)

    return ActionResult(
        intervention_id=intervention.intervention_id,
        label=intervention.label,
        channel_scope=ie.channel_scope,
        selection_rate_control=control_rate,
        selection_rate_treatment=float(s_trt.mean()),
        effect_pp=float(effect_posterior.mean()),
        p_effect_positive=float((effect_posterior > 0).mean()),
        cm_control_cents=cm_ctrl,
        cm_treatment_cents=cm_trt,
        agent_orders_control=float(b["orders_ctrl"].mean()),
        agent_orders_treatment=float(b["orders_trt"].mean()),
        gross_agent_delta_cents=float(b["gross_delta"].mean()),
        cannibalization_cents=float(b["cannibal"].mean()),
        agent_channel_gain_cents=float(b["agent_gain"].mean()),
        non_agent_effect_cents=float(b["non_agent"].mean()),
        delta_total_cents=float(b["total"].mean()),
        p5_cents=float(np.quantile(b["total"], 0.05)),
        p50_cents=float(np.quantile(b["total"], 0.50)),
        p95_cents=float(np.quantile(b["total"], 0.95)),
        p_profit_positive=float((b["total"] > 0).mean()),
    )


# --------------------------------------------------------------- breakeven


def breakeven(
    f, lo: float, hi: float, tol: float = 1e-4, iters: int = 60
) -> float | None:
    """Bisection on a monotone-ish scalar sweep. Returns the input value at
    which f crosses zero, or None if it does not cross within [lo, hi].

    This powers the most persuasive line in the report: 'free shipping only
    becomes the right call above X% agent exposure, and you are at Y%'.
    """
    f_lo, f_hi = f(lo), f(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = f(mid)
        if abs(hi - lo) < tol:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


# ----------------------------------------------------------------- status


def classify(
    r: ActionResult,
    ie: InterventionEconomics,
    min_value_cents: int = 100_000,
    max_loss_probability: float = 0.25,
    inconclusive_p_band: tuple[float, float] = (0.15, 0.85),
) -> ActionResult:
    """Assign exactly one status. Nothing is silently dropped, and
    'inconclusive' is kept distinct from 'no effect' — conflating those is
    how an experimentation product loses credible users."""
    lo, hi = inconclusive_p_band
    if not ie.feasible:
        r.status = ActionStatus.REJECTED_FEASIBILITY
        r.status_reason = "operational requirements not met: " + ", ".join(
            ie.operational_requirements
        )
    elif lo < r.p_effect_positive < hi:
        r.status = ActionStatus.INCONCLUSIVE
        r.status_reason = (
            f"selection effect not resolved (P(effect>0)={r.p_effect_positive:.2f}); "
            "more mandates required"
        )
    elif r.delta_total_cents < min_value_cents:
        r.status = ActionStatus.REJECTED_VALUE
        r.status_reason = f"modeled contribution ${r.delta_total_cents/100:,.0f} below floor"
    elif (1 - r.p_profit_positive) > max_loss_probability:
        r.status = ActionStatus.REJECTED_RISK
        r.status_reason = f"P(loss) = {1-r.p_profit_positive:.0%} exceeds risk limit"
    elif r.p_profit_positive >= 0.85:
        r.status = ActionStatus.RECOMMENDED
        r.status_reason = "clears value, risk and feasibility gates"
    else:
        r.status = ActionStatus.PROMISING
        r.status_reason = "positive expected value, uncertainty still material"
    return r


def do_nothing() -> ActionResult:
    """The permanent null action. Delta is zero by construction; it exists so
    the ranking is well-formed and so 'change nothing' can win."""
    return ActionResult(
        intervention_id="int_do_nothing",
        label="Do nothing",
        channel_scope=ChannelScope.AGENT_ONLY,
        status=ActionStatus.PROMISING,
        status_reason="baseline; always on the board",
        p_profit_positive=1.0,
    )


def rank(actions: list[ActionResult]) -> list[ActionResult]:
    order = {
        ActionStatus.RECOMMENDED: 0, ActionStatus.PROMISING: 1,
        ActionStatus.INCONCLUSIVE: 2, ActionStatus.REJECTED_RISK: 3,
        ActionStatus.REJECTED_FEASIBILITY: 4, ActionStatus.REJECTED_VALUE: 5,
    }
    return sorted(actions, key=lambda a: (order[a.status], -a.delta_total_cents))
