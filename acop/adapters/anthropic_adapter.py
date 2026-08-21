"""Anthropic provider adapter — closed-catalog mode.

This is real-probe code. Every call costs money, so:
  * output is minimized to one product ID and one abstain flag
  * rationale is requested only on a small diagnostic sample
  * the raw response is persisted BEFORE parsing, and a failed write means
    the probe did not happen
  * token usage and estimated cost are recorded per probe

Model IDs and prices are configuration, never hard-coded constants. Verify
both against current provider documentation before a large run.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from ..domain import ChoiceRecord
from ..manifest import ArtifactStore, ArtifactWriteError
from ..parsing import PARSER_VERSION, PROMPT_VERSION, SYSTEM_PROMPT, build_user_message, parse_choice
from .base import ProbeRequest

ADAPTER_VERSION = "anthropic_closed_catalog@1.0.0"


@dataclass(frozen=True)
class ProviderPricing:
    """USD per million tokens. CHECK CURRENT PRICING before any large run."""

    input_per_mtok: float
    output_per_mtok: float

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.input_per_mtok
            + output_tokens / 1_000_000 * self.output_per_mtok
        )


class AnthropicBuyerAdapter:
    name = "anthropic"
    version = ADAPTER_VERSION

    def __init__(
        self,
        model: str,
        pricing: ProviderPricing,
        store: ArtifactStore,
        temperature: float = 1.0,
        max_tokens: int = 600,
        diagnostic_rate: float = 0.07,
        max_retries: int = 3,
    ):
        self.model = model
        self.pricing = pricing
        self.store = store
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.diagnostic_rate = diagnostic_rate
        self.max_retries = max_retries

        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.failures = 0

        import anthropic  # lazy: repo runs without the SDK installed

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=key)

    def _is_diagnostic(self, request: ProbeRequest) -> bool:
        return (request.seed % 1000) / 1000.0 < self.diagnostic_rate

    def run(self, request: ProbeRequest) -> ChoiceRecord:
        from ..mandates import render

        diagnostic = self._is_diagnostic(request)
        rendered = render(request.mandate, request.template_index)
        user_msg = build_user_message(request, rendered, diagnostic=diagnostic)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                started = time.time()
                resp = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens if not diagnostic else self.max_tokens + 300,
                    temperature=self.temperature,
                    system=SYSTEM_PROMPT,
                    # Claude 5-family models (incl. claude-sonnet-5) run adaptive
                    # thinking by default. Explicitly disabling it (tried first)
                    # backfires on harder filtering problems: with nowhere to
                    # think internally, the model sometimes reasons in the open —
                    # writes prose straight into the visible response — and that
                    # competes with the JSON answer for max_tokens (8/20 real
                    # probes were truncated mid-reasoning). Leaving thinking on
                    # at low effort keeps hard reasoning off-budget internally so
                    # the visible output stays a short, clean JSON object, which
                    # is what happened on every probe that had thinking room.
                    # 300 tokens still wasn't enough headroom: a 60-mandate real
                    # run (slice_release0_60m_v4) hit the 300-token ceiling on
                    # 12/300 probes (4%), each with output_tokens==300 and either
                    # an empty or mid-JSON-truncated response_text — thinking ran
                    # long on the harder mandates and left nothing for the visible
                    # answer. Bumped to 600; re-check parser_quality_pass after
                    # every run and raise further if truncation reappears.
                    output_config={"effort": "low"},
                    messages=[{"role": "user", "content": user_msg}],
                )
                elapsed = time.time() - started
                break
            except Exception as exc:  # transient provider errors only
                last_error = exc
                if attempt == self.max_retries - 1:
                    self.failures += 1
                    raise
                time.sleep(2**attempt)
        else:  # pragma: no cover
            raise last_error  # type: ignore[misc]

        text = "".join(b.text for b in resp.content if b.type == "text")
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = self.pricing.cost_usd(in_tok, out_tok)

        # --- persist BEFORE parsing. A failed write means the probe is not done.
        payload = {
            "probe_id": request.probe_id,
            "cell_id": request.cell_id,
            "mandate_id": request.mandate.mandate_id,
            "provider": self.name,
            "model_id": self.model,
            "adapter_version": ADAPTER_VERSION,
            "prompt_version": PROMPT_VERSION,
            "temperature": self.temperature,
            "diagnostic_sample": diagnostic,
            "template_index": request.template_index,
            "candidate_order": [p.product_id for p in request.candidates],
            "rendered_mandate": rendered,
            "response_text": text,
            "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
            "estimated_cost_usd": cost,
            "latency_seconds": round(elapsed, 3),
            "provider_request_id": getattr(resp, "id", None),
        }
        try:
            artifact_path = self.store.write_raw(request.probe_id, payload)
        except ArtifactWriteError:
            self.failures += 1
            raise

        self.input_tokens += in_tok
        self.output_tokens += out_tok
        self.cost_usd += cost

        record = parse_choice(
            text,
            request,
            provider_name=self.name,
            model_id=self.model,
            adapter_version=ADAPTER_VERSION,
            raw_artifact_path=artifact_path,
        )
        record.prompt_version = PROMPT_VERSION
        return record

    def usage_summary(self) -> dict:
        return {
            "provider": self.name,
            "model_id": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.cost_usd, 4),
            "failures": self.failures,
            "parser_version": PARSER_VERSION,
        }
