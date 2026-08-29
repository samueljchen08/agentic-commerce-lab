"""Cross-provider agreement report (item 7). Free — reads two already-written
economics.json files, dispatches nothing.

`run_pipeline` writes artifacts/economics.json at a fixed path, so a second
provider's run overwrites the first provider's summary. Snapshot each run's
file under a provider-specific name before running the next one, e.g.:

    python -m scripts.run_vertical_slice --mandates 60
    cp artifacts/economics.json artifacts/economics_anthropic.json

    python -m scripts.run_vertical_slice --mandates 60 --provider openai
    cp artifacts/economics.json artifacts/economics_openai.json

    python -m scripts.compare_providers \\
        artifacts/economics_anthropic.json anthropic \\
        artifacts/economics_openai.json openai
"""
from __future__ import annotations

import argparse

from acop.provider_comparison import load_actions_from_economics_json, provider_agreement_report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path_a")
    p.add_argument("name_a")
    p.add_argument("path_b")
    p.add_argument("name_b")
    args = p.parse_args()

    actions_a = load_actions_from_economics_json(args.path_a)
    actions_b = load_actions_from_economics_json(args.path_b)
    report = provider_agreement_report(actions_a, actions_b, args.name_a, args.name_b)
    print(report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
