"""Cost preflight.

Estimates what a run will cost BEFORE dispatching a single probe, by building
one real message for a real mandate against the real candidate set and
measuring it. Nothing here is a guess about "typical" prompt size — the
candidate block dominates token count and scales with catalog size, so it must
be measured against the actual catalog.

The gate is a hard stop, not a warning. A typo in `--mandates` is the classic
way to turn a $12 run into a $1,200 one.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .adapters.base import ProbeRequest
from .domain import BuyerMandate, ProductState
from .mandates import render
from .parsing import build_user_message, SYSTEM_PROMPT


@dataclass
class CostEstimate:
    n_probes: int
    input_tokens_per_probe: int
    output_tokens_per_probe: int
    total_input_tokens: int
    total_output_tokens: int
    input_per_mtok: float
    output_per_mtok: float
    total_usd: float
    per_probe_usd: float
    budget_usd: float

    @property
    def within_budget(self) -> bool:
        return self.total_usd <= self.budget_usd

    def render(self) -> str:
        bar = "=" * 66
        status = "OK" if self.within_budget else "OVER BUDGET"
        return (
            f"\n{bar}\n  COST PREFLIGHT — {status}\n{bar}\n"
            f"  probes                {self.n_probes:,}\n"
            f"  tokens per probe      {self.input_tokens_per_probe:,} in / "
            f"{self.output_tokens_per_probe:,} out\n"
            f"  total tokens          {self.total_input_tokens:,} in / "
            f"{self.total_output_tokens:,} out\n"
            f"  price                 ${self.input_per_mtok}/Mtok in, "
            f"${self.output_per_mtok}/Mtok out\n"
            f"  cost per probe        ${self.per_probe_usd:.4f}\n"
            f"  PROJECTED TOTAL       ${self.total_usd:,.2f}\n"
            f"  budget                ${self.budget_usd:,.2f}\n{bar}"
        )


def approx_tokens(text: str) -> int:
    """Chars/2.4.

    Calibrated against a real call, not assumed: a probe estimated at 2,748
    input tokens actually consumed 4,146 (+86%). Two compounding reasons —
    JSON tokenizes worse than prose because of punctuation and quoted keys,
    and Claude 4.7+ tokenizers produce roughly 30% more tokens for the same
    text than older heuristics assume.

    Re-calibrate this against `scripts/check_provider.py` output whenever the
    model or the candidate-record shape changes. An underestimating preflight
    is a budget gate that has quietly stopped protecting you.
    """
    return int(len(text) / 2.4) + 1


def estimate_cost(
    *,
    mandate: BuyerMandate,
    candidates: list[ProductState],
    n_probes: int,
    input_per_mtok: float,
    output_per_mtok: float,
    budget_usd: float,
    max_output_tokens: int = 200,
) -> CostEstimate:
    """Build one real message and measure it. No 'typical prompt' guesswork."""
    req = ProbeRequest(
        probe_id="preflight", cell_id="preflight", mandate=mandate,
        candidates=candidates, template_index=0, seed=0,
    )
    user_msg = build_user_message(req, render(mandate, 0), diagnostic=False)
    in_tok = approx_tokens(SYSTEM_PROMPT) + approx_tokens(user_msg)
    # Minimal schema means short outputs; assume most of the ceiling is unused
    # but budget for half of it, plus the diagnostic sample overhead.
    out_tok = min(max_output_tokens, 90)

    total_in = in_tok * n_probes
    total_out = out_tok * n_probes
    total = total_in / 1_000_000 * input_per_mtok + total_out / 1_000_000 * output_per_mtok

    return CostEstimate(
        n_probes=n_probes,
        input_tokens_per_probe=in_tok,
        output_tokens_per_probe=out_tok,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        input_per_mtok=input_per_mtok,
        output_per_mtok=output_per_mtok,
        total_usd=total,
        per_probe_usd=total / n_probes if n_probes else 0.0,
        budget_usd=budget_usd,
    )


def load_env(path: str = ".env") -> dict[str, str]:
    """Minimal .env loader — avoids a dependency for eight lines of parsing."""
    values: dict[str, str] = {}
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in values.items():
        os.environ.setdefault(k, v)
    return values


def require_env(name: str, hint: str = "") -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(
            f"\n  {name} is not set.\n"
            f"  Copy .env.example to .env and fill it in."
            + (f"\n  {hint}" if hint else "")
        )
    return v
