# CLAUDE.md — Agentic Commerce Lab

Read this before touching anything. It carries decisions made across a long
design process. Several of them look wrong until you know why they exist, and
undoing one silently breaks the science rather than the code.

---

## What this is

A merchant-side decision system for agent-mediated demand. It runs controlled
experiments in which AI buyer agents choose among a frozen competitive set,
changing one merchant-controlled variable at a time, then translates measured
choice effects through merchant unit economics into a ranked list of actions by
modeled incremental contribution profit **across all channels**.

**The wedge:** the action with the largest agent-choice lift is frequently the
worst action on the board, because most levers cannot be scoped to the ~3% of
demand that agents mediate. In the current simulation, free shipping wins
+8.68pp of agent selection and costs $883,432.

Competing tools tell merchants whether they appear in AI answers. This tells
them which change to make and what it is worth.

---

## Current state

Working end to end. `make sim` runs 2,250 probes on the simulated oracle in ~3s
and produces a ranked action list. 19 tests pass. One real API call has been
made successfully against `claude-sonnet-5`.

| Component | File | State |
|---|---|---|
| Domain models, integer-cent money | `acop/domain.py` | done |
| Buyer mandates (7 desk segments) | `acop/mandates.py` | done |
| Interventions + their economics | `acop/interventions.py` | done |
| Experiment engine, diff checker | `acop/experiment.py` | done |
| Bayesian clustered estimator | `acop/stats.py` | done |
| Channel-mix economics | `acop/economics.py` | done |
| Artifact store + run manifest | `acop/manifest.py` | done |
| Minimal-output parser | `acop/parsing.py` | done |
| Cost preflight | `acop/preflight.py` | done |
| Pipeline | `acop/pipeline.py` | done |
| Simulated oracle (E0) | `acop/adapters/simulated.py` | done |
| Anthropic adapter | `acop/adapters/anthropic_adapter.py` | done, verified live |
| Resume / reparse wrapper | `acop/adapters/resumable.py` | done |
| Real catalog (11 real + 1 fictional) | `acop/catalog_v1.py` | **44 fields unverified** |
| HTML report | — | **not built yet** |
| Second provider | — | **not built yet** |

---

## THE BLOCKER

`acop/catalog_v1.py` has 11 real competitor desks with source-verified specs.
Four fields per competitor are still `None`: `shipping_usd`, `eta_min_days`,
`eta_max_days`, `returns_fee_usd`. They live behind checkout and could not be
sourced from search.

**These are the two fields the headline arms act on.** The free-shipping arm
needs shipping to vary; the SLA arm needs lead times to vary. With them unset,
all 11 competitors read as $0 shipping and 0-day delivery.

This is not theoretical. A real probe against the unverified catalog returned:

> "Only three desks meet the hard 48-inch width limit: D01, D02, and D05. All
> fit comfortably within the $950 budget **and ship immediately with no rush
> needed**."

The model reasoned fluently about data that does not exist.

`build_catalog()` raises `UnverifiedCatalogError` until the fields are filled.
**Do not work around this gate.** Do not pass `allow_unverified=True` in any
path that produces a merchant-facing number. The human fills these in from
checkout pages using one consistent ZIP code.

---

## Permanent rules

1. Raw provider response is persisted **before** parsing. A failed write means
   the probe did not happen and must be retried — never a successful call with
   a lost artifact.
2. Never force an entity match. If the model names something outside the
   candidate set, record `unresolved_text` and drop the selection. Coercing it
   into the focal product corrupts the outcome variable in the direction that
   flatters the merchant.
3. All money is integer cents. No float ever enters the money path.
4. Never call a lab effect a real-world lift.
5. Never call synthetic economics merchant economics.
6. `Do nothing` stays permanently on the action board.
7. Simulated oracle for all structural debugging. Real probes only for
   measuring model behaviour. Never spend a real probe debugging a formula or
   a template.
8. Model IDs and prices are configuration, never constants. Verify against
   current provider docs before any large run.
9. `INCONCLUSIVE` and "no effect" are different findings. Never conflate them.
10. Never cache a stochastic model choice as a fresh replication.
11. Evidence class travels with every number. Never promote a result up a tier.
12. Attributes must be source-verified. Never invent a spec. A blank is data —
    it is exactly what the attribute-completion arm is about.

---

## Decisions that look wrong but are not

**Economics uses `Δtotal = agent_gain − non_agent_exposure`, not expected
contribution per agent opportunity.** The per-opportunity version ignores that
a price cut applies to every channel. It recommends value-destroying actions.
This correction is the product.

**`channel_scope` is a trichotomy** (`AGENT_ONLY` / `GLOBAL` / `PARTIAL` with a
spillover fraction), not a boolean. Do not simplify it.

**The SLA arm has `direct_cost_cents_per_order=0`.** It exposes an SLA the
merchant *already meets* — the feed understates it. Correcting the feed costs
nothing. Charging a freight-upgrade cost here models a different intervention
and flips a $392k winner into a $122k loser. Buying genuinely faster
fulfilment is a separate arm that does not exist yet.

**`displaced_channel_cm_cents` must not exceed the control-arm contribution
margin.** The displaced order is the same product through another channel. Set
it higher and every incremental agent order becomes value-destroying by
construction.

**`conversion_multiplier` is not 1.0 for price and shipping arms.** Those levers
genuinely raise checkout conversion. Holding it at 1.0 under-credits the global
levers, which is the direction that flatters this product's central claim. See
the note in `economics.py`.

**Inference clusters on mandate and is Bayesian.** Replications of one mandate
are correlated. Power follows `effective_n`, not probe count. The Bayesian
formulation makes optional stopping valid and makes `P(profit>0)` a real
probability rather than a p-value read backwards.

**Candidate order is randomised per pair, held constant across arms.** The
simulated oracle carries a deliberate position-bias term. Balanced across arms
it is harmless; unbalanced it *is* the result.

**Mandate breadth beats replication depth.** Extra reps of the same mandate buy
very little power. Spend probe budget on more mandates.

**`ResumableAdapter` refuses to reuse an artifact if candidate order or template
index differs**, even for the same probe_id. A cached response from a different
presentation order is a different experimental condition.

**The focal product is fictional (Arbor, D12).** Competitors are real. Using a
real brand as focal would mean asserting a named company has weak shipping and
should reprice, from data we cannot fully verify.

**The tall-user constraint is 50.5 inches, not 51.** At 51, exactly one desk in
the real catalog clears it — the focal — which would hand it an entire segment
by construction. Real frame heights top out near 50.5–50.9.

**Target baseline selection rate is 0.10–0.20.** Below 0.05 the focal is
uncompetitive and no effect resolves at any sane budget. Above 0.35 it
saturates and nothing can move it. Currently 0.120 on the oracle.

---

## Cost discipline

Measured, not estimated: **~$0.0087 per probe** on `claude-sonnet-5` at
$2/$10 per Mtok, using the minimal output schema.

| Run | Probes | Cost |
|---|---|---|
| smoke | 20 | ~$0.17 |
| slice | 300 | ~$2.61 |
| 400 mandates × 3 reps × 5 arms | 6,000 | ~$52 |

`MAX_RUN_COST_USD` in `.env` is a hard gate — any run projecting above it is
refused before dispatch. There is also a spend cap set in the Anthropic Console.

**Known issue to fix:** `approx_tokens()` in `acop/preflight.py` uses
`len(text) / 3.6`, which underestimated a real call by 86% (2,748 estimated vs
4,146 actual). Claude 4.7+ tokenizers produce ~30% more tokens than prose
heuristics suggest. Change the divisor to `2.4` and update the comment.

---

## Task queue

1. Fix `approx_tokens()` divisor (above). Small, do it first.
2. **Human task:** fill the 44 checkout fields in `acop/catalog_v1.py`.
3. `python -m scripts.run_vertical_slice --smoke` — 20 probes, control only.
   Read the baseline selection rate. If outside 0.10–0.20, adjust the focal's
   specs and re-smoke *before* spending on a full run.
4. Full slice: `--mandates 60`. Real effects on real desks.
5. Measure real ICC. It will be far higher than the oracle's 0.013 — expect
   0.4–0.7 — which changes the sample plan. Update the power table.
6. Hand-label 60 probes; build the golden parser fixture set; gate at ≥98%.
7. Second provider (OpenAI) behind the same interface. Report per-provider
   effects and Spearman rank correlation. Provider disagreement is a finding,
   not noise.
8. HTML report: decision-first, ledger bridge showing agent gain vs non-agent
   exposure with the naive claim ghosted behind, assumptions ledger,
   sensitivity sliders, breakeven channel share.
9. Representation-validity arms: same commercial truth encoded as a structured
   field vs product copy vs absent. If structured ≫ text ≈ absent, the measured
   lift is largely schema salience and the report must say so.

---

## Working style

- Restate the acceptance criterion before starting a ticket. List files that
  will change. Do not broaden scope silently.
- Run `make test` after every change. 19 tests currently pass.
- Run `make sim` to check the full loop still produces sensible output.
- Do not add a database, web server, auth layer, or tenancy. None answers an
  open question. They are correctly specified in `docs/BUILD_SPEC_v2.1.md` and
  belong after a merchant has committed.
- Do not build the demand model (conditional logit). Running an intervention
  costs $3; predicting one is not yet worth the complexity.
- If a feature does not strengthen
  `intent → experiment → choice → causality → economics → action`,
  it is not on the critical path.

---

## Spending guardrail for autonomous work

Scripts under `scripts/` that hit a provider cost real money:
`run_vertical_slice.py`, `check_provider.py`.

**Do not run these autonomously.** Ask first, every time, and state the
projected cost from the preflight. `make sim`, `make test`, `make lint`, and
`make dryrun` are free and safe to run without asking.
