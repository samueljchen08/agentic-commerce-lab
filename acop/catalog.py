"""Catalog loading and the placeholder fixture.

The real catalog lives in `fixtures/catalog_v1.json` and is built by hand from
source-verified product pages, with every public fact recorded in
`fixtures/catalog_sources_v1.csv`.

`placeholder_catalog()` exists so `make sim` runs before you have done that
work. It is NOT source-verified and must never appear in anything shown to a
merchant or investor. Numbers in it are representative of the category's shape,
not claims about any real product.
"""
from __future__ import annotations

import json
from pathlib import Path

from .domain import ProductState, Returns, Shipping, Warranty, cents

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

# Attributes an agent can actually reason over for this category.
DESK_ATTRIBUTES = (
    "width_in",
    "depth_in",
    "height_min_in",
    "height_max_in",
    "weight_capacity_lb",
    "motors",
    "leg_stages",
    "warranty_years",
    "noise_db",
    "top_material",
    "presets",
    "cable_management",
)


def load_catalog(path: Path | str = FIXTURES / "catalog_v1.json") -> list[ProductState]:
    """Load the source-verified catalog. Fails loudly if it is not there —
    silently falling back to the placeholder is how fake data ends up in a
    merchant deck."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Build it from real product pages "
            f"(see fixtures/CATALOG_INSTRUCTIONS.md), or call placeholder_catalog() "
            f"explicitly if you are only smoke-testing the machinery."
        )
    raw = json.loads(path.read_text())
    return [ProductState(**p) for p in raw["products"]]


def save_catalog(products: list[ProductState], path: Path | str, version: str = "v1") -> Path:
    path = Path(path)
    path.write_text(
        json.dumps(
            {"version": version, "category": "standing_desk",
             "products": [p.model_dump() for p in products]},
            indent=2,
        )
    )
    return path


def _desk(
    pid: str, brand: str, title: str, price: float, ship: float, eta: tuple[int, int],
    ret_days: int, ret_fee: float, w: float, d: float, h_min: float, h_max: float,
    cap: int, motors: int, stages: int, warranty_y: int, noise: int, top: str,
    presets: int, cable: bool, focal: bool = False,
) -> ProductState:
    return ProductState(
        product_id=pid, brand=brand, title=title, category="standing_desk",
        price_cents=cents(price),
        shipping=Shipping(price_cents=cents(ship), eta_min_days=eta[0], eta_max_days=eta[1]),
        returns=Returns(window_days=ret_days, fee_cents=cents(ret_fee)),
        warranty=Warranty(duration_months=warranty_y * 12),
        attributes={
            "width_in": w, "depth_in": d, "height_min_in": h_min, "height_max_in": h_max,
            "weight_capacity_lb": cap, "motors": motors, "leg_stages": stages,
            "warranty_years": warranty_y, "noise_db": noise, "top_material": top,
            "presets": presets, "cable_management": cable,
        },
        is_merchant_product=focal,
    )


PLACEHOLDER_FOCAL_ID = "D05"


def placeholder_catalog() -> list[ProductState]:
    """PLACEHOLDER — not source-verified. Smoke-testing only.

    Shaped to the category's real structure: wide price dispersion, shipping
    from free to $199, lead times from 3 days to 6 weeks, and genuine tradeoffs
    so that no single desk dominates every mandate.
    """
    return [
        #     id    brand         title                    price  ship   eta      ret fee   w    d   hmin  hmax  cap  mot st  wty noise top        pre cable
        _desk("D01", "Basecamp",  "Basecamp Lift 48",       299,  79,  (10, 21), 30,  149,  48, 24, 28.0, 47.5, 154, 1, 2,  2, 55, "laminate",   0, False),
        _desk("D02", "Cadence",   "Cadence C1 Adjustable",  379,   0,  (14, 28), 30,   99,  55, 28, 27.5, 46.0, 176, 1, 2,  3, 52, "laminate",   2, False),
        _desk("D03", "Meridian",  "Meridian Core 55",       449,  49,  (7, 14),  60,    0,  55, 28, 25.5, 50.5, 220, 2, 2,  5, 50, "laminate",   3, True),
        _desk("D04", "Northfield","Northfield Studio 60",   699,   0,  (21, 42), 30,  179,  60, 30, 25.0, 51.0, 265, 2, 3,  7, 48, "bamboo",     4, True),
        # FOCAL. Deliberately a mid-pack contender: eligible for most mandates,
        # but weak exactly where the interventions act — paid shipping, a long
        # lead time, and a return fee. If the focal is weak everywhere the
        # baseline collapses and nothing is measurable; if it dominates, nothing
        # can move it. Target baseline selection: 0.10-0.20.
        _desk("D05", "Arbor",     "Arbor Ridge 55",         579,  79,  (12, 24), 30,  129,  48, 28, 25.0, 51.0, 285, 2, 3,  6, 48, "bamboo",     3, True, focal=True),
        _desk("D06", "Vantage",   "Vantage Pro 72",         949,   0,  (18, 35), 60,    0,  72, 30, 24.5, 52.0, 355, 2, 3, 10, 45, "solid_oak",  4, True),
        _desk("D07", "Tempo",     "Tempo Slim 42",          329,   0,  (5, 10),  30,  129,  42, 24, 28.5, 47.0, 150, 1, 2,  2, 56, "laminate",   0, False),
        _desk("D08", "Kestrel",   "Kestrel Frame 60",       549,  59,  (10, 20), 45,   99,  60, 30, 25.0, 50.5, 275, 2, 3,  7, 47, "laminate",   3, True),
        _desk("D09", "Halden",    "Halden Nordic 55",      1149,   0,  (28, 56), 45,    0,  55, 28, 24.0, 51.5, 300, 2, 3, 12, 44, "solid_ash",  4, True),
        _desk("D10", "Pilot",     "Pilot Compact 40",       279,  39,  (7, 14),  30,   89,  40, 22, 29.0, 46.5, 132, 1, 2,  2, 58, "laminate",   0, False),
        _desk("D11", "Summit",    "Summit HD 72",           879,  49,  (21, 42), 30,  199,  72, 30, 25.5, 51.0, 400, 2, 3,  8, 46, "laminate",   4, True),
        _desk("D12", "Lumen",     "Lumen Air 48",           499,   0,  (3, 7),   30,  119,  48, 27, 27.0, 48.5, 200, 2, 2,  5, 51, "bamboo",     2, True),
    ]


def catalog_shape_report(products: list[ProductState]) -> dict:
    """Pre-flight check on a catalog before you spend probes on it.

    A catalog with no dispersion produces no measurable effects. Run this
    against your real fixture before building the mandate set.
    """
    prices = [p.price_cents for p in products]
    ships = [p.shipping.price_cents for p in products]
    etas = [(p.shipping.eta_min_days + p.shipping.eta_max_days) / 2 for p in products]
    caps = [float(p.attributes["weight_capacity_lb"]) for p in products]
    widths = [float(p.attributes["width_in"]) for p in products]
    h_max = [float(p.attributes["height_max_in"]) for p in products]

    checks = {
        "price_spread_ratio": round(max(prices) / min(prices), 2),
        "free_shipping_count": sum(1 for s in ships if s == 0),
        "paid_shipping_count": sum(1 for s in ships if s > 0),
        "lead_time_days_min": round(min(etas), 1),
        "lead_time_days_max": round(max(etas), 1),
        "capacity_range_lb": [min(caps), max(caps)],
        "width_range_in": [min(widths), max(widths)],
        "meets_tall_constraint": sum(1 for h in h_max if h >= 51),
        "meets_heavy_constraint": sum(1 for c in caps if c >= 250),
        "meets_narrow_constraint": sum(1 for w in widths if w <= 48),
    }
    warnings = []
    if checks["price_spread_ratio"] < 2.5:
        warnings.append("price spread below 2.5x — effects will be hard to resolve")
    if checks["free_shipping_count"] < 3 or checks["paid_shipping_count"] < 3:
        warnings.append("shipping is not varied — the free-shipping arm has no headroom")
    if checks["lead_time_days_max"] - checks["lead_time_days_min"] < 10:
        warnings.append("lead times too similar — the delivery-SLA arm has no headroom")
    for name in ("meets_tall_constraint", "meets_heavy_constraint", "meets_narrow_constraint"):
        if not 2 <= checks[name] <= len(products) - 2:
            warnings.append(f"{name}: {checks[name]}/{len(products)} — constraint is trivial or impossible")
    checks["warnings"] = warnings
    return checks
