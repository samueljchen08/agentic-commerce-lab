"""Resumable adapter wrapper.

Real probes cost money, so losing them to a crash at 80% completion is a real
loss. This wrapper checks the artifact store before dispatching: if a raw
response for this probe_id is already on disk, it re-parses it instead of
paying for it again.

Two things fall out of that for free:

  * **Resume.** Re-run a failed experiment and only the missing probes are
    dispatched.
  * **Re-parsing.** Improve the parser, re-run with `force_reparse`, and every
    stored response is re-interpreted at zero cost. This is the whole reason
    parsing lives outside the adapter.

The wrapper is deliberately dumb about correctness: it only reuses an artifact
if the stored candidate ORDER and template index match the request exactly. A
cached response from a different presentation order is a different experimental
condition and reusing it would silently corrupt the position control.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import ChoiceRecord
from ..manifest import ArtifactStore
from ..parsing import parse_choice
from .base import BuyerSurfaceAdapter, ProbeRequest


@dataclass
class ResumableAdapter:
    inner: BuyerSurfaceAdapter
    store: ArtifactStore
    force_reparse: bool = False

    reused: int = field(default=0, init=False)
    dispatched: int = field(default=0, init=False)

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def version(self) -> str:
        return self.inner.version

    def _cached(self, request: ProbeRequest) -> ChoiceRecord | None:
        safe = request.probe_id.replace("/", "_").replace(":", "_")
        path = f"raw/{safe}.json"
        try:
            payload = self.store.read_raw(path)
        except (FileNotFoundError, ValueError):
            return None

        # Same probe id is not enough — the experimental condition must match.
        presented = [p.product_id for p in request.candidates]
        if payload.get("candidate_order") != presented:
            return None
        if payload.get("template_index") != request.template_index:
            return None
        text = payload.get("response_text")
        if text is None:
            return None

        return parse_choice(
            text,
            request,
            provider_name=payload.get("provider", "unknown"),
            model_id=payload.get("model_id", "unknown"),
            adapter_version=payload.get("adapter_version", "unknown"),
            raw_artifact_path=path,
        )

    def run(self, request: ProbeRequest) -> ChoiceRecord:
        cached = self._cached(request)
        if cached is not None:
            self.reused += 1
            return cached
        self.dispatched += 1
        return self.inner.run(request)

    def usage_summary(self) -> dict:
        base = self.inner.usage_summary() if hasattr(self.inner, "usage_summary") else {}
        return {**base, "probes_reused_from_disk": self.reused,
                "probes_dispatched": self.dispatched}
