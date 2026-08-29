"""Free, structural tests for item 7's cross-provider comparison. No API calls."""
from __future__ import annotations

from acop.economics import ActionResult, ActionStatus, ChannelScope
from acop.provider_comparison import provider_agreement_report
from acop.stats import spearman_rank_correlation


def test_spearman_perfect_agreement():
    a = {"x": 1.0, "y": 2.0, "z": 3.0}
    b = {"x": 10.0, "y": 20.0, "z": 30.0}
    assert spearman_rank_correlation(a, b) == 1.0


def test_spearman_perfect_disagreement():
    a = {"x": 1.0, "y": 2.0, "z": 3.0}
    b = {"x": 3.0, "y": 2.0, "z": 1.0}
    assert spearman_rank_correlation(a, b) == -1.0


def test_spearman_ties_use_midrank():
    a = {"x": 1.0, "y": 1.0, "z": 3.0}
    b = {"x": 1.0, "y": 1.0, "z": 3.0}
    assert spearman_rank_correlation(a, b) == 1.0


def test_spearman_needs_two_shared_keys():
    assert spearman_rank_correlation({"x": 1.0}, {"x": 1.0, "y": 2.0}) == 0.0
    assert spearman_rank_correlation({}, {}) == 0.0


def _action(iid, effect_pp, delta_total_cents, status):
    return ActionResult(
        intervention_id=iid,
        label=iid,
        channel_scope=ChannelScope.AGENT_ONLY,
        effect_pp=effect_pp,
        delta_total_cents=delta_total_cents,
        status=status,
    )


def test_provider_agreement_report_flags_status_and_sign_disagreement():
    actions_a = [
        _action("free_shipping", 8.68, -883_432_00, ActionStatus.REJECTED_VALUE),
        _action("agent_sla", 5.0, 90_262_00, ActionStatus.RECOMMENDED),
        _action("do_nothing_only_in_a", 0.0, 0, ActionStatus.PROMISING),
    ]
    actions_b = [
        _action("free_shipping", -2.0, -400_000_00, ActionStatus.REJECTED_VALUE),
        _action("agent_sla", 6.0, 100_000_00, ActionStatus.RECOMMENDED),
        _action("feed_attributes_only_in_b", 1.0, 1000, ActionStatus.INCONCLUSIVE),
    ]
    report = provider_agreement_report(actions_a, actions_b, "anthropic", "openai")

    assert report.n_shared_interventions == 2
    assert "free_shipping" in report.sign_disagreements
    assert "agent_sla" not in report.sign_disagreements
    assert report.status_disagreements == []
    assert set(report.status_agreements) == {"free_shipping", "agent_sla"}


def test_provider_agreement_report_status_disagreement_is_reported():
    actions_a = [_action("price_5", 4.0, 50_000_00, ActionStatus.RECOMMENDED)]
    actions_b = [_action("price_5", 3.5, 45_000_00, ActionStatus.PROMISING)]
    report = provider_agreement_report(actions_a, actions_b, "anthropic", "openai")

    assert report.status_disagreements == ["price_5: anthropic=RECOMMENDED vs openai=PROMISING"]
    assert report.status_agreements == []
