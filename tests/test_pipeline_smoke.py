"""Smoke test: the whole loop runs on the oracle and produces every artifact."""
from __future__ import annotations

import json
from pathlib import Path

from acop.catalog import PLACEHOLDER_FOCAL_ID as MERCHANT_PRODUCT_ID, placeholder_catalog as build_catalog
from acop.adapters import SimulatedAgentAdapter
from acop.interventions import release_0_set
from acop.mandates import build_mandate_set
from acop.pipeline import run_pipeline
from scripts.run_simulated import demo_economics as _demo_econ
demo_economics = lambda: _demo_econ(62900)


def test_pipeline_produces_all_artifacts(tmp_path: Path) -> None:
    catalog = build_catalog()
    focal = next(p for p in catalog if p.product_id == MERCHANT_PRODUCT_ID)
    out = run_pipeline(
        experiment_id="test_smoke",
        catalog=catalog,
        focal_product_id=MERCHANT_PRODUCT_ID,
        mandates=build_mandate_set(n=20),
        arms=release_0_set(focal)[:2],
        merchant_economics=demo_economics(),
        adapter=SimulatedAgentAdapter(),
        artifacts_dir=tmp_path,
        replications=2,
        prompt_variants=1,
        progress=False,
    )
    for name in ("run_manifest.json", "effects.json", "economics.json", "choices.jsonl"):
        assert (tmp_path / name).exists(), name

    manifest = json.loads((tmp_path / "run_manifest.json").read_text())
    assert manifest["n_cells"] == 20 * 2 * 3
    assert manifest["catalog_hash"] and manifest["mandate_set_hash"]
    assert manifest["evidence_class"].startswith("E0")

    # do-nothing is always on the board
    econ = json.loads((tmp_path / "economics.json").read_text())
    assert any(a["intervention_id"] == "int_do_nothing" for a in econ["actions"])
    assert econ["assumptions_ledger"], "assumptions ledger must never be empty"
    assert out["validity"]["balanced"]
