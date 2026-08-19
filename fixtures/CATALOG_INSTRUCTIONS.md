# Building catalog_v1 — standing desks. Your task, ~2 hours.

12 desks. One is the focal (the merchant we're advising). The rest are real
competitors. Every public fact needs a source URL and a timestamp in
`catalog_sources_v1.csv`.

## Pre-flight, 5 minutes — do this before sourcing all 12

Open five brand product pages and write down **shipping cost** and **stated
lead time**. If all five are identical, the category has no headroom and three
of your four arms are dead on arrival. Standing desks should show wide spread
here — that's why we picked them.

## Rules

1. **Source everything public.** Price, shipping cost, lead time, return window,
   return fee, and every spec come off a real page you looked at.
2. **No images.** Usage rights are unclear and you don't need them.
3. **No scraping.** Twelve by hand is two hours and is auditable.
4. **Synthetic stays separate.** COGS, fulfillment cost, return rate, channel
   volumes, conversion, cannibalization are not public. They live in
   `economics_demo_v1.json` and the report labels them SYNTHETIC.
5. **Leave blanks blank.** If noise_db isn't published, leave it empty. A blank
   is data — it's exactly what the attribute-completion arm is about. Never
   invent a spec.

## Candidate brands

Uplift, Fully/Branch, Autonomous, FlexiSpot, Vari, Ergonofis, Desky, Secretlab,
Progressive Desk, Humanscale, Steelcase, Jarvis, ApexDesk, Flexispot E7.

## Choosing the focal — the decision with the largest statistical consequence

**The focal must be a genuine mid-pack contender, weak precisely where the
interventions act.**

That means: competitive on specs and price, but currently carrying **paid
shipping**, a **long stated lead time**, and ideally an **incomplete attribute
set**. Those three weaknesses are what the arms have room to fix. A focal that's
already free-shipping, fast, and fully specced has no headroom and every arm
returns zero.

Target baseline selection rate: **0.10 to 0.20**.

The placeholder D05 is built this way — $579, $79 shipping, 12–24 day lead,
strong frame specs — and lands at 0.133. Use it as the shape to match.

| Baseline you measure | Meaning | Action |
|---|---|---|
| under 0.05 | focal is uncompetitive; effects unmeasurable | swap focal, rerun smoke test |
| 0.10–0.20 | ideal | proceed |
| over 0.35 | saturated; nothing can move it | strengthen competitors or weaken focal |

## Coverage to hit across the 12

Run `catalog_shape_report()` after building — it checks these automatically:

- price spread at least 2.5x low to high
- at least 3 free-shipping and 3 paid-shipping
- lead times spanning at least 10 days min-to-max
- 2 to 10 desks meeting each hard constraint (raise to 51in+, hold 250lb+,
  width 48in or under)

That last one matters most. If only one desk clears a hard constraint, that
segment has a forced answer and contributes no information. If all twelve clear
it, the constraint does nothing.
