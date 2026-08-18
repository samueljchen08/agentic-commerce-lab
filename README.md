# Agentic Commerce Lab

Merchant-side decision system for agent-mediated demand.

Measures how AI buyer agents respond to merchant-controlled variables in a
controlled experiment, then translates those measured choice effects through
merchant unit economics into a ranked list of actions by modeled incremental
contribution profit — across all channels, not just the agent channel.

**The wedge:** the action with the largest agent-choice lift is frequently the
worst action on the board, because most levers cannot be scoped to the ~3% of
demand that agents mediate.

## Quick start

```bash
make setup          # venv + deps
make test           # 13 tests, ~0.3s
make sim            # full loop on the simulated oracle — free, no API calls
```

`make sim` should print selection effects, an ICC/design-effect line, and a
ranked action list, and write four artifacts. If it does, the scaffold is good.

## Evidence classes

Every number carries one. Never promote a result up a tier.

| Class | Environment | May claim |
|---|---|---|
| E0 | simulated oracle | the software behaves correctly under known assumptions |
| E1a | one real provider, frozen candidate set | causal within that model/prompt/candidate environment |
| E1b | two providers agreeing on rank | effect is robust across tested models |
| E2 | live/retrieval, not randomized | association on an external surface |
| E3 | randomized merchant test | causal in the merchant population |
| E4 | orders/returns/margin linked to treatment | realized incremental contribution |

The simulated oracle is E0 and is **not evidence about real agents**. It exists
so structural work costs nothing.

## Layout

```
acop/
  domain.py            canonical models, integer-cent money
  mandates.py          structured buyer intent + deterministic renderer
  interventions.py     arms paired with their economics declarations
  experiment.py        cells, pairing, position control, diff checker
  parsing.py           minimal-output schema + versioned parser
  stats.py             mandate-clustered Bayesian estimator + diagnostics
  economics.py         conversion, cannibalization, channel scope, breakeven
  manifest.py          artifact store (write-before-parse) + run manifest
  pipeline.py          the whole loop, adapter-agnostic
  adapters/
    base.py            ProbeRequest / BuyerSurfaceAdapter contract
    simulated.py       known-coefficient oracle (E0)
    anthropic_adapter.py   real provider, closed-catalog
  _seed_catalog.py     PLACEHOLDER fixture — replace with sourced products
fixtures/              your real catalog + sources CSV go here
artifacts/             run outputs (gitignored)
docs/BUILD_SPEC_v2.1.md
```

## Permanent rules

1. Raw provider response persists **before** parsing. Failed write = probe not completed.
2. Never force an entity match. Unresolved is a valid outcome.
3. Money is integer cents. No float in the money path.
4. Never call a lab effect a real-world lift.
5. Never call synthetic economics merchant economics.
6. `Do nothing` stays on the board.
7. Simulated oracle for structural debugging; real probes only for behavior measurement.
8. Model IDs and prices are configuration. Verify against current provider docs.
