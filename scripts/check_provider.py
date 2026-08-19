"""Provider check — one real API call, about half a cent."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from acop.adapters.anthropic_adapter import AnthropicBuyerAdapter, ProviderPricing
from acop.adapters.base import ProbeRequest
from acop.catalog_v1 import FOCAL_ID, build_catalog
from acop.mandates import build_mandate_set, render
from acop.manifest import ArtifactStore
from acop.preflight import estimate_cost, load_env, require_env

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    load_env()

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("\n  ANTHROPIC_API_KEY is not set in .env\n")
        return 1
    if not key.startswith("sk-ant-"):
        print(f"\n  ANTHROPIC_API_KEY looks wrong — expected 'sk-ant-', got '{key[:8]}...'\n")
        return 1
    print(f"  key       {key[:14]}...{key[-4:]}")

    model = require_env("PROVIDER_A_MODEL")
    in_price = float(require_env("PROVIDER_A_INPUT_PER_MTOK"))
    out_price = float(require_env("PROVIDER_A_OUTPUT_PER_MTOK"))
    print(f"  model     {model}")
    print(f"  pricing   ${in_price}/Mtok in, ${out_price}/Mtok out")

    try:
        import anthropic  # noqa: F401
    except ImportError:
        print("\n  SDK missing. Run: ./.venv/bin/pip install anthropic\n")
        return 1

    catalog = build_catalog(allow_unverified=True)
    mandate = build_mandate_set(n=5)[0]
    print(f"\n  sending one probe: {len(catalog)} products, mandate {mandate.mandate_id}")
    print(f'  shopper says: "{render(mandate, 0)[:110]}..."')

    est = estimate_cost(
        mandate=mandate, candidates=catalog, n_probes=1,
        input_per_mtok=in_price, output_per_mtok=out_price, budget_usd=1.0,
    )
    print(f"  estimated : {est.input_tokens_per_probe:,} in tokens, ${est.per_probe_usd:.5f}")

    store = ArtifactStore(ROOT / "artifacts")
    adapter = AnthropicBuyerAdapter(
        model=model,
        pricing=ProviderPricing(input_per_mtok=in_price, output_per_mtok=out_price),
        store=store,
        diagnostic_rate=1.0,
    )

    req = ProbeRequest(
        probe_id="provider_check", cell_id="provider_check",
        mandate=mandate, candidates=catalog, template_index=0, seed=1,
    )

    try:
        record = adapter.run(req)
    except Exception as exc:
        msg = str(exc)
        print(f"\n  CALL FAILED: {type(exc).__name__}")
        print(f"  {msg[:300]}")
        low = msg.lower()
        if "credit" in low or "billing" in low:
            print("\n  Billing issue. The API needs prepaid credit and is separate")
            print("  from a Claude.ai Pro subscription.")
        elif "not_found" in low or "model" in low:
            print(f"\n  '{model}' may not be a valid model ID. Check current docs.")
        elif "authentication" in low or "401" in msg:
            print("\n  Key rejected. Regenerate it in the Anthropic Console.")
        return 1

    usage = adapter.usage_summary()
    actual = usage["estimated_cost_usd"]

    print("\n" + "=" * 62)
    print("  PROVIDER CHECK PASSED")
    print("=" * 62)
    print(f"  selected        {record.selected_product_id}"
          f"{'  (FOCAL)' if record.selected_product_id == FOCAL_ID else ''}")
    print(f"  abstained       {record.abstained}")
    print(f"  parsed cleanly  {record.parser_confidence >= 0.85} "
          f"(confidence {record.parser_confidence})")
    if record.unresolved_text:
        print(f"  UNRESOLVED      model named '{record.unresolved_text}', not in candidate set")
    if record.stated_reasons:
        print(f"  reason          {record.stated_reasons[0][:150]}")
    print(f"\n  actual tokens   {usage['input_tokens']:,} in / {usage['output_tokens']:,} out")
    print(f"  actual cost     ${actual:.5f}   (estimated ${est.per_probe_usd:.5f})")

    drift = (actual - est.per_probe_usd) / est.per_probe_usd if est.per_probe_usd else 0
    if abs(drift) > 0.35:
        print(f"  NOTE: estimate off by {drift:+.0%}; preflight will be wrong at scale.")

    print("\n  projected costs at this rate:")
    for label, n in (("smoke (20 probes)", 20), ("slice (300 probes)", 300),
                     ("400 mandates x 3 reps x 5 arms", 6000)):
        print(f"    {label:<32} ${actual * n:>8.2f}")
    print(f"\n  raw artifact -> artifacts/{record.raw_artifact_path}")
    print("\n  Next:  python -m scripts.run_vertical_slice --smoke\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
