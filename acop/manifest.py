"""Raw artifact persistence and the run manifest.

Two permanent rules live here.

**Write before parse.** The raw provider response is persisted to disk before
the parser is ever called. If that write fails, the probe is NOT counted as
completed and the cell is retried. A probe you paid for but cannot re-parse is
worse than a probe you never ran, because it silently biases the sample toward
whatever the parser happened to handle on the first attempt.

**Every result is reconstructible.** The manifest records catalog version,
mandate set version, intervention versions, prompt version, adapter version,
parser version, provider, model ID, and every seed. If you cannot rebuild the
experiment configuration exactly from the manifest, the result is not evidence.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


class ArtifactWriteError(RuntimeError):
    """Raised when a raw response cannot be persisted. The caller must treat
    the probe as incomplete — never as a successful call with a lost artifact."""


@dataclass
class ArtifactStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        (self.root / "raw").mkdir(parents=True, exist_ok=True)

    def write_raw(self, probe_id: str, payload: dict) -> str:
        """Persist a raw provider response. Returns the relative path.

        Raises ArtifactWriteError on any failure — including a readback
        mismatch, which catches a full disk or a truncated write.
        """
        safe = probe_id.replace("/", "_").replace(":", "_")
        path = self.root / "raw" / f"{safe}.json"
        body = json.dumps(payload, indent=2, default=str)
        try:
            path.write_text(body)
            if path.read_text() != body:
                raise ArtifactWriteError(f"readback mismatch for {probe_id}")
        except ArtifactWriteError:
            raise
        except OSError as exc:
            raise ArtifactWriteError(f"could not persist raw artifact for {probe_id}: {exc}") from exc
        return str(path.relative_to(self.root))

    def read_raw(self, relative_path: str) -> dict:
        return json.loads((self.root / relative_path).read_text())

    def write_json(self, name: str, payload: dict | list) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path

    def write_jsonl(self, name: str, rows: list[dict]) -> Path:
        path = self.root / name
        path.write_text("\n".join(json.dumps(r, default=str) for r in rows))
        return path


def content_hash(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "not-a-git-repo"


@dataclass
class RunManifest:
    """Everything needed to reconstruct this run's configuration exactly."""

    experiment_id: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None

    evidence_class: str = "E0_SYNTHETIC_SYSTEM_CHECK"

    catalog_version: str = ""
    catalog_hash: str = ""
    mandate_set_version: str = ""
    mandate_set_hash: str = ""
    intervention_versions: dict[str, str] = field(default_factory=dict)

    prompt_version: str = ""
    parser_version: str = ""
    adapter_name: str = ""
    adapter_version: str = ""
    provider_name: str = ""
    model_id: str = ""

    randomization_seed: int = 0
    replications: int = 0
    prompt_template_variants: int = 0
    n_mandates: int = 0
    n_arms: int = 0
    n_cells: int = 0

    probes_completed: int = 0
    probes_failed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    git_sha: str = field(default_factory=_git_sha)
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    platform: str = field(default_factory=platform.platform)

    notes: list[str] = field(default_factory=list)

    def finish(self) -> None:
        self.completed_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)
