"""The five hand-calculated economics cases v2.1 requires before any external
demo. Every expected value below was computed by hand first, then asserted.

Run: python -m tests.test_economics_v21
"""
from __future__ import annotations

import numpy as np

from acop.domain import Intervention, InterventionType, ProductState, Returns, Shipping, Warranty, cents
from acop.economics import (
    ChannelScope,
    InterventionEconomics,
    MerchantEconomics,
    ActionStatus,
    breakeven,
    classify,
    contribution_margin_cents,
    evaluate_action,
)

D = 20_000


def _state(price: float, ship: float = 14.0, eta=(4, 6)) -> ProductState:
    return ProductState(
        product_id="focal", brand="B", title="T", category="c",
        price_cents=cents(price),
        shipping=Shipping(price_cents=cents(ship), eta_min_days=eta[0], eta_max_days=eta[1]),
        returns=Returns(window_days=30),
        warranty=Warranty(duration_months=60),
        attributes={"weight_lb": 7.4},
    )


def _econ(**kw) -> MerchantEconomics:
    base = dict(
        annual_agent_comparison_events=38_000,
        annual_non_agent_orders=13_800,
        baseline_post_selection_conversion=0.60,
        cannibalization_rate=0.30,
        displaced_channel_cm_cents=cents(96),
        cogs_cents=cents(148),
        fulfillment_cost_cents=cents(41),
        payment_bps=290,
        baseline_return_rate=0.09,
        return_cost_cents=cents(22),
        conversion_prior=(0.60, 0.60),        # pinned for exact tests
        cannibalization_prior=(0.0, 0.0),
        elasticity_prior=(0.0, 0.0),
    )
    base.update(kw)
    return MerchantEconomics(**base)


def _iv(iid: str, label: str, patch: dict) -> Intervention:
    return Intervention(
        intervention_id=iid, type=InterventionType.SHIPPING, label=label,
        target_product_ids=["focal"], patch=patch,
    )


# ---------------------------------------------------------------- case 1

def test_margin_by_hand() -> None:
    """price 299 - cogs 148 - fulfil 41 - payment(299*2.9%=8.67->867c)
       - subsidy 0 - returns(0.09*2200=198c) = 299-148-41-8.67-1.98 = 99.35"""
    econ = _econ()
    cm = contribution_margin_cents(_state(299), econ, None)
    assert cm == 9935, cm
    print(f"  case 1 margin           : ${cm/100:.2f}  (expected $99.35)")


def test_zero_effect_is_zero_value() -> None:
    """No selection effect and no cost change -> exactly zero delta."""
    econ = _econ()
    s = _state(299)
    ie = InterventionEconomics(channel_scope=ChannelScope.AGENT_ONLY)
    r = evaluate_action(
        _iv("noop", "No-op", {}), ie, s, s, econ,
        np.zeros(D), control_rate=0.15, rng=np.random.default_rng(1),
    )
    assert abs(r.delta_total_cents) < 1e-6, r.delta_total_cents
    print(f"  case 2 zero effect      : ${r.delta_total_cents/100:,.2f}  (expected $0.00)")


# ---------------------------------------------------------------- case 3

def test_free_lift_agent_only() -> None:
    """+3pp selection, zero cost, agent-only.
       orders_c = 38000*0.15*0.60 = 3420
       orders_t = 38000*0.18*0.60 = 4104
       delta    = (4104-3420)*99.35 = 684*99.35 = $67,955.40"""
    econ = _econ()
    s = _state(299)
    ie = InterventionEconomics(channel_scope=ChannelScope.AGENT_ONLY)
    r = evaluate_action(
        _iv("feed", "Feed attributes", {}), ie, s, s, econ,
        np.full(D, 0.03), control_rate=0.15, rng=np.random.default_rng(2),
    )
    expected = 684 * 9935
    assert abs(r.delta_total_cents - expected) < 100, (r.delta_total_cents, expected)
    assert r.non_agent_effect_cents == 0.0
    print(f"  case 3 agent-only lift  : ${r.delta_total_cents/100:,.2f}  (expected ${expected/100:,.2f})")


# ---------------------------------------------------------------- case 4

def test_global_subsidy_destroys_value() -> None:
    """Free shipping: +6pp selection but a $14 subsidy on EVERY order.
       cm_t = 9935 - 1400 = 8535
       agent: 38000*0.21*0.6=4788 orders x 8535  minus  3420 x 9935
       non-agent: 13800 x (8535 - 9935) = -$193,200
       Total must be strongly negative."""
    econ = _econ()
    s = _state(299)
    ie = InterventionEconomics(
        channel_scope=ChannelScope.GLOBAL, direct_cost_cents_per_order=cents(14)
    )
    r = evaluate_action(
        _iv("ship", "Free shipping", {}), ie, s, s, econ,
        np.full(D, 0.06), control_rate=0.15, rng=np.random.default_rng(3),
    )
    assert r.cm_treatment_cents == 8535, r.cm_treatment_cents
    assert abs(r.non_agent_effect_cents - (13_800 * (8535 - 9935))) < 100
    assert r.delta_total_cents < 0, r.delta_total_cents
    print(f"  case 4 global subsidy   : ${r.delta_total_cents/100:,.2f}  "
          f"(agent +${r.agent_channel_gain_cents/100:,.0f}, "
          f"non-agent ${r.non_agent_effect_cents/100:,.0f})")


# ---------------------------------------------------------------- case 5

def test_cannibalization_eliminates_value() -> None:
    """Same +3pp agent-only lift, but 100% cannibalization against a
       displaced channel of equal margin -> gain collapses to ~zero."""
    econ = _econ(cannibalization_prior=(1.0, 1.0), displaced_channel_cm_cents=9935)
    s = _state(299)
    ie = InterventionEconomics(channel_scope=ChannelScope.AGENT_ONLY)
    r = evaluate_action(
        _iv("feed", "Feed attributes", {}), ie, s, s, econ,
        np.full(D, 0.03), control_rate=0.15, rng=np.random.default_rng(4),
    )
    assert abs(r.delta_total_cents) < 100, r.delta_total_cents
    print(f"  case 5 full cannibal.   : ${r.delta_total_cents/100:,.2f}  (expected ~$0.00)")


# ---------------------------------------------------------------- case 6

def test_price_cut_with_elasticity() -> None:
    """5% price cut, elasticity pinned at 1.0.
       new price 284.05 -> round to 284; payment floors to 823c: cm_t = 284-148-41-8.23-1.98 = 84.79
       non-agent volume response = -1.0 * (-0.0502) = +5.02%
       Still expected negative: margin loss dominates."""
    econ = _econ(elasticity_prior=(1.0, 1.0))
    s0, s1 = _state(299), _state(284)
    ie = InterventionEconomics(channel_scope=ChannelScope.GLOBAL, conversion_multiplier=1.05)
    r = evaluate_action(
        _iv("price", "Cut price 5%", {"price_cents": cents(284)}), ie, s0, s1, econ,
        np.full(D, 0.01), control_rate=0.15, rng=np.random.default_rng(5),
    )
    assert r.cm_treatment_cents == 8479, r.cm_treatment_cents
    print(f"  case 6 price cut        : ${r.delta_total_cents/100:,.2f}  "
          f"(cm ${r.cm_control_cents/100:.2f} -> ${r.cm_treatment_cents/100:.2f})")


# ------------------------------------------------------------- breakeven

def test_breakeven_solver() -> None:
    """Find the agent comparison volume at which free shipping breaks even."""
    s = _state(299)
    ie = InterventionEconomics(
        channel_scope=ChannelScope.GLOBAL, direct_cost_cents_per_order=cents(14)
    )

    def value_at(n_cmp: float) -> float:
        econ = _econ(annual_agent_comparison_events=int(n_cmp))
        r = evaluate_action(
            _iv("ship", "Free shipping", {}), ie, s, s, econ,
            np.full(2000, 0.06), control_rate=0.15, rng=np.random.default_rng(6),
        )
        return r.delta_total_cents

    be = breakeven(value_at, 1_000, 5_000_000)
    assert be is not None and be > 38_000
    print(f"  breakeven volume        : {be:,.0f} agent comparisons/yr "
          f"(scenario is at 38,000 -> {be/38_000:.1f}x away)")


def test_status_classification() -> None:
    econ = _econ()
    s = _state(299)
    ie = InterventionEconomics(channel_scope=ChannelScope.AGENT_ONLY)
    rng = np.random.default_rng(7)

    strong = classify(evaluate_action(_iv("a", "Strong", {}), ie, s, s, econ,
                                      rng.normal(0.03, 0.004, D), 0.15, rng), ie)
    noisy = classify(evaluate_action(_iv("b", "Noisy", {}), ie, s, s, econ,
                                     rng.normal(0.0, 0.03, D), 0.15, rng), ie)
    assert strong.status is ActionStatus.RECOMMENDED, strong.status
    assert noisy.status is ActionStatus.INCONCLUSIVE, noisy.status
    print(f"  status: strong={strong.status.value}  noisy={noisy.status.value}")
    print(f"          '{noisy.status_reason}'")


def _manual() -> None:
    print("\nECONOMICS v2.1 — five hand-calculated cases\n")
    test_margin_by_hand()
    test_zero_effect_is_zero_value()
    test_free_lift_agent_only()
    test_global_subsidy_destroys_value()
    test_cannibalization_eliminates_value()
    test_price_cut_with_elasticity()
    print()
    test_breakeven_solver()
    test_status_classification()
    print("\n  ALL PASS\n")
