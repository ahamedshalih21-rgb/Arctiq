"""
Arctiq — Early Warning Service
===================================
Implements a two-stage spoilage warning system on top of the existing PyTorch LSTM model.

IMPORTANT — Technical Honesty:
-------------------------------
The PyTorch LSTM model predicts `hours_until_spoilage` based on sequence data (360 timesteps x 10 features).
This prediction is used directly as the model-driven operational reference.

The ~12-hour EARLY WARNING is NOT presented as an LSTM-validated ML prediction.
It is a projected risk horizon calculated from:
  - Current LSTM-predicted hours remaining
  - Temperature trend (slope over recent readings)
  - Humidity trend (slope over recent readings)
  - Product perishability factor (product-type multiplier)
  - Temperature excursion magnitude

This projection helps operators prepare before the model reaches its critical
action threshold (~6.4h in observed demo operation).

Operational State Hierarchy:
-------------------------------
The hierarchy integrates both the LSTM model output and the trend projection.
States are never contradictory: if trend projection gives <12h but model says
>48h with flat trends, the model reading takes precedence for definitive status.

| LSTM Hours Remaining | Operational State |
|--------------------|-------------------|
| > 48h              | SAFE              |
| 24–48h             | MONITOR           |
| 12–24h             | WATCH             |
| ≤ 12h (model) OR projected_horizon ≤ 12h (trend) | EARLY_WARNING |
| 6.4h–12h           | HIGH_RISK         |
| ≤ 6.4h             | CRITICAL          |
| ≤ 0h               | SPOILED           |

The projected horizon is labeled as "Projected risk horizon (trend-based estimate)"
in all API responses to distinguish it from the model's direct output.
"""

from typing import Optional

# ── Operational thresholds ─────────────────────────────────────────────────────
# Standardized to 12-hour intervention window (>24h LOW, 12-24h MEDIUM, <=12h HIGH)
SAFE_HOURS     = 48.0   # above this: SAFE
MONITOR_HOURS  = 24.0   # 24–48h: MONITOR (LOW risk)
WATCH_HOURS    = 18.0   # 12–24h: WATCH / MEDIUM risk
CRITICAL_HOURS = 12.0   # <= 12h: CRITICAL action window (HIGH risk intervention)

# Early warning projection threshold (trend-based projection)
EARLY_WARNING_PROJECTION_HOURS = 16.0

# Minimum readings needed to compute a meaningful trend
MIN_TREND_WINDOW = 6

# Weight of trend-based projection vs model hours when computing projected horizon
# Higher weight = trend projection has more influence on the projected horizon estimate
TREND_PROJECTION_WEIGHT = 0.40  # 40% trend, 60% model direct output


def compute_temperature_slope(history: list) -> float:
    """
    Compute the rate of temperature change (°C per reading tick).
    Uses the last MIN_TREND_WINDOW readings.
    Positive slope = temperature rising (bad for perishables).
    Returns 0.0 if insufficient history.
    """
    if len(history) < MIN_TREND_WINDOW:
        return 0.0
    recent = [r["temperature"] for r in history[-MIN_TREND_WINDOW:]]
    n = len(recent)
    # Simple linear regression slope
    x_mean = (n - 1) / 2.0
    y_mean = sum(recent) / n
    numerator   = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def compute_humidity_slope(history: list) -> float:
    """
    Compute rate of humidity change (% per reading tick).
    For humidity, large deviation from ideal in either direction is harmful.
    Returns signed slope; caller interprets direction per product.
    """
    if len(history) < MIN_TREND_WINDOW:
        return 0.0
    recent = [r["humidity"] for r in history[-MIN_TREND_WINDOW:]]
    n = len(recent)
    x_mean = (n - 1) / 2.0
    y_mean = sum(recent) / n
    numerator   = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def compute_projected_horizon(
    model_hours: float,
    temp_slope: float,
    humidity_slope: float,
    ideal_temp: float,
    current_temp: float,
    ideal_humidity: float,
    current_humidity: float,
    perishability_factor: float,
) -> float:
    """
    Estimate a projected spoilage risk horizon that accounts for sensor trends.

    This is NOT the direct LSTM model output. It is a trend-extrapolation that gives
    operators an earlier indication of developing risk.

    Method:
      - Start with the model's predicted hours_remaining
      - Compute a trend penalty based on temperature/humidity deterioration rate
      - Apply product perishability to amplify sensitivity for more fragile products
      - Blend model output and trend-adjusted estimate

    The result is labeled "projected_risk_horizon_hours" in the API response
    to clearly distinguish it from the model's direct prediction.

    Parameters:
        model_hours          — LSTM predicted hours_until_spoilage
        temp_slope           — °C per tick, positive = rising
        humidity_slope       — % per tick
        ideal_temp           — product's ideal storage temperature
        current_temp         — current EMA-smoothed temperature
        ideal_humidity       — product's ideal storage humidity
        current_humidity     — current EMA-smoothed humidity
        perishability_factor — product multiplier (1.0 = normal, >1 = more sensitive)

    Returns:
        projected_horizon_hours (float) — always >= 0
    """
    # Temperature excursion from ideal (always positive)
    temp_excursion = max(0.0, current_temp - ideal_temp)

    # Humidity deviation from ideal
    hum_deviation = abs(current_humidity - ideal_humidity)

    # Trend penalties per unit of slope magnitude
    # A positive temp slope means temperature is rising, shortening safe time
    # Scale: 1°C/tick rising trend reduces projected horizon by ~4h
    temp_trend_impact = max(0.0, temp_slope) * 4.0

    # Humidity drifting away reduces horizon too, but less dramatically
    # Scale: 1%/tick humidity change reduces projected horizon by ~1h
    hum_trend_impact = abs(humidity_slope) * 1.0

    # Current excursion penalty (independent of trend)
    # A 3°C excursion above ideal reduces horizon by ~3 effective hours
    excursion_penalty = temp_excursion * 1.0 + hum_deviation * 0.05

    # Total trend-based reduction in hours (before perishability scaling)
    raw_trend_reduction = temp_trend_impact + hum_trend_impact + excursion_penalty

    # Scale by perishability: milk (1.8) degrades faster under the same conditions
    scaled_reduction = raw_trend_reduction * perishability_factor

    # Trend-adjusted estimate
    trend_adjusted = max(0.0, model_hours - scaled_reduction)

    # Blend: model output + trend adjustment
    projected = (
        (1.0 - TREND_PROJECTION_WEIGHT) * model_hours
        + TREND_PROJECTION_WEIGHT * trend_adjusted
    )

    return max(0.0, round(projected, 1))


def determine_operational_state(
    model_hours: float,
    projected_horizon: float,
) -> str:
    """
    Determine the operational warning state.

    Uses BOTH model hours and projected horizon to avoid contradictory states:
    - The state escalates to EARLY_WARNING if projected_horizon <= 12h,
      even if model_hours is still > 12h (trend shows deteriorating conditions)
    - The state never shows SAFE if projected_horizon is critical

    This prevents the API from returning warning_stage=SAFE while
    projected_risk_horizon=8h simultaneously.

    Returns one of: SAFE | MONITOR | WATCH | EARLY_WARNING | HIGH_RISK | CRITICAL | SPOILED
    """
    if model_hours <= 0.0:
        return "SPOILED"

    if model_hours <= CRITICAL_HOURS:
        return "CRITICAL"

    # If model says > critical but projected horizon is <= critical, HIGH_RISK
    if projected_horizon <= CRITICAL_HOURS:
        return "HIGH_RISK"

    if model_hours <= WATCH_HOURS or projected_horizon <= EARLY_WARNING_PROJECTION_HOURS:
        # Both the 6.4–12h model range and the projected ≤12h trend trigger HIGH_RISK
        if model_hours <= WATCH_HOURS and projected_horizon <= CRITICAL_HOURS:
            return "HIGH_RISK"
        return "EARLY_WARNING"

    if model_hours <= MONITOR_HOURS:
        return "WATCH"

    if model_hours <= SAFE_HOURS:
        return "MONITOR"

    return "SAFE"


def assess_early_warning(
    produce_type: str,
    model_hours: float,
    history: list,
    ideal_temp: float,
    ideal_humidity: float,
    current_temp: float,
    current_humidity: float,
    perishability_factor: float,
) -> dict:
    """
    Full early warning assessment for a produce batch.

    Returns a structured dict with:
      warning_stage              — operational state string
      model_hours_remaining      — direct PyTorch LSTM output (model-driven reference)
      projected_risk_horizon_hours — trend-based early warning estimate
      temp_slope_per_tick        — temperature trend (°C/tick)
      humidity_slope_per_tick    — humidity trend (%/tick)
      temp_excursion_c           — how far above ideal temp (°C)
      humidity_deviation_pct     — how far from ideal humidity (%)
      early_warning_active       — bool: true when EARLY_WARNING or worse
      critical_action_active     — bool: true when CRITICAL (model-driven threshold)
      warning_description        — human-readable text for the current stage
      horizon_note               — disclaimer text for the projected horizon

    IMPORTANT: The API response must always include horizon_note to ensure
    the projected horizon is never mistaken for an LSTM-validated ML prediction.
    """
    temp_slope = compute_temperature_slope(history)
    hum_slope  = compute_humidity_slope(history)

    projected = compute_projected_horizon(
        model_hours=model_hours,
        temp_slope=temp_slope,
        humidity_slope=hum_slope,
        ideal_temp=ideal_temp,
        current_temp=current_temp,
        ideal_humidity=ideal_humidity,
        current_humidity=current_humidity,
        perishability_factor=perishability_factor,
    )

    state = determine_operational_state(model_hours, projected)

    # Human-readable descriptions per state
    descriptions = {
        "SPOILED":       "Batch has reached or exceeded predicted spoilage threshold. Remove from inventory.",
        "CRITICAL":      f"Model-driven critical action window. Predicted {model_hours:.1f}h remaining. Prioritize immediate sale.",
        "HIGH_RISK":     f"Risk is increasing rapidly. Model predicts {model_hours:.1f}h, trend projection indicates deteriorating conditions.",
        "EARLY_WARNING": f"Projected sensor trends indicate potential spoilage risk within approximately {projected:.0f}h. Prepare this batch for priority sale.",
        "WATCH":         f"Model predicts {model_hours:.1f}h remaining. Monitor closely and prepare SmartSell actions.",
        "MONITOR":       f"Model predicts {model_hours:.1f}h remaining. No immediate action required. Continue monitoring.",
        "SAFE":          f"Model predicts {model_hours:.1f}h remaining. Conditions are stable.",
    }

    return {
        "warning_stage":               state,
        "model_hours_remaining":        round(model_hours, 1),
        "projected_risk_horizon_hours": projected,
        "temp_slope_per_tick":          round(temp_slope, 4),
        "humidity_slope_per_tick":      round(hum_slope, 4),
        "temp_excursion_c":             round(max(0.0, current_temp - ideal_temp), 2),
        "humidity_deviation_pct":       round(abs(current_humidity - ideal_humidity), 2),
        "early_warning_active":         state in ("EARLY_WARNING", "HIGH_RISK", "CRITICAL", "SPOILED"),
        "critical_action_active":       state in ("CRITICAL", "SPOILED"),
        "warning_description":          descriptions.get(state, ""),
        "horizon_note": (
            "Projected risk horizon is a trend-based estimate derived from sensor slope, "
            "temperature excursion, and product perishability. It is not the PyTorch LSTM model's "
            "validated prediction output. The model-driven critical action threshold is "
            f"approximately {CRITICAL_HOURS}h based on observed operational behaviour."
        ),
    }
