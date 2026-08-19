"""Cost preflight must measure a real message and gate hard on budget."""
from __future__ import annotations

from acop.catalog_v1 import build_catalog
from acop.mandates import build_mandate_set
from acop.preflight import approx_tokens, estimate_cost


def test_estimate_scales_with_catalog_size() -> None:
    cat = build_catalog(allow_unverified=True)
    m = build_mandate_set(n=5)[0]
    full = estimate_cost(mandate=m, candidates=cat, n_probes=10,
                         input_per_mtok=3.0, output_per_mtok=15.0, budget_usd=100)
    half = estimate_cost(mandate=m, candidates=cat[:6], n_probes=10,
                         input_per_mtok=3.0, output_per_mtok=15.0, budget_usd=100)
    # candidate block dominates: half the catalog must be materially cheaper
    assert half.input_tokens_per_probe < full.input_tokens_per_probe * 0.75


def test_budget_gate() -> None:
    cat = build_catalog(allow_unverified=True)
    m = build_mandate_set(n=5)[0]
    cheap = estimate_cost(mandate=m, candidates=cat, n_probes=10,
                          input_per_mtok=3.0, output_per_mtok=15.0, budget_usd=25)
    dear = estimate_cost(mandate=m, candidates=cat, n_probes=100_000,
                         input_per_mtok=3.0, output_per_mtok=15.0, budget_usd=25)
    assert cheap.within_budget
    assert not dear.within_budget


def test_token_estimate_is_conservative() -> None:
    # chars/3.6 should exceed the naive chars/4 heuristic
    text = '{"product_id": "D01", "price_usd": 269.0}'
    assert approx_tokens(text) > len(text) / 4
