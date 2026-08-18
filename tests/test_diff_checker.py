"""An arm that changes an undeclared field must abort before any API call."""
from __future__ import annotations

import pytest

from acop._seed_catalog import MERCHANT_PRODUCT_ID, build_catalog
from acop.domain import Intervention, InterventionType, cents
from acop.experiment import UndeclaredTreatmentDiff, apply_intervention, assert_only_declared_changes


def test_declared_change_passes() -> None:
    catalog = build_catalog()
    iv = Intervention(
        intervention_id="ok", type=InterventionType.SHIPPING, label="free ship",
        target_product_ids=[MERCHANT_PRODUCT_ID], patch={"shipping.price_cents": 0},
    )
    assert_only_declared_changes(catalog, apply_intervention(catalog, iv), iv)


def test_undeclared_change_aborts() -> None:
    catalog = build_catalog()
    honest = Intervention(
        intervention_id="sneaky", type=InterventionType.SHIPPING, label="free ship",
        target_product_ids=[MERCHANT_PRODUCT_ID], patch={"shipping.price_cents": 0},
    )
    treated = apply_intervention(catalog, honest)
    # simulate a bug: price silently changed too
    for p in treated:
        if p.product_id == MERCHANT_PRODUCT_ID:
            p.price_cents = cents(279)
    with pytest.raises(UndeclaredTreatmentDiff, match="price_cents"):
        assert_only_declared_changes(catalog, treated, honest)
