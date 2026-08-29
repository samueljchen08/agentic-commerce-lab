# Agentic Commerce Lab

**A merchant-side decision system for agent-mediated demand.** It runs
controlled experiments in which real AI buyer agents choose among a frozen
competitive set, changes one merchant-controlled variable at a time, measures
the causal effect on agent choice, and translates that effect through
merchant unit economics into a ranked list of actions — by modeled
incremental contribution profit **across every channel a merchant sells
through, not just the agent channel.**

**[Live report →](https://samueljchen08.github.io/agentic-commerce-lab/)** —
an interactive decision ledger built from a real experiment's output.

---

## The wedge

Every tool in this space measures whether a merchant *appears* in AI answers.
None of them tell a merchant what to *change*, or what that change is worth.

The reason that gap exists is that the obvious move is usually wrong:

> **The intervention with the largest agent-choice lift is frequently the
> worst action on the board** — because almost no merchant lever can be
> scoped to only the agent-mediated slice of demand. Free shipping doesn't
> know an order came from an AI agent instead of a human on the website; it
> pays out on all of it.

On this lab's synthetic system-check catalog, free shipping wins **+8.68
percentage points of agent selection** — the single largest lift of any
tested lever — and **costs $883,432** once its price is paid across the
merchant's entire order volume instead of just the ~3% an agent influences.
The naive read (biggest lift → do it first) and the correct read (biggest
lift → check the denominator) point in opposite directions.

That correction — `Δtotal = agent_gain − non_agent_exposure`, not
"contribution per agent order" — is the product.

## Does this hold up on a real model, not just a synthetic check?

Yes, on the one real run this lab has spent real money on so far. Against a
sourced catalog of 11 real competitor desks plus one fictional focal product,
`claude-sonnet-5` was probed 300 times across 60 realistic buyer mandates and
5 experimental arms:

```
  SELECTION EFFECTS
    Free standard shipping (all channels)             +1.69 pp [ +0.04,  +6.22]  P(>0)=1.000

  RANKED ACTIONS  (modeled contribution, all channels)
    [PROMISING     ] Do nothing                                    $          0
    [INCONCLUSIVE  ] Complete structured attributes in agent feed  $     -8,966
    [INCONCLUSIVE  ] Expose existing 7-day delivery SLA in feed    $    -10,309
    [REJECTED_VALUE] Free standard shipping (all channels)         $   -188,718
    [REJECTED_VALUE] Cut list price 5% ($474)                      $   -236,982
```

Same pattern, real model: a statistically decisive, positive selection effect
(P(effect>0) = 1.000) that is still the wrong action once its cost is
integrated over real order volume. Full transcript, cost, and every ranked
action: [`reports/slice_release0_60m_v5.txt`](reports/slice_release0_60m_v5.txt).
This run is tagged evidence class `E1a` (one real provider, one frozen
candidate set, one prompt) — see [Evidence classes](#evidence-classes) for
what that does and doesn't license anyone to claim.

## How it works

```
buyer mandates (structured intent)
        │
        ▼
experiment arms  ──  one merchant-controlled variable changed at a time,
        │              candidate order randomized-but-paired to cancel
        │              position bias, everything else in the catalog frozen
        ▼
real AI buyer-agent probes  ──  closed candidate set, minimal-output JSON
        │                        schema, raw response persisted before parsing
        ▼
parsed choice records  ──  versioned parser, never forces an unresolved
        │                   mention onto a candidate in the set
        ▼
mandate-clustered Bayesian estimator  ──  P(effect > 0) as a real posterior
        │                                  probability, ICC-aware, valid
        │                                  under optional stopping
        ▼
merchant economics bridge  ──  agent-channel gain, cross-channel
        │                       cannibalization, and non-agent exposure,
        │                       kept as three separate numbers, never netted
        │                       into one until the final dollar figure
        ▼
ranked actions  ──  RECOMMENDED / PROMISING / INCONCLUSIVE / NO_EFFECT /
                     REJECTED_(VALUE|RISK|FEASIBILITY), by modeled $, with
                     "do nothing" permanently on the board
```

## Evidence classes

Every number this lab produces carries a tier, and the codebase enforces
never promoting a result up a tier or reusing a stochastic model response as
a fresh replication.

| Class | Environment | May claim |
|---|---|---|
| **E0** | simulated oracle, known coefficients | the software behaves correctly under known assumptions |
| **E1a** | one real provider, frozen candidate set | causal, within that model/prompt/candidate environment |
| **E1b** | two providers agreeing on rank | effect is robust across tested models |
| **E2** | live/retrieval surface, not randomized | association on an external surface |
| **E3** | randomized merchant test | causal in the merchant population |
| **E4** | orders/returns/margin linked to treatment | realized incremental contribution |

This lab has real, spent-money data at **E1a**. The simulated oracle (E0) is
free and unlimited and is used for all structural development — it is never
cited as evidence about how a real agent behaves.

## Engineering notes

A few decisions that look like overkill for a demo but are load-bearing for
the claim the lab makes:

- **Bayesian clustered inference, not a t-test.** Replications of the same
  buyer mandate are correlated (measured real intraclass correlation:
  **0.7456**), so probe count overstates precision unless you cluster on
  mandate. The estimator is a Dirichlet-weighted bootstrap over mandates,
  which makes `P(effect > 0)` a genuine posterior probability — not a
  p-value read backwards — and makes optional stopping valid.
- **A `NO_EFFECT` status, distinct from `INCONCLUSIVE`.** A selection effect
  stuck at P≈0.50 looks identical whether you're underpowered or looking at
  a genuine null — until you check CI width, not just the point estimate.
  `classify()` only calls a null decisively when the 90% CI sits entirely
  inside a configurable region of practical equivalence around zero;
  otherwise more data could still resolve it either way, and it stays
  `INCONCLUSIVE`. Verified against real data: two arms in the run above
  landed *exactly* tied with control (3 selections out of 60 mandates in
  both control and treatment); bootstrap-resampling that real result up to
  64x the sample size through the production estimator confirms `P(effect>0)`
  stays pinned at ~0.50 the whole way — growing N alone would not resolve it,
  which is the actual signature of "there's nothing here" rather than "ask
  again later."
- **Integer-cent money, everywhere.** No float ever touches a dollar
  figure; the type system won't let one in.
- **Write-before-parse artifact discipline.** The raw provider response is
  persisted to disk *before* it's parsed. A failed write means the probe
  didn't happen and gets retried — never a paid-for call whose only record
  is a crashed process.
- **Resumable, cache-aware dispatch.** Re-running an experiment (or
  improving the parser) re-parses already-paid-for responses at zero
  marginal cost, but only reuses a cached response if the candidate
  presentation order and prompt template match exactly — a cached response
  from a different position is a different experimental condition, not a
  free replication.
- **A cost preflight that's a hard gate, not a warning.** Every real
  dispatch measures actual token counts against the real catalog and prompt
  before spending a cent, and refuses to run above a configured budget. A
  typo in a mandate count fails loudly instead of turning into a four-figure
  surprise.
- **Never force an entity match.** If a model names something outside the
  closed candidate set, the parser records the raw text and drops the
  selection — it never gets coerced into "closest known product," which
  would corrupt the outcome variable in whatever direction that coercion
  happens to point.
- **A golden fixture set sampled from real failures, not invented ones.**
  The parser's test suite (`tests/test_parser_fixtures.py`) is built from
  ~1,770 real captured model responses, classified by what actually went
  wrong (truncated mid-JSON at the token cap, prose written before the JSON
  object, empty responses), with the *expected* output for each established
  by running the real parser against it — not guessed by hand.
- **Provider-neutral by construction.** `BuyerSurfaceAdapter` is a small
  protocol; the Anthropic and OpenAI adapters share it and share the exact
  same system prompt and free-text JSON parsing (deliberately no
  provider-specific structured-output mode), so a future cross-provider
  rank comparison measures model disagreement, not parsing-difficulty
  disagreement.

## Repo layout

```
acop/
  domain.py                canonical models, integer-cent money
  mandates.py               structured buyer intent + deterministic renderer
  catalog_v1.py              sourced real catalog (11 real competitors + 1 fictional focal)
  interventions.py          experimental arms paired with their economics declarations
  experiment.py              cells, pairing, position-bias control, diff checker
  parsing.py                 minimal-output schema + versioned parser
  stats.py                   mandate-clustered Bayesian estimator, ICC, Spearman correlation
  economics.py               conversion, cannibalization, channel scope, breakeven, classify()
  provider_comparison.py    cross-provider agreement report
  manifest.py                 artifact store (write-before-parse) + run manifest
  pipeline.py                 the whole loop, adapter-agnostic
  preflight.py                 cost estimation + hard budget gate
  adapters/
    base.py                    ProbeRequest / BuyerSurfaceAdapter contract
    simulated.py                known-coefficient oracle (E0)
    anthropic_adapter.py        real provider, closed-catalog
    openai_adapter.py          second provider, same protocol
    resumable.py                 cache-aware dispatch wrapper
fixtures/                    catalog sourcing docs + verification worksheet
tests/                        28 tests, incl. a real-data golden parser fixture set
scripts/
  run_simulated.py             free, no API calls
  run_vertical_slice.py        real dispatch — costs money, hard-gated
  compare_providers.py         Spearman rank correlation between two providers
  check_provider.py            connectivity smoke test
reports/                      real run transcripts + the interactive HTML report
docs/BUILD_SPEC_v2.1.md      the venture-scale product architecture this MVP is a slice of
CLAUDE.md                    the full engineering brief — permanent rules, decisions, and why
```

## Quick start

```bash
make setup          # venv + deps
make test           # 28 tests, well under a second
make sim            # full loop on the simulated oracle — free, no API calls
```

`make sim` prints selection effects, an ICC/design-effect line, and a ranked
action list, and writes `artifacts/effects.json` + `artifacts/economics.json`.
If it does, the whole loop — mandates through economics — is intact.

Real dispatch (`make smoke`, `make slice`, or `scripts/run_vertical_slice.py`)
costs actual money against a real provider API and is gated behind an
explicit cost preflight; see `CLAUDE.md` for the full spending discipline.

## What's next

- **Second provider, live.** The OpenAI adapter and the Spearman
  rank-correlation report are built; running it for real needs an
  `OPENAI_API_KEY` and a confirmed model/price in `.env`.
- **Representation-validity arms.** Already wired and validated for free on
  the simulated oracle: the same SLA fact encoded as a structured shipping
  field vs. product copy vs. absent. If structured data decisively beats
  prose, the measured lift is largely schema salience — worth knowing before
  telling a merchant to rewrite marketing copy instead of a data feed.
- **A live/retrieval surface (E2)** and eventually a randomized merchant
  pilot (E3) to move past a frozen lab candidate set.

## License

All rights reserved. This repository is public for evaluation, portfolio,
and diligence purposes — reading, running, and citing it is welcome. Reuse,
redistribution, or derivative works require permission.

---

Built by [Samuel Chen](https://github.com/samueljchen08).
