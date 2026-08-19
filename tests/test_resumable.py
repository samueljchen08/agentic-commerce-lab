"""Resumable adapter must reuse artifacts, and must NOT reuse across conditions."""
from __future__ import annotations

from pathlib import Path

from acop.adapters.base import ProbeRequest
from acop.adapters.resumable import ResumableAdapter
from acop.catalog_v1 import build_catalog
from acop.domain import ChoiceRecord
from acop.mandates import build_mandate_set
from acop.manifest import ArtifactStore


class _CountingAdapter:
    name, version = "fake", "0"

    def __init__(self, store):
        self.store = store
        self.calls = 0

    def run(self, request):
        self.calls += 1
        sel = request.candidates[0].product_id
        self.store.write_raw(request.probe_id, {
            "provider": "fake", "model_id": "m", "adapter_version": "0",
            "template_index": request.template_index,
            "candidate_order": [p.product_id for p in request.candidates],
            "response_text": f'{{"selected_product_id": "{sel}", "abstain": false}}',
        })
        return ChoiceRecord(probe_id=request.probe_id, cell_id=request.cell_id,
                            selected_product_id=sel, abstained=False)


def _req(cands, template=0):
    return ProbeRequest("p1", "c1", build_mandate_set(n=1)[0], cands, template, 1)


def test_reuses_matching_artifact(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    inner = _CountingAdapter(store)
    ad = ResumableAdapter(inner=inner, store=store)
    cat = build_catalog(allow_unverified=True)

    ad.run(_req(cat))
    ad.run(_req(cat))
    assert inner.calls == 1
    assert ad.reused == 1 and ad.dispatched == 1


def test_does_not_reuse_across_different_order(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    inner = _CountingAdapter(store)
    ad = ResumableAdapter(inner=inner, store=store)
    cat = build_catalog(allow_unverified=True)

    ad.run(_req(cat))
    ad.run(_req(list(reversed(cat))))     # different presentation order
    assert inner.calls == 2, "a different candidate order is a different condition"


def test_does_not_reuse_across_template(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    inner = _CountingAdapter(store)
    ad = ResumableAdapter(inner=inner, store=store)
    cat = build_catalog(allow_unverified=True)

    ad.run(_req(cat, template=0))
    ad.run(_req(cat, template=1))
    assert inner.calls == 2
