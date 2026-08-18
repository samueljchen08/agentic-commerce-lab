# Building catalog_v1 — your task, ~2 hours

10–12 products. One is the focal (yours). The rest are real competitors.

## Rules

1. **Every public fact needs a source URL and a timestamp.** Price, shipping cost,
   delivery estimate, return window, and physical specs all come off a real product
   page you looked at. Fill `catalog_sources_v1.csv` as you go — one row per field.
2. **Do not store images.** Usage rights are unclear and you do not need them.
3. **Do not scrape.** Twelve products by hand is two hours and is auditable.
   A scraper is a week and is not.
4. **Synthetic goes in a separate file.** COGS, fulfillment cost, return rate,
   payment fees, channel volumes, conversion, cannibalization — none of these are
   public. They live in `economics_demo_v1.json` and the report labels them
   SYNTHETIC. Never mix them into the catalog.

## The one decision that matters statistically

**Pick a focal product that is a genuine mid-pack contender.**

If the focal product is uncompetitive, its baseline selection rate will be ~2%, and
detecting a 3pp change on a 2% base needs several thousand mandates. If it is
obviously dominant, everything saturates at the ceiling and no intervention moves it.

Target a baseline selection rate of **10–20%**. Practically that means: mid-price
for the set, decent but not best specs, at least one visible weakness an
intervention could plausibly fix (slow shipping, thin attributes, paid shipping).

You will not know the real baseline until Day 1 runs. If the smoke test comes back
below ~5% or above ~35%, swap the focal product before building the full mandate
set. That swap is cheap on Day 1 and expensive on Day 5.

## Coverage to aim for across the 12

- price spread of at least 2.5x from cheapest to most expensive
- at least 3 with free shipping, at least 3 with paid shipping
- delivery estimates ranging from ~2 days to ~10 days
- a mix of return windows (30 / 45 / 60 day)
- at least 4 with materially different specs on the attribute your mandates care about

Homogeneous sets produce null results. Spread is what makes effects measurable.
