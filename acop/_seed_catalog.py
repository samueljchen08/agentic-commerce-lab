"""Pilot category fixture: carry-on luggage.

20 canonical competing products. One is the design-partner merchant's SKU
(`meridian-cx`). Attributes are the ones a buyer agent can actually reason
over: weight, capacity, shell material, wheels, lock, airline compliance.
"""
from __future__ import annotations

from .domain import (
    ProductEconomics,
    ProductState,
    Returns,
    Shipping,
    Warranty,
    cents,
)

MERCHANT_PRODUCT_ID = "meridian-cx"


def _p(
    pid: str,
    brand: str,
    title: str,
    price: float,
    ship_price: float,
    eta: tuple[int, int],
    ret_days: int,
    warranty_months: int,
    weight_lb: float,
    capacity_l: float,
    shell: str,
    wheels: int,
    tsa_lock: bool,
    expandable: bool,
    is_merchant: bool = False,
) -> ProductState:
    return ProductState(
        product_id=pid,
        brand=brand,
        title=title,
        category="carry_on_luggage",
        attributes={
            "weight_lb": weight_lb,
            "capacity_l": capacity_l,
            "shell_material": shell,
            "wheels": wheels,
            "tsa_lock": tsa_lock,
            "expandable": expandable,
            "carry_on_compliant": True,
        },
        price_cents=cents(price),
        shipping=Shipping(
            price_cents=cents(ship_price), eta_min_days=eta[0], eta_max_days=eta[1]
        ),
        returns=Returns(window_days=ret_days),
        warranty=Warranty(duration_months=warranty_months),
        is_merchant_product=is_merchant,
    )


def build_catalog() -> list[ProductState]:
    return [
        _p(MERCHANT_PRODUCT_ID, "Meridian", "Meridian CX Carry-On", 299, 14, (4, 6), 30, 60, 7.4, 40, "polycarbonate", 4, True, True, is_merchant=True),
        _p("aeris-lite", "Aeris", "Aeris Lite 22", 189, 0, (3, 5), 45, 24, 6.1, 38, "polycarbonate", 4, True, False),
        _p("voyage-pro", "Voyage", "Voyage Pro Hardside", 349, 0, (2, 4), 60, 120, 7.9, 42, "aluminum", 4, True, True),
        _p("nomadica-22", "Nomadica", "Nomadica 22 Cabin", 245, 9, (5, 8), 30, 24, 8.2, 41, "polycarbonate", 4, True, True),
        _p("terra-carry", "Terra", "Terra Carry Softside", 159, 0, (4, 7), 30, 12, 6.8, 36, "ballistic_nylon", 4, False, True),
        _p("stratus-one", "Stratus", "Stratus One", 279, 0, (2, 3), 45, 60, 7.1, 39, "polycarbonate", 4, True, False),
        _p("kestrel-cabin", "Kestrel", "Kestrel Cabin Spinner", 219, 12, (5, 9), 30, 36, 7.6, 40, "abs", 4, True, True),
        _p("orion-alu", "Orion", "Orion Aluminum 21", 495, 0, (3, 5), 30, 120, 9.8, 37, "aluminum", 4, True, False),
        _p("baseline-22", "Baseline", "Baseline 22 Hardshell", 129, 0, (6, 10), 30, 12, 8.9, 38, "abs", 4, False, False),
        _p("pathfinder-c", "Pathfinder", "Pathfinder C-Series", 329, 0, (2, 4), 60, 999, 7.2, 40, "polycarbonate", 4, True, True),
        _p("halcyon-go", "Halcyon", "Halcyon Go 21", 265, 8, (4, 6), 30, 36, 6.9, 37, "polycarbonate", 4, True, False),
        _p("lumen-carry", "Lumen", "Lumen Carry 22", 199, 0, (3, 6), 45, 24, 7.3, 39, "polycarbonate", 4, True, True),
        _p("atlas-cabin", "Atlas", "Atlas Cabin Trolley", 289, 15, (5, 8), 30, 60, 8.4, 43, "polycarbonate", 4, True, True),
        _p("cirrus-ultra", "Cirrus", "Cirrus Ultralight", 229, 0, (4, 7), 30, 24, 5.4, 34, "polycarbonate", 4, True, False),
        _p("granite-22", "Granite", "Granite 22 Expedition", 379, 0, (3, 5), 60, 999, 9.1, 44, "polycarbonate", 4, True, True),
        _p("wayfare-s", "Wayfare", "Wayfare S Softside", 149, 7, (5, 9), 30, 12, 6.4, 35, "ballistic_nylon", 2, False, True),
        _p("northbound-21", "Northbound", "Northbound 21", 259, 0, (3, 5), 45, 60, 7.7, 38, "polycarbonate", 4, True, False),
        _p("apex-cabin", "Apex", "Apex Cabin Pro", 419, 0, (2, 3), 60, 120, 8.0, 41, "aluminum", 4, True, True),
        _p("drift-carry", "Drift", "Drift Carry 22", 179, 0, (5, 8), 30, 24, 7.0, 37, "abs", 4, True, False),
        _p("summit-c22", "Summit", "Summit C22", 309, 0, (3, 6), 45, 60, 7.5, 40, "polycarbonate", 4, True, True),
    ]


def merchant_economics() -> dict[str, ProductEconomics]:
    """Only the design partner's own SKU has real economics. That is correct --
    you never have a competitor's COGS, and you must not pretend to."""
    return {
        MERCHANT_PRODUCT_ID: ProductEconomics(
            product_id=MERCHANT_PRODUCT_ID,
            cogs_cents=cents(148),
            fulfillment_cents=cents(41),
            payment_cost_bps=290,
            baseline_return_rate=0.09,
            return_cost_cents=cents(22),
        )
    }
