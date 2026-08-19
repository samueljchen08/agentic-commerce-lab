# The 20 minutes that matter — checkout verification

`acop/catalog_v1.py` holds 11 real competitors with source-verified specs, plus
one fictional focal merchant (Arbor). Specs are done.

**Four fields per competitor could not be sourced from search**, because they
live behind checkout rather than on spec pages:

| Field | Why it's not searchable |
|---|---|
| `shipping_usd` | Calculated at cart, varies by ZIP and desktop size |
| `eta_min_days` | Shown after address entry |
| `eta_max_days` | Same |
| `returns_fee_usd` | Buried in policy pages; often "customer pays return freight" with no number |

**These are the two levers your headline arms act on.** The free-shipping arm
needs shipping to vary. The SLA arm needs lead times to vary. If you fill in
nothing else by hand, fill in these.

## How to do it

For each of the 11 competitors: add the desk to cart, enter a ZIP (use one
consistent ZIP for the whole catalog — shipping varies regionally and mixing
ZIPs makes the set incoherent), and record what checkout shows.

Then set the four fields in `acop/catalog_v1.py` and run:

```python
from acop.catalog_v1 import verification_report
verification_report()["ready_for_real_run"]   # must be True
```

`build_catalog()` raises `UnverifiedCatalogError` until every field is filled.
That gate is deliberate — it is what stops invented numbers reaching a report.

## What to expect

Standing desks should show real spread here. If they don't — if all 11 are free
shipping with identical lead times — the category has no headroom and we should
know that before spending probes, not after.

Record the ZIP you used and the date in the `checked_at` field. Shipping
promotions change; a catalog is a snapshot.
