"""Catalog v1 — 11 real competitors + 1 fictional focal merchant.

WHY THE FOCAL IS FICTIONAL
--------------------------
Competitors are real products with source-verified public facts. The focal is
"Arbor" — an invented mid-market DTC brand standing in for a design partner.

Using a real brand as the focal would mean the demo asserts that a named
company has weak shipping and should change its pricing, from data we cannot
fully verify. That is a commercial claim about a real business. It also happens
to be wrong about how the product works: the merchant is the customer, and the
competitive set is the market around them.

VERIFICATION STATUS
-------------------
Every field carries a status:
  VERIFIED   — read off a source page, URL and date recorded
  DERIVED    — computed or reasonably inferred from a verified fact
  UNVERIFIED — MUST be filled in from a checkout page before any real run
  FICTIONAL  — the focal merchant only

`build_catalog()` refuses to return a catalog containing UNVERIFIED fields
unless explicitly overridden. Shipping cost and lead time are UNVERIFIED for
every competitor, because they do not appear reliably in search results — they
live behind checkout. Those are also the two fields the shipping and SLA arms
act on, so filling them is the highest-value 20 minutes of catalog work.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .domain import ProductState, Returns, Shipping, Warranty, cents

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FOCAL_ID = "D12"


class UnverifiedCatalogError(RuntimeError):
    """Raised when a catalog still contains fields that must be checked by hand."""


@dataclass
class DeskRecord:
    product_id: str
    brand: str
    title: str
    price_usd: float
    width_in: float
    depth_in: float
    height_min_in: float
    height_max_in: float
    weight_capacity_lb: int
    motors: int
    leg_stages: int
    warranty_years: int
    top_material: str
    presets: int
    cable_management: bool
    returns_window_days: int
    noise_db: int | None = None
    # --- fields that cannot be sourced from search; fill from checkout ---
    shipping_usd: float | None = None
    eta_min_days: int | None = None
    eta_max_days: int | None = None
    returns_fee_usd: float | None = None
    # --- provenance ---
    source_url: str = ""
    checked_at: str = ""
    notes: str = ""
    fictional: bool = False

    def unverified_fields(self) -> list[str]:
        if self.fictional:
            return []
        missing = []
        for f in ("shipping_usd", "eta_min_days", "eta_max_days", "returns_fee_usd"):
            if getattr(self, f) is None:
                missing.append(f)
        return missing


# --------------------------------------------------------------------------
# Prices reflect typical street/promotional pricing observed Aug 2026, not list.
# FlexiSpot in particular effectively never sells at list, so list price would
# misrepresent the competitive set.
# --------------------------------------------------------------------------

COMPETITORS: list[DeskRecord] = [
    DeskRecord(
        "D01", "FlexiSpot", "FlexiSpot E5 (48x24)", 269.0,
        48, 24, 28.4, 48.0, 220, 2, 2, 10, "laminate", 4, False, 30,
        shipping_usd=0.0, eta_min_days=3, eta_max_days=6, returns_fee_usd=0.0,
        source_url="https://www.remoteofficeguy.com/flexispot-e5-vs-e6-vs-e7/",
        checked_at="2026-08-18",
        notes="~$209 frame-only street price; ~$269 complete. 10-yr warranty. Heights frame-only. "
        "Checkout fields per flexispot.com/shipping-policy (checked 2026-08-18, ZIP 60614): free "
        "shipping to contiguous 48 states, ships in 1-2 biz days with 3-6 day transit, 30-day "
        "risk-free returns with no restocking or return-shipping fee. Policy applies uniformly to "
        "all FlexiSpot standing desks.",
    ),
    DeskRecord(
        "D02", "FlexiSpot", "FlexiSpot E7 (48x24)", 369.0,
        48, 24, 22.8, 48.4, 355, 2, 3, 15, "laminate", 4, True, 30, noise_db=50,
        shipping_usd=0.0, eta_min_days=3, eta_max_days=6, returns_fee_usd=0.0,
        source_url="https://www.remoteofficeguy.com/flexispot-e7-review/",
        checked_at="2026-08-18",
        notes="~$299 frame / ~$369 complete street. 355lb, 15-yr, 4 presets, LCD keypad. "
        "Checkout fields per flexispot.com/shipping-policy (checked 2026-08-18, ZIP 60614): free "
        "shipping to contiguous 48 states, ships in 1-2 biz days with 3-6 day transit, 30-day "
        "risk-free returns with no restocking or return-shipping fee.",
    ),
    DeskRecord(
        "D03", "FlexiSpot", "FlexiSpot E7 Pro (55x28)", 499.0,
        55, 28, 24.0, 50.6, 440, 2, 3, 15, "bamboo", 4, True, 30, noise_db=50,
        shipping_usd=0.0, eta_min_days=3, eta_max_days=6, returns_fee_usd=0.0,
        source_url="https://www.remoteofficeguy.com/flexispot-e7-vs-e7-pro/",
        checked_at="2026-08-18",
        notes="C-frame, 440lb, 50.6in max frame height, comprehensive cable mgmt. "
        "Checkout fields per flexispot.com/shipping-policy (checked 2026-08-18, ZIP 60614): free "
        "shipping to contiguous 48 states, ships in 1-2 biz days with 3-6 day transit, 30-day "
        "risk-free returns with no restocking or return-shipping fee.",
    ),
    DeskRecord(
        "D04", "FlexiSpot", "FlexiSpot E7 Plus 4-leg (72x30)", 699.0,
        72, 30, 24.4, 49.6, 440, 2, 3, 15, "bamboo", 4, True, 30,
        shipping_usd=0.0, eta_min_days=3, eta_max_days=6, returns_fee_usd=0.0,
        source_url="https://magneticmag.com/2025/10/flexispot-e7-plus-4-leg-standing-desk/",
        checked_at="2026-08-18",
        notes="$499.99 base during summer promo, reg $599.99. Four-leg. Top priced separately. "
        "Checkout fields per flexispot.com/shipping-policy (checked 2026-08-18, ZIP 60614): free "
        "shipping to contiguous 48 states via standard FedEx (the CEVA freight surcharge only "
        "applies to L-shaped desktops, not this 4-leg model), ships in 1-2 biz days with 3-6 day "
        "transit, 30-day risk-free returns with no restocking or return-shipping fee.",
    ),
    DeskRecord(
        "D05", "Vari", "Vari Essential Electric (48x24)", 399.0,
        48, 24, 27.5, 47.2, 150, 1, 2, 3, "laminate", 4, False, 30,
        shipping_usd=0.0, eta_min_days=2, eta_max_days=7, returns_fee_usd=0.0,
        source_url="https://slickdeals.net/f/16208872-vari-essential-electric-standing-desk-48-x-24-varidesk-ergonomic-sit-to-stand-raising-desk-for-home-office-adjustable-height-desk-with-split-top-4-height-setting-199",
        checked_at="2026-08-18",
        notes="27.5-47.2in, 150lb, 3-yr warranty, split laminate top, 4 presets. "
        "Checkout fields per vari.com/faqs.html (checked 2026-08-18, ZIP 60614): free delivery to "
        "contiguous 48 states, arrives in 2-7 business days after ordering, 30-Day No-Risk "
        "Guarantee with free return arranged by Vari.",
    ),
    DeskRecord(
        "D06", "Vari", "Vari Electric Standing Desk (60x30)", 795.0,
        60, 30, 25.5, 50.5, 200, 2, 2, 5, "laminate", 4, True, 30,
        shipping_usd=0.0, eta_min_days=2, eta_max_days=7, returns_fee_usd=0.0,
        source_url="https://www.companionlink.com/blog/2026/08/vari-electric-standing-desk-alternatives-4-standing-desks-for-american-buyers-in-2026/",
        checked_at="2026-08-18",
        notes="60x30 caps at 200lb — notably below the 275-355 range of rivals. Ships mostly "
        "pre-assembled. Checkout fields per vari.com/faqs.html (checked 2026-08-18, ZIP 60614): "
        "free delivery to contiguous 48 states, arrives in 2-7 business days after ordering, "
        "30-Day No-Risk Guarantee with free return arranged by Vari.",
    ),
    DeskRecord(
        "D07", "Branch", "Branch Duo (57x27)", 549.0,
        57, 27, 25.5, 50.5, 275, 2, 2, 10, "laminate", 4, False, 30,
        shipping_usd=0.0, eta_min_days=1, eta_max_days=3, returns_fee_usd=45.0,
        source_url="https://www.companionlink.com/blog/2026/08/vari-electric-standing-desk-alternatives-4-standing-desks-for-american-buyers-in-2026/",
        checked_at="2026-08-18",
        notes="$549 across all three sizes. 10 desktop finishes, 5 leg colors. Low-profile C legs. "
        "Cable tray sold separately. Shipping/ETA per branchfurniture.com product page and "
        "/pages/shipping (checked 2026-08-18, ZIP 60614): free parcel shipping (orders $90+), "
        "ships in 1-3 business days. CAVEAT — returns_fee_usd=$45 is an ESTIMATE, not a sourced "
        "figure: Branch's standing-desk return fee is a 'Label Fee' computed dynamically in their "
        "return portal by item/location (see /pages/returns), no flat number is published. $45 is "
        "interpolated from Branch's own published flat-rate return fees for comparable categories "
        "(Chairs $40/unit, Duo Desk Accessories $9/unit, Larger Accessories $15/unit) as a "
        "boxed-parcel desk sits above chairs in size/weight. Replace with the real portal quote "
        "before treating this as merchant economics.",
    ),
    DeskRecord(
        "D08", "Autonomous", "Autonomous SmartDesk Core (53x29)", 449.0,
        53, 29, 29.4, 48.0, 265, 2, 2, 5, "laminate", 4, False, 30,
        shipping_usd=0.0, eta_min_days=7, eta_max_days=14, returns_fee_usd=0.0,
        source_url="https://www.autonomous.ai/help-center/policies/shipping-policy",
        checked_at="2026-08-21",
        notes="Budget dual-motor entry point. 30-day trial. 5-yr frame / 1-yr top warranty. "
        "Checkout fields per autonomous.ai/help-center (shipping-policy, "
        "shipping-and-delivery/how-long-does-it-take-for-autonomous-to-deliver-a-product, and "
        "trial-return-exchange-policy-us, checked 2026-08-21) plus corroborating aggregate at "
        "standingdeskreference.com/manufacturers/autonomous: free shipping on standard SmartDesk "
        "models, standard delivery 7-14 days (3-5 business day transit after an unstated processing "
        "window, so the 7-14 combined figure is sourced from the aggregator rather than summed from "
        "Autonomous's own pages), free return with a prepaid label within the 30-day trial if "
        "returned in original packaging on time — the return-fee exception (deducted return "
        "shipping / 30% restocking) applies only to XL-tabletop and Corner SmartDesk variants, not "
        "this Core model, so $0 is a real match rather than an estimate.",
    ),
    DeskRecord(
        "D09", "UPLIFT", "UPLIFT V2 (42x30 laminate)", 599.0,
        42, 30, 25.3, 50.9, 355, 2, 3, 15, "laminate", 2, True, 30, noise_db=56,
        shipping_usd=0.0, eta_min_days=1, eta_max_days=4, returns_fee_usd=0.0,
        source_url="https://www.tomsguide.com/reviews/uplift-v2-standing-desk",
        checked_at="2026-08-18",
        notes="From $569-599 for 42x30 laminate. 355lb, 15-yr incl desktop, 3-stage, free return "
        "shipping within 30 days. Programmable keypad +$29 (base has 2-button). Checkout fields "
        "confirmed per upliftdesk.com/shipping and /returns (checked 2026-08-18, ZIP 60614): free "
        "shipping to 48 contiguous states, ships same business day with 1-4 day FedEx Ground "
        "transit from Austin TX, free returns with free return shipping under the 30-day trial.",
    ),
    DeskRecord(
        "D10", "Secretlab", "Secretlab MAGNUS Pro (70x31.5)", 949.0,
        70, 31.5, 25.0, 48.4, 265, 2, 2, 5, "laminate", 4, True, 30, noise_db=50,
        shipping_usd=41.0, eta_min_days=1, eta_max_days=4, returns_fee_usd=41.0,
        source_url="https://standingdeskreference.com/manufacturers/secretlab/",
        checked_at="2026-08-18",
        notes="$749-1300 configured. Integrated power supply column, magnetic cable mgmt. 5-yr "
        "frame/motor, 1-yr electronics. Ships from Utah. Shipping/ETA per secretlab.co/pages/delivery "
        "(checked 2026-08-18, ZIP 60614): ~$41+ shipping (varies by location, calculated at "
        "checkout, not free), processed within 1 working day + delivered within 3 more. "
        "CAVEAT — returns_fee_usd=$41 is an ESTIMATE, not a sourced figure: per secretlab.co US "
        "Return Policy PDF (effective 2026-07-13), restocking fee is $0 but 'you are responsible "
        "for all shipping fees and costs' on return, no fixed dollar figure is published. $41 is "
        "carried over from Secretlab's own stated inbound shipping baseline ('generally costs "
        "around US$41 or more') as the best available proxy for a same-size outbound parcel. "
        "Replace with the real return-label quote before treating this as merchant economics.",
    ),
    DeskRecord(
        "D11", "Ergonofis", "Ergonofis Sway (60x30 solid wood)", 1295.0,
        60, 30, 24.5, 50.0, 300, 2, 3, 10, "solid_ash", 4, True, 30,
        shipping_usd=0.0, eta_min_days=7, eta_max_days=28, returns_fee_usd=250.0,
        source_url="https://www.bsuperb.com/top-11-standing-desks-with-best-warranty-for-home-office-use-in-the-us-2026/",
        checked_at="2026-08-18",
        notes="Premium solid wood, 10-yr warranty tier. Made in Canada; long lead times confirmed. "
        "Checkout fields per ergonofis.com/pages/shipping and /pages/30-day-trial (checked "
        "2026-08-18, ZIP 60614): free shipping over $250, Sway Desk order processing is 5-20 "
        "business days plus 2-8 day delivery transit (min/max combined = 7-28 days), flat-rate "
        "$250 return fee per standing desk.",
    ),
]

# --------------------------------------------------------------------------
# FOCAL — fictional design-partner merchant.
#
# Deliberately a mid-pack contender that is weak precisely where the arms act:
# paid shipping, a long STATED lead time, and an incomplete attribute set.
# Those three weaknesses are the headroom the interventions have to work with.
# Target baseline selection rate: 0.10-0.20.
# --------------------------------------------------------------------------

FOCAL = DeskRecord(
    FOCAL_ID, "Arbor", "Arbor Ridge 48 (48x24 bamboo)", 499.0,
    48, 24, 25.0, 51.0, 360, 2, 3, 15, "bamboo", 3, True, 30,
    shipping_usd=19.0, eta_min_days=7, eta_max_days=10, returns_fee_usd=39.0,
    source_url="FICTIONAL — stands in for a design partner",
    checked_at="2026-08-19",
    notes="Fictional merchant, deliberately redesigned across two passes (2026-08-18, 2026-08-19) "
    "after real-probe testing on the verified catalog. Pass 1 (2026-08-18) fixed width (55x28->48x24, "
    "was categorically excluding ~35% of mandates on a width<=48in constraint unrelated to any arm) "
    "and moderated the severity of the deliberately-weak arm-target fields (shipping $79->$19, eta "
    "12-24->7-10 days, returns $129->$39 — still clearly worse than the real market's norm, SLA-arm "
    "headroom intact, but no longer a Pareto-catastrophic outlier) plus unset noise_db (was 48) to "
    "restore genuine headroom for the attribute-completion arm. That pass raised baseline off 0.000 "
    "but only to 0.017 (1/60) on a 60-mandate real full run: pass-1 priced Arbor at $549, which "
    "re-triggered a hard-disqualification the $349 test had accidentally avoided — 18/60 (30%) of "
    "real mandates carry a fixed 'can't go over $400' budget constraint, and $549 fails it outright, "
    "before any comparison happens. Separately, even in eligible mandates Arbor kept losing to "
    "whichever FlexiSpot SKU (D02/D03/D04) was nearest its price, because FlexiSpot standardizes "
    "15-year warranties and 220-440lb weight capacity across its entire line — Arbor's prior 10yr/"
    "325lb was below that floor regardless of which SKU it was compared against. Pass 2 "
    "(2026-08-19) is a joint fix, not another single-field guess: price $549->$359 clears the $400 "
    "budget tier and undercuts D02 ($369) specifically; warranty 10->15yr matches FlexiSpot's "
    "line-wide standard instead of sitting below it; weight_capacity_lb 325->360 edges past D02's "
    "355lb. Checked against D02 with this spec: Arbor now wins on price and weight and ties on "
    "warranty; D02 only leads on the three arm-target commercial-terms fields (shipping/eta/returns), "
    "which is exactly where it is meant to still be weaker. width_in/depth_in (48x24) and "
    "height_max_in (51.0, tallest in the real catalog, deliberately calibrated — see the module "
    "docstring's 50.5in note) are untouched from pass 1. Pass 2's $359 price ran once (real 60-mandate "
    "full run, 2026-08-19): baseline improved to 0.067 with real positive selection lifts on the "
    "shipping and SLA arms (P(effect>0)=1.000 both), but the RANKED ACTIONS economics came back "
    "REJECTED_VALUE across every arm, including those two — not because the interventions are bad, "
    "but because $359 is below the synthetic demo_economics() cost floor (cogs $305 + fulfillment "
    "$74 + ~2.9% payment + ~$12.60 expected return cost ≈ $403 before any margin), so every order "
    "loses money by construction regardless of which lever drives the volume. Pass 3 (2026-08-19) "
    "raises price 359->499 for a real, comfortable margin above that floor (~$93/order) while "
    "keeping pass-2's weight/warranty gains — deliberately accepting loss of the $400-budget-tier "
    "mandate segment (~30% of mandates) rather than repeat the sub-cost pricing mistake. $499 "
    "happens to match FlexiSpot E7 Pro (D03) exactly, a known, checkable real comp. Selection-effect "
    "results from the $359 run remain valid evidence (the lift itself was real); only that run's "
    "dollar-value ranking should be discarded. Re-verify both baseline AND that contribution margin "
    "is positive before treating any arm's economics as reportable — check both, this project has "
    "now broken on each dimension separately at least once.",
    fictional=True,
)


def _to_product(r: DeskRecord) -> ProductState:
    attrs: dict = {
        "width_in": r.width_in,
        "depth_in": r.depth_in,
        "height_min_in": r.height_min_in,
        "height_max_in": r.height_max_in,
        "weight_capacity_lb": r.weight_capacity_lb,
        "motors": r.motors,
        "leg_stages": r.leg_stages,
        "warranty_years": r.warranty_years,
        "top_material": r.top_material,
        "presets": r.presets,
        "cable_management": r.cable_management,
    }
    if r.noise_db is not None:
        attrs["noise_db"] = r.noise_db  # genuinely absent for some brands — that is data
    return ProductState(
        product_id=r.product_id,
        brand=r.brand,
        title=r.title,
        category="standing_desk",
        price_cents=cents(r.price_usd),
        shipping=Shipping(
            price_cents=cents(r.shipping_usd or 0),
            eta_min_days=r.eta_min_days or 0,
            eta_max_days=r.eta_max_days or 0,
        ),
        returns=Returns(window_days=r.returns_window_days, fee_cents=cents(r.returns_fee_usd or 0)),
        warranty=Warranty(duration_months=r.warranty_years * 12),
        attributes=attrs,
        is_merchant_product=r.fictional,
    )


def all_records() -> list[DeskRecord]:
    return [*COMPETITORS, FOCAL]


def verification_report() -> dict:
    records = all_records()
    missing = {r.product_id: r.unverified_fields() for r in records if r.unverified_fields()}
    total_missing = sum(len(v) for v in missing.values())
    return {
        "products": len(records),
        "real": sum(1 for r in records if not r.fictional),
        "fictional": sum(1 for r in records if r.fictional),
        "products_with_gaps": len(missing),
        "total_unverified_fields": total_missing,
        "missing_by_product": missing,
        "ready_for_real_run": total_missing == 0,
    }


def build_catalog(allow_unverified: bool = False) -> list[ProductState]:
    report = verification_report()
    if not report["ready_for_real_run"] and not allow_unverified:
        raise UnverifiedCatalogError(
            f"{report['total_unverified_fields']} fields across "
            f"{report['products_with_gaps']} products still need checkout verification "
            f"(shipping cost, lead time, return fee). Fill them in acop/catalog_v1.py, "
            f"or pass allow_unverified=True to smoke-test the machinery with zeros."
        )
    return [_to_product(r) for r in all_records()]


def export_sources_csv(path: Path | str = FIXTURES / "catalog_sources_v1.csv") -> Path:
    rows = ["product_id,brand,title,field,value,status,source_url,checked_at,notes"]
    for r in all_records():
        status_default = "FICTIONAL" if r.fictional else "VERIFIED"
        for fname in (
            "price_usd", "width_in", "depth_in", "height_min_in", "height_max_in",
            "weight_capacity_lb", "motors", "leg_stages", "warranty_years",
            "top_material", "presets", "cable_management", "returns_window_days",
            "noise_db", "shipping_usd", "eta_min_days", "eta_max_days", "returns_fee_usd",
        ):
            v = getattr(r, fname)
            status = status_default
            if v is None:
                status = "UNVERIFIED — fill from checkout page"
            title = r.title.replace(",", ";")
            notes = r.notes.replace(",", ";")
            rows.append(
                f'{r.product_id},{r.brand},"{title}",{fname},'
                f'{"" if v is None else v},{status},{r.source_url},{r.checked_at},"{notes}"'
            )
    Path(path).write_text("\n".join(rows))
    return Path(path)


def save_json(path: Path | str = FIXTURES / "catalog_v1.json") -> Path:
    products = build_catalog(allow_unverified=True)
    Path(path).write_text(
        json.dumps(
            {
                "version": "v1",
                "category": "standing_desk",
                "generated_at": "2026-08-18",
                "verification": verification_report(),
                "products": [p.model_dump() for p in products],
            },
            indent=2,
        )
    )
    return Path(path)
