"""Versioned parser and prompt construction.

Deliberately separate from any adapter: parsers are re-run against stored raw
artifacts, so improving a parser never costs another probe. This module must
not import a provider SDK.

Output minimization (v2.1 §61): the default real probe returns one product ID
and one abstain flag. Rationale is expensive, is never an outcome variable, and
is collected only on a small diagnostic sample.
"""
from __future__ import annotations

import json

from .adapters.base import ProbeRequest
from .domain import ChoiceRecord, ProductState

PARSER_VERSION = "choice_parser@1.0.0"
PROMPT_VERSION = "closed_catalog@1.0.0"

# Minimal schema — the default for every probe.
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_product_id": {
            "type": ["string", "null"],
            "description": "Exact product_id of the single best choice, or null to abstain.",
        },
        "abstain": {
            "type": "boolean",
            "description": "True if no product is a reasonable fit for this shopper.",
        },
    },
    "required": ["selected_product_id", "abstain"],
    "additionalProperties": False,
}

# Diagnostic schema — used on a configurable 5–10% sample only.
DIAGNOSTIC_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_product_id": {"type": ["string", "null"]},
        "abstain": {"type": "boolean"},
        "top_alternatives": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "reason": {"type": "string"},
    },
    "required": ["selected_product_id", "abstain"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You are helping one specific shopper choose a single product. "
    "You are given the complete set of products available to them, with full "
    "commercial terms. Evaluate them against what this shopper actually asked for. "
    "If no product is a reasonable fit, abstain rather than forcing a choice. "
    "Respond only with a JSON object matching the schema. No prose, no code fences."
)


def product_to_record(p: ProductState) -> dict:
    """Provider-neutral projection of ProductState.

    This is a *projection*, not the domain model. Provider feed schemas
    (OpenAI product feed, UCP, Merchant Center) each get their own projection.
    """
    return {
        "product_id": p.product_id,
        "brand": p.brand,
        "title": p.title,
        "price_usd": p.price_cents / 100,
        "shipping": {
            "cost_usd": p.shipping.price_cents / 100,
            "estimated_delivery_days": f"{p.shipping.eta_min_days}-{p.shipping.eta_max_days}",
        },
        "returns": {
            "window_days": p.returns.window_days,
            "fee_usd": p.returns.fee_cents / 100,
        },
        "warranty_months": p.warranty.duration_months,
        "availability": p.availability,
        "attributes": p.attributes,
    }


def build_user_message(request: ProbeRequest, rendered_mandate: str, diagnostic: bool = False) -> str:
    payload = {
        "shopper_request": rendered_mandate,
        "available_products": [product_to_record(p) for p in request.candidates],
        "response_schema": DIAGNOSTIC_SCHEMA if diagnostic else DECISION_SCHEMA,
    }
    return json.dumps(payload, indent=2)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1].removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def parse_choice(
    raw: str,
    request: ProbeRequest,
    *,
    provider_name: str = "unknown",
    model_id: str = "unknown",
    adapter_version: str = "unknown",
    raw_artifact_path: str = "",
) -> ChoiceRecord:
    """Parse a raw provider response into a normalized ChoiceRecord.

    Never forces an entity match. If the model names something outside the
    candidate set, the selection is dropped, the text is preserved in
    `unresolved_text`, and parser confidence falls. Silently coercing an
    unresolved mention into the focal product would corrupt the outcome
    variable in the direction that flatters the merchant.
    """
    valid = {p.product_id for p in request.candidates}
    presented = [p.product_id for p in request.candidates]
    data = _extract_json(raw)

    if data is None:
        return ChoiceRecord(
            probe_id=request.probe_id,
            cell_id=request.cell_id,
            selected_product_id=None,
            abstained=False,
            presented_order=presented,
            parser_confidence=0.0,
            parser_version=PARSER_VERSION,
            provider_name=provider_name,
            model_id=model_id,
            adapter_version=adapter_version,
            raw_artifact_path=raw_artifact_path,
        )

    confidence = 1.0 if raw.strip().startswith("{") else 0.85
    sel = data.get("selected_product_id")
    unresolved = None

    if sel is not None and sel not in valid:
        unresolved = str(sel)
        sel = None
        confidence = min(confidence, 0.4)

    abstained = bool(data.get("abstain", data.get("abstained", sel is None)))
    if sel is not None:
        abstained = False

    alts = [i for i in data.get("top_alternatives", []) if i in valid]
    reason = data.get("reason")

    return ChoiceRecord(
        probe_id=request.probe_id,
        cell_id=request.cell_id,
        discovered_product_ids=presented,
        considered_product_ids=alts,
        ranked_product_ids=([sel] if sel else []) + alts,
        selected_product_id=sel,
        abstained=abstained,
        stated_reasons=[reason] if reason else [],
        presented_order=presented,
        parser_confidence=confidence,
        parser_version=PARSER_VERSION,
        unresolved_text=unresolved,
        provider_name=provider_name,
        model_id=model_id,
        adapter_version=adapter_version,
        raw_artifact_path=raw_artifact_path,
    )
