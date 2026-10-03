"""
Arctiq — SmartSell Decision Engine
=======================================
Calculates sell priority scores and dynamic pricing recommendations for
produce batches based on spoilage risk, inventory exposure, demand, and
expected financial loss.

SCORING FORMULA:
  Sell Priority Score (0–100) =
    0.35 × Spoilage Urgency      (time pressure)
    + 0.20 × Waste Exposure      (financial risk from spoilage)
    + 0.15 × Inventory Exposure  (quantity pressure)
    + 0.15 × Demand Opportunity  (ability to move stock quickly)
    + 0.15 × Financial Exposure  (purchase cost at risk)

  All component scores are normalized to 0–100 before weighting.
  Final score is clamped to [0, 100].

PRICING LOGIC:
  Base discount = f(spoilage urgency, inventory pressure)
  Demand adjustment = reduces discount when demand is high
  Floor = purchase_cost_per_kg (only breached when clearance is economically preferable)
  Ceiling = market_price_per_kg (never recommend above market)

PRIORITY LEVELS:
  80–100: SELL NOW
  60–79:  SELL SOON
  40–59:  PROMOTE
  0–39:   HOLD

DEMAND INTERPRETATION:
  80–100: High demand
  50–79:  Medium demand
  20–49:  Low demand
"""

import math
from typing import Optional

# ── Priority level thresholds ──────────────────────────────────────────────────
PRIORITY_SELL_NOW  = 80
PRIORITY_SELL_SOON = 60
PRIORITY_PROMOTE   = 40

# ── Spoilage urgency curve ─────────────────────────────────────────────────────
# Below this many hours, urgency is at maximum (100)
URGENCY_CRITICAL_HOURS = 12.0  # 12-hour intervention window
# Above this many hours, urgency is at minimum (0)
URGENCY_SAFE_HOURS = 48.0

# ── Pricing constraints ────────────────────────────────────────────────────────
MAX_DISCOUNT_FRACTION   = 0.45   # Never discount more than 45% off market price
MIN_MARGIN_ON_COST      = 0.05   # Prefer at least 5% above purchase cost
# Below-cost threshold: only go below cost if expected loss from spoilage is
# greater than the controlled loss from clearance
BELOW_COST_WASTE_MULTIPLIER = 1.10  # 10% buffer before recommending below-cost sale


def calculate_spoilage_urgency(model_hours: float) -> float:
    """
    Normalized urgency score 0–100 based on model-predicted hours remaining.
    Uses a non-linear curve: urgency rises steeply as hours fall below ~12h.

    At >= URGENCY_SAFE_HOURS: urgency = 0
    At URGENCY_CRITICAL_HOURS: urgency ~= 80
    At 0h: urgency = 100
    """
    if model_hours >= URGENCY_SAFE_HOURS:
        return 0.0
    if model_hours <= 0.0:
        return 100.0

    # Non-linear decay: urgency = 100 * (1 - hours/safe_hours)^0.6
    # Power < 1 gives steeper urgency rise at low hours
    raw = 1.0 - (model_hours / URGENCY_SAFE_HOURS)
    urgency = 100.0 * (raw ** 0.6)
    return round(min(100.0, max(0.0, urgency)), 2)


def calculate_spoilage_probability(model_hours: float) -> float:
    """
    Estimate probability of spoilage (0–1) from model-predicted hours.
    Used in waste and financial exposure calculations.
    This is a heuristic mapping, not a probabilistic PyTorch LSTM output.

    At 0h: probability = 1.0
    At URGENCY_SAFE_HOURS: probability ≈ 0.02
    """
    if model_hours <= 0.0:
        return 1.0
    if model_hours >= URGENCY_SAFE_HOURS:
        return 0.02
    # Sigmoid-like curve
    x = 1.0 - (model_hours / URGENCY_SAFE_HOURS)
    return round(min(1.0, max(0.02, x ** 1.5)), 4)


def calculate_expected_waste(
    quantity_kg: float,
    purchase_cost_per_kg: float,
    spoilage_probability: float,
) -> float:
    """
    Expected financial loss if this batch is not sold.
    expected_waste_value = quantity × purchase_cost × spoilage_probability
    Returns value in INR.
    """
    return round(quantity_kg * purchase_cost_per_kg * spoilage_probability, 2)


def calculate_potential_revenue_at_risk(
    quantity_kg: float,
    market_price_per_kg: float,
    spoilage_probability: float,
) -> float:
    """
    Revenue foregone if batch spoils before being sold.
    potential_revenue_at_risk = quantity × market_price × spoilage_probability
    """
    return round(quantity_kg * market_price_per_kg * spoilage_probability, 2)


def calculate_waste_exposure_score(
    expected_waste_value: float,
    max_reference_waste: float = 10000.0,
) -> float:
    """
    Normalized waste exposure score 0–100.
    max_reference_waste: upper reference for normalization (INR).
    Batches with expected waste above this cap at 100.
    """
    score = (expected_waste_value / max_reference_waste) * 100.0
    return round(min(100.0, max(0.0, score)), 2)


def calculate_inventory_exposure_score(
    quantity_kg: float,
    max_reference_qty: float = 300.0,
) -> float:
    """
    Normalized inventory exposure score 0–100.
    Higher when more quantity is still in stock.
    """
    score = (quantity_kg / max_reference_qty) * 100.0
    return round(min(100.0, max(0.0, score)), 2)


def calculate_demand_opportunity_score(demand_score: float) -> float:
    """
    Normalized demand opportunity score 0–100.
    Higher demand = higher score (discounting can realistically move stock quickly).
    demand_score is already 20–100, so we normalize linearly.
    """
    normalized = ((demand_score - 20.0) / 80.0) * 100.0
    return round(min(100.0, max(0.0, normalized)), 2)


def calculate_financial_exposure_score(
    quantity_kg: float,
    purchase_cost_per_kg: float,
    spoilage_probability: float,
    max_reference_financial: float = 15000.0,
) -> float:
    """
    Normalized financial exposure score 0–100.
    Based on the total purchase cost at risk.
    """
    at_risk = quantity_kg * purchase_cost_per_kg * spoilage_probability
    score = (at_risk / max_reference_financial) * 100.0
    return round(min(100.0, max(0.0, score)), 2)


def calculate_sell_priority(
    spoilage_urgency: float,
    waste_exposure: float,
    inventory_exposure: float,
    demand_opportunity: float,
    financial_exposure: float,
) -> float:
    """
    Composite SmartSell Priority Score (0–100).

    Weights:
      0.35 — Spoilage Urgency:    time pressure is the dominant factor
      0.20 — Waste Exposure:      financial risk from potential spoilage loss
      0.15 — Inventory Exposure:  large quantities create more urgency
      0.15 — Demand Opportunity:  high demand makes discounting effective
      0.15 — Financial Exposure:  purchase cost / invested capital at risk

    Total weight = 1.00
    """
    score = (
        0.35 * spoilage_urgency
        + 0.20 * waste_exposure
        + 0.15 * inventory_exposure
        + 0.15 * demand_opportunity
        + 0.15 * financial_exposure
    )
    return round(min(100.0, max(0.0, score)), 1)


def priority_level_label(score: float) -> str:
    """Map numeric priority score to action label."""
    if score >= PRIORITY_SELL_NOW:
        return "SELL NOW"
    elif score >= PRIORITY_SELL_SOON:
        return "SELL SOON"
    elif score >= PRIORITY_PROMOTE:
        return "PROMOTE"
    else:
        return "HOLD"


def calculate_recommended_price(
    market_price_per_kg: float,
    purchase_cost_per_kg: float,
    spoilage_urgency: float,
    demand_score: float,
    quantity_kg: float,
    expected_waste_value: float,
    model_hours: float,
) -> dict:
    """
    Dynamic pricing engine with economic safety constraints.

    Strategy:
      1. Base discount starts from spoilage urgency (0–45% max)
      2. Inventory pressure adds additional discount when quantity is large
      3. High demand reduces the required discount
      4. Result is bounded: never exceed market price, prefer not to go below cost
      5. Below-cost sale is only recommended when waste loss > clearance loss

    Returns:
        market_price       — reference market price
        purchase_cost      — purchase cost (economic reference/floor)
        recommended_price  — computed recommended selling price (INR/kg)
        discount_percent   — discount off market price
        estimated_margin   — margin above purchase cost (can be negative)
        below_cost         — bool: True if recommended price is below purchase cost
        below_cost_reason  — explanation if below cost (empty string otherwise)
        pricing_rationale  — concise explanation of the pricing decision
    """
    # ── Base discount from urgency ─────────────────────────────────────────────
    # urgency 0–100 → base discount 0–30% of market price
    base_discount_frac = (spoilage_urgency / 100.0) * 0.30

    # ── Inventory pressure adjustment ─────────────────────────────────────────
    # Large quantities add up to an additional 10% discount pressure
    qty_pressure = min(0.10, (quantity_kg / 300.0) * 0.10)

    # ── Demand strength adjustment ─────────────────────────────────────────────
    # High demand reduces required discount (stock will sell without steep cuts)
    # demand 80–100 → up to 8% discount reduction
    # demand 20–49 → up to 5% discount increase
    demand_adjustment = ((demand_score - 50.0) / 50.0) * 0.08

    # ── Combined discount fraction ─────────────────────────────────────────────
    total_discount_frac = base_discount_frac + qty_pressure - demand_adjustment
    total_discount_frac = max(0.0, min(MAX_DISCOUNT_FRACTION, total_discount_frac))

    # ── Recommended price before floor check ──────────────────────────────────
    raw_recommended = market_price_per_kg * (1.0 - total_discount_frac)

    # ── Economic floor check ───────────────────────────────────────────────────
    cost_floor = purchase_cost_per_kg * (1.0 + MIN_MARGIN_ON_COST)
    below_cost = False
    below_cost_reason = ""

    if raw_recommended < cost_floor:
        # Check if controlled loss is preferable to total waste loss
        clearance_loss = (purchase_cost_per_kg - raw_recommended) * quantity_kg
        # If the clearance loss is less than the expected waste, recommend below cost
        if expected_waste_value > clearance_loss * BELOW_COST_WASTE_MULTIPLIER:
            below_cost = True
            below_cost_reason = (
                f"Recommended price is below purchase cost because a controlled clearance "
                f"loss of approx. Rs{clearance_loss:,.0f} is economically preferable to "
                f"an expected total waste loss of Rs{expected_waste_value:,.0f} "
                f"if the batch is not sold."
            )
            recommended_price = max(0.01, raw_recommended)
        else:
            # Protect cost floor: lift price to cost + minimum margin
            recommended_price = cost_floor
    else:
        recommended_price = raw_recommended

    # Never allow zero or negative price
    recommended_price = max(0.01, round(recommended_price, 2))
    discount_percent  = round((1.0 - recommended_price / market_price_per_kg) * 100.0, 1)
    discount_percent  = max(0.0, discount_percent)
    estimated_margin  = round(recommended_price - purchase_cost_per_kg, 2)

    # ── Pricing rationale ─────────────────────────────────────────────────────
    urgency_text = (
        "high urgency" if spoilage_urgency >= 70
        else "moderate urgency" if spoilage_urgency >= 40
        else "low urgency"
    )
    demand_text = (
        "high demand" if demand_score >= 80
        else "moderate demand" if demand_score >= 50
        else "low demand"
    )
    rationale = (
        f"Recommended at Rs{recommended_price:.0f}/kg based on {urgency_text} "
        f"({model_hours:.1f}h model-predicted remaining), "
        f"{demand_text} ({demand_score:.0f}/100), "
        f"and inventory pressure ({quantity_kg:.0f}kg in stock). "
        f"Market price: Rs{market_price_per_kg:.0f}/kg."
    )
    if below_cost_reason:
        rationale += " " + below_cost_reason

    return {
        "market_price_per_kg":    round(market_price_per_kg, 2),
        "purchase_cost_per_kg":   round(purchase_cost_per_kg, 2),
        "recommended_price_per_kg": recommended_price,
        "discount_percent":        discount_percent,
        "estimated_margin_per_kg": estimated_margin,
        "below_cost":              below_cost,
        "below_cost_reason":       below_cost_reason,
        "pricing_rationale":       rationale,
    }


def build_reason_factors(
    spoilage_urgency: float,
    waste_exposure: float,
    inventory_exposure: float,
    demand_opportunity: float,
    financial_exposure: float,
    model_hours: float,
    demand_score: float,
) -> list:
    """
    Generate machine-readable reason factors for a SmartSell recommendation.
    Used by the frontend to display explainable decisions.
    """
    factors = []

    if spoilage_urgency >= 70:
        factors.append(f"High spoilage urgency ({model_hours:.1f}h predicted remaining)")
    elif spoilage_urgency >= 40:
        factors.append(f"Moderate spoilage urgency ({model_hours:.1f}h predicted remaining)")

    if waste_exposure >= 60:
        factors.append("High expected waste exposure")
    elif waste_exposure >= 30:
        factors.append("Moderate waste exposure")

    if inventory_exposure >= 60:
        factors.append("Large quantity remaining in stock")
    elif inventory_exposure >= 30:
        factors.append("Moderate inventory quantity")

    if demand_score >= 80:
        factors.append(f"High market demand ({demand_score:.0f}/100) — discounting will be effective")
    elif demand_score >= 50:
        factors.append(f"Moderate demand ({demand_score:.0f}/100)")
    else:
        factors.append(f"Low demand ({demand_score:.0f}/100) — stronger discount may be needed")

    if financial_exposure >= 60:
        factors.append("Significant purchase cost at risk")
    elif financial_exposure >= 30:
        factors.append("Moderate financial exposure")

    return factors


def generate_smartsell_recommendation(
    produce_type: str,
    display_name: str,
    batch_id: str,
    model_hours: float,
    warning_stage: str,
    projected_horizon: float,
    quantity_kg: float,
    purchase_cost_per_kg: float,
    market_price_per_kg: float,
    demand_score: float,
) -> dict:
    """
    Generate a complete SmartSell recommendation for one batch.

    Integrates:
      - Spoilage urgency (from model hours)
      - Expected waste calculation
      - Sell priority score (composite)
      - Dynamic price recommendation
      - Explainable reason factors

    Returns a recommendation dict suitable for direct API serialization.
    """
    spoilage_prob    = calculate_spoilage_probability(model_hours)
    urgency          = calculate_spoilage_urgency(model_hours)
    expected_waste   = calculate_expected_waste(quantity_kg, purchase_cost_per_kg, spoilage_prob)
    revenue_at_risk  = calculate_potential_revenue_at_risk(quantity_kg, market_price_per_kg, spoilage_prob)
    waste_exp        = calculate_waste_exposure_score(expected_waste)
    inv_exp          = calculate_inventory_exposure_score(quantity_kg)
    demand_opp       = calculate_demand_opportunity_score(demand_score)
    fin_exp          = calculate_financial_exposure_score(quantity_kg, purchase_cost_per_kg, spoilage_prob)

    priority_score   = calculate_sell_priority(urgency, waste_exp, inv_exp, demand_opp, fin_exp)
    priority_action  = priority_level_label(priority_score)
    pricing          = calculate_recommended_price(
        market_price_per_kg=market_price_per_kg,
        purchase_cost_per_kg=purchase_cost_per_kg,
        spoilage_urgency=urgency,
        demand_score=demand_score,
        quantity_kg=quantity_kg,
        expected_waste_value=expected_waste,
        model_hours=model_hours,
    )
    reason_factors   = build_reason_factors(
        urgency, waste_exp, inv_exp, demand_opp, fin_exp, model_hours, demand_score
    )

    return {
        "batch_id":                   batch_id,
        "produce_type":               produce_type,
        "display_name":               display_name,
        "warning_stage":              warning_stage,
        "model_hours_remaining":      round(model_hours, 1),
        "projected_risk_horizon_hours": round(projected_horizon, 1),
        "quantity_kg":                round(quantity_kg, 1),
        "demand_score":               round(demand_score, 1),
        "spoilage_probability":       spoilage_prob,
        "expected_waste_inr":         expected_waste,
        "potential_revenue_at_risk_inr": revenue_at_risk,
        "sell_priority_score":        priority_score,
        "priority_action":            priority_action,
        # Pricing breakdown
        "market_price_per_kg":        pricing["market_price_per_kg"],
        "purchase_cost_per_kg":       pricing["purchase_cost_per_kg"],
        "recommended_price_per_kg":   pricing["recommended_price_per_kg"],
        "discount_percent":           pricing["discount_percent"],
        "estimated_margin_per_kg":    pricing["estimated_margin_per_kg"],
        "below_cost_sale":            pricing["below_cost"],
        "below_cost_reason":          pricing["below_cost_reason"],
        "pricing_rationale":          pricing["pricing_rationale"],
        # Explainability
        "reason_factors":             reason_factors,
        # Component scores (for transparency / debugging)
        "_component_scores": {
            "spoilage_urgency":       urgency,
            "waste_exposure":         waste_exp,
            "inventory_exposure":     inv_exp,
            "demand_opportunity":     demand_opp,
            "financial_exposure":     fin_exp,
        },
    }
