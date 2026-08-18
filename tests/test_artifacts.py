"""Raw artifact must be written before parsing; a failed write is not a probe."""
from __future__ import annotations

from pathlib import Path

import pytest

from acop.manifest import ArtifactStore, ArtifactWriteError


def test_roundtrip(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    rel = store.write_raw("probe:1/a", {"response_text": "{}"})
    assert store.read_raw(rel)["response_text"] == "{}"


def test_write_failure_raises(tmp_path: Path, monkeypatch) -> None:
    store = ArtifactStore(tmp_path)

    def boom(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    with pytest.raises(ArtifactWriteError):
        store.write_raw("probe_2", {"response_text": "x"})
