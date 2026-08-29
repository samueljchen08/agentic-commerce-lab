"""Golden parser fixture set — real captured provider responses, hand-verified.

Cases come from `artifacts/raw/*.json` produced by real dispatched probes
(slice_smoke_002, slice_release0_60m and its v2-v5 re-dispatches,
icc_measurement_001), classified by response-text shape, then sampled and
run through the real `parse_choice()` to establish expected output — not
hand-guessed. One case (`synthetic_unresolved`) is hand-built because real
data contains zero instances of the model naming a product outside the
candidate set; project rule 2 (never force an entity match) has no organic
fixture, so this path is tested explicitly.

Category counts reflect real frequency in ~1770 captured artifacts, not an
even split: clean_json (1695 of 1770) is heavily sampled; truncated_nobrace
and empty are small but real failure modes worth locking down; prose_prefixed
and other (5) are exhaustive — every real instance of the disabled-thinking
prose-leakage bug is included.
"""
from __future__ import annotations

import json
from pathlib import Path

from acop.adapters.base import ProbeRequest
from acop.catalog_v1 import build_catalog
from acop.mandates import build_mandate_set
from acop.parsing import parse_choice

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "parser_golden_set.json").read_text()
)

MIN_PASS_RATE = 0.98


def _catalog_by_id():
    return {p.product_id: p for p in build_catalog(allow_unverified=True)}


def test_golden_set_pass_rate():
    by_id = _catalog_by_id()
    mandate = build_mandate_set(n=1)[0]

    failures = []
    for case in FIXTURES:
        candidates = [by_id[pid] for pid in case["candidate_order"] if pid in by_id]
        request = ProbeRequest("p1", "c1", mandate, candidates, 0, 1)
        record = parse_choice(
            case["response_text"],
            request,
            provider_name="anthropic",
            model_id="claude-sonnet-5",
            adapter_version="test",
            raw_artifact_path=case["source_file"],
        )
        ok = (
            record.selected_product_id == case["expected_selected_product_id"]
            and record.abstained == case["expected_abstained"]
            and record.parser_confidence == case["expected_parser_confidence"]
            and record.unresolved_text == case["expected_unresolved_text"]
        )
        if not ok:
            failures.append((case["name"], case["source_file"], record))

    pass_rate = 1 - len(failures) / len(FIXTURES)
    assert pass_rate >= MIN_PASS_RATE, (
        f"parser golden-set pass rate {pass_rate:.3f} below {MIN_PASS_RATE}: "
        f"{[(n, f) for n, f, _ in failures]}"
    )


def test_golden_set_covers_every_observed_response_shape():
    categories = {c["category"] for c in FIXTURES}
    assert categories == {
        "clean_json",
        "empty",
        "truncated_nobrace",
        "prose_prefixed",
        "other",
        "synthetic_unresolved",
    }


def test_never_forces_unresolved_entity_match():
    """Rule 2: a product named outside the candidate set must never resolve
    to a selection, even a plausible-looking one."""
    case = next(c for c in FIXTURES if c["category"] == "synthetic_unresolved")
    by_id = _catalog_by_id()
    mandate = build_mandate_set(n=1)[0]
    candidates = [by_id[pid] for pid in case["candidate_order"] if pid in by_id]
    request = ProbeRequest("p1", "c1", mandate, candidates, 0, 1)
    record = parse_choice(
        case["response_text"], request, raw_artifact_path=case["source_file"]
    )
    assert record.selected_product_id is None
    assert record.unresolved_text == "D99"
    assert record.parser_confidence <= 0.4
