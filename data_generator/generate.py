"""
ColdSense — Synthetic Data Generator
Generates multi-day hourly sensor sequences for three produce types.
Outputs: ../model/data/training_data.csv
"""

import numpy as np
import pandas as pd
import os
import random
from datetime import datetime, timedelta

# ── Reproducibility ────────────────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
random.seed(SEED)

# ── Produce profiles ───────────────────────────────────────────────────────────
PRODUCE_PROFILES = {
    "leafy_greens": {
        "encode": 0,
        "ideal_temp": 3.0,        # °C
        "ideal_humidity": 92.0,   # %
        "base_shelf_life": 72.0,  # hours
        "heat_weight": 4.5,       # degrades fast under heat
        "humidity_weight": 1.5,
        "temp_range": (1.0, 6.0),
        "humidity_range": (82.0, 97.0),
        "temp_std": 0.6,
        "humidity_std": 2.5,
        "door_open_prob": 0.10,
    },
    "tomatoes": {
        "encode": 1,
        "ideal_temp": 13.0,
        "ideal_humidity": 87.0,
        "base_shelf_life": 120.0,
        "heat_weight": 2.5,
        "humidity_weight": 2.0,
        "temp_range": (10.0, 18.0),
        "humidity_range": (78.0, 94.0),
        "temp_std": 0.8,
        "humidity_std": 3.0,
        "door_open_prob": 0.08,
    },
    "potatoes": {
        "encode": 2,
        "ideal_temp": 7.0,
        "ideal_humidity": 87.0,
        "base_shelf_life": 240.0,
        "heat_weight": 1.2,
        "humidity_weight": 3.8,   # very sensitive to humidity
        "temp_range": (3.0, 12.0),
        "humidity_range": (78.0, 95.0),
        "temp_std": 0.7,
        "humidity_std": 3.5,
        "door_open_prob": 0.06,
    },
}

WINDOW = 24          # hours per sequence
SEQUENCES_PER_TYPE = 2000   # → ~6000 total rows
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "model", "data")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "training_data.csv")


def generate_sequence(profile: dict, fault_prob: float = 0.35) -> tuple[list, float]:
    """
    Generate one 24-hour sensor sequence and its label.
    With fault_prob probability, inject a mid-sequence temperature/humidity drift
    to create diverse (higher-risk) examples.
    Returns: (list of 24 dicts, hours_until_spoilage_risk)
    """
    p = profile
    readings = []

    # Stochastic walk starting point
    temp = np.clip(
        np.random.normal(p["ideal_temp"] + np.random.uniform(-2, 2), p["temp_std"]),
        p["temp_range"][0] - 2,
        p["temp_range"][1] + 4,
    )
    humidity = np.clip(
        np.random.normal(p["ideal_humidity"] + np.random.uniform(-5, 5), p["humidity_std"]),
        p["humidity_range"][0] - 5,
        p["humidity_range"][1] + 5,
    )

    # Decide whether this sequence has a fault event
    has_fault = random.random() < fault_prob
    fault_start = random.randint(6, 18) if has_fault else WINDOW + 1
    fault_temp_drift = random.uniform(0.3, 0.8) * (1 if random.random() > 0.1 else -1)
    fault_humidity_drift = random.uniform(0.5, 2.0) * (1 if random.random() > 0.2 else -1)

    cumulative_exposure = 0.0

    for h in range(WINDOW):
        # Random walk
        temp += np.random.normal(0, p["temp_std"] * 0.3)
        humidity += np.random.normal(0, p["humidity_std"] * 0.3)

        # Fault drift
        if h >= fault_start:
            temp += fault_temp_drift
            humidity += fault_humidity_drift

        # Clamp to realistic extremes
        temp = np.clip(temp, p["temp_range"][0] - 5, p["temp_range"][1] + 10)
        humidity = np.clip(humidity, 60.0, 100.0)

        door_event = 1 if random.random() < p["door_open_prob"] else 0

        # Cumulative exposure score for this timestep
        heat_excess = max(0.0, temp - p["ideal_temp"])
        humidity_deviation = abs(humidity - p["ideal_humidity"])
        step_exposure = (
            p["heat_weight"] * heat_excess
            + p["humidity_weight"] * humidity_deviation * 0.1
            + 0.5 * door_event
        )
        cumulative_exposure += step_exposure

        readings.append({
            "temperature": round(temp, 2),
            "humidity": round(humidity, 2),
            "door_open_event": door_event,
            "produce_type": p["encode"],
        })

    # Label: hours_until_spoilage_risk
    hours_remaining = p["base_shelf_life"] - cumulative_exposure
    # Add noise (± 5% of base shelf life)
    noise = np.random.normal(0, p["base_shelf_life"] * 0.05)
    hours_remaining = max(0.0, hours_remaining + noise)

    return readings, round(hours_remaining, 2)


def build_dataset() -> pd.DataFrame:
    all_rows = []

    for produce_name, profile in PRODUCE_PROFILES.items():
        print(f"  Generating {SEQUENCES_PER_TYPE} sequences for {produce_name}...")
        for seq_idx in range(SEQUENCES_PER_TYPE):
            readings, label = generate_sequence(profile)
            for h, r in enumerate(readings):
                all_rows.append({
                    "seq_id": f"{produce_name}_{seq_idx:04d}",
                    "timestep": h,
                    "temperature": r["temperature"],
                    "humidity": r["humidity"],
                    "door_open_event": r["door_open_event"],
                    "produce_type": r["produce_type"],
                    "hours_until_spoilage": label,  # same label for all steps in sequence
                })

    return pd.DataFrame(all_rows)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("ColdSense Data Generator")
    print("=" * 40)
    df = build_dataset()
    df.to_csv(OUTPUT_PATH, index=False)
    total_sequences = len(df["seq_id"].unique())
    print(f"\nDone! {total_sequences} sequences ({len(df)} rows) saved to:")
    print(f"  {os.path.abspath(OUTPUT_PATH)}")
    print(f"\nLabel statistics:")
    print(df.groupby("produce_type")["hours_until_spoilage"].describe()[["mean","min","max"]].to_string())


if __name__ == "__main__":
    main()
