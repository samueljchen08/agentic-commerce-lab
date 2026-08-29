"""Cross-provider agreement report (item 7).

Two providers dispatched against the same catalog, mandates and arms produce
two independent ranked-action lists. This compares them without collapsing
them into one number: Spearman rank correlation on both the raw agent-choice
effect and the economics-ranked action value, plus an explicit list of
interventions where the two providers' recommendation status disagrees.

Never averages the two providers' effects together. A merged effect implies
one underlying truth measured twice; provider disagreement may instead mean
the two models genuinely weigh the same catalog facts differently, which is
itself the finding this function exists to surface.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

from .economics import ActionResult, ActionStatus, ChannelScope
from .stats import spearman_rank_correlation


@dataclass
class ProviderAgreementReport:
    provider_a: str
    provider_b: str
    n_shared_interventions: int
    effect_rank_correlation: float
    value_rank_correlation: float
    status_agreements: list[str] = field(default_factory=list)
    status_disagreements: list[str] = field(default_factory=list)
    sign_disagreements: list[str] = field(default_factory=list)

    def render(self) -> str:
        bar = "=" * 66
        lines = [
            "", bar,
            f"  PROVIDER AGREEMENT — {self.provider_a} vs {self.provider_b}",
            bar,
            f"  shared interventions        {self.n_shared_interventions}",
            f"  effect rank correlation     {self.effect_rank_correlation:+.3f}  (selection-effect ranking)",
            f"  value rank correlation      {self.value_rank_correlation:+.3f}  (modeled-$ ranking)",
        ]
        if self.sign_disagreements:
            lines.append(f"  SIGN DISAGREEMENT           {', '.join(self.sign_disagreements)}")
        if self.status_disagreements:
            lines.append("  STATUS DISAGREEMENT:")
            for d in self.status_disagreements:
                lines.append(f"    {d}")
        else:
            lines.append("  status agreement            all shared interventions match")
        return "\n".join(lines) + "\n"


def provider_agreement_report(
    actions_a: list[ActionResult],
    actions_b: list[ActionResult],
    provider_a: str,
    provider_b: str,
) -> ProviderAgreementReport:
    by_a = {a.intervention_id: a for a in actions_a}
    by_b = {b.intervention_id: b for b in actions_b}
    shared = sorted(set(by_a) & set(by_b))

    effect_corr = spearman_rank_correlation(
        {k: by_a[k].effect_pp for k in shared}, {k: by_b[k].effect_pp for k in shared}
    )
    value_corr = spearman_rank_correlation(
        {k: by_a[k].delta_total_cents for k in shared}, {k: by_b[k].delta_total_cents for k in shared}
    )

    agreements, disagreements, sign_flips = [], [], []
    for k in shared:
        a, b = by_a[k], by_b[k]
        if a.status == b.status:
            agreements.append(k)
        else:
            disagreements.append(f"{k}: {provider_a}={a.status.value} vs {provider_b}={b.status.value}")
        if a.effect_pp != 0 and b.effect_pp != 0 and (a.effect_pp > 0) != (b.effect_pp > 0):
            sign_flips.append(k)

    return ProviderAgreementReport(
        provider_a=provider_a,
        provider_b=provider_b,
        n_shared_interventions=len(shared),
        effect_rank_correlation=effect_corr,
        value_rank_correlation=value_corr,
        status_agreements=agreements,
        status_disagreements=disagreements,
        sign_disagreements=sign_flips,
    )


_ACTION_FIELD_NAMES = {f.name for f in fields(ActionResult)}


def load_actions_from_economics_json(path: str | Path) -> list[ActionResult]:
    """Reconstruct ActionResult objects from a written economics.json.

    `run_pipeline` writes actions with `channel_scope`/`status` flattened to
    plain strings and drops the `breakevens` field (not JSON-serializable as
    written); this reverses the enum flattening and ignores fields the
    written record doesn't carry.
    """
    payload = json.loads(Path(path).read_text())
    actions = []
    for row in payload["actions"]:
        kwargs = {k: v for k, v in row.items() if k in _ACTION_FIELD_NAMES}
        kwargs["channel_scope"] = ChannelScope(row["channel_scope"])
        kwargs["status"] = ActionStatus(row["status"])
        actions.append(ActionResult(**kwargs))
    return actions
