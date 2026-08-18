"""Probe contract. Core experiment code sees only these types.

Provider-specific response shapes must never cross this boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain import BuyerMandate, ChoiceRecord, ProductState


@dataclass(frozen=True)
class ProbeRequest:
    probe_id: str
    cell_id: str
    mandate: BuyerMandate
    candidates: list[ProductState]      # already in presentation order
    template_index: int
    seed: int


class BuyerSurfaceAdapter(Protocol):
    name: str
    version: str

    def run(self, request: ProbeRequest) -> ChoiceRecord: ...
