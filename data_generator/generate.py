"""
Arctiq — Synthetic Data Generator Calibrated on Mendeley Reference Data
==========================================================================
Reference Dataset:
  "A Real-Time Shelf-Life Estimation Model"
  Abougharib & Awad (2023), Mendeley Data, DOI: 10.17632/kphtgxn3ff.4

Products:
  0: Spinach    (optimal 0–4°C, target 2°C, baseline shelf-life 288h / 12 days)
  1: Tomato     (optimal 12–15°C, target 13°C, baseline shelf-life 360h / 15 days, chilling-sensitive)
  2: Strawberry (optimal 0–4°C, target 1.5°C, baseline shelf-life 192h / 8 days, Mendeley fruit baseline)

Arctiq 10-Feature Conceptual Sequence:
  1. temperature
  2. humidity
  3. door_event
  4. batch_age_hours
  5. hours_in_cold_storage
  6. cumulative_heat_exposure
  7. time_above_safe_temperature
  8. temperature_rate_of_change
  9. produce_type
  10. batch_picked_temperature

Target:
  remaining_shelf_life_hours (continuous non-linear kinetic regression target)
"""

import os
import random
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d

SEED = 42
np.random.seed(SEED)
random.seed(SEED)

REFERENCE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "reference", "mendeley")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "model", "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── PRODUCE PROFILES ────────────────────────────────────────────────────────────
PRODUCE_PROFILES = {
    "spinach": {
        "encode": 0,
        "display_name": "Spinach",
        "optimal_temp": 2.0,       # °C
        "safe_temp": 4.0,          # °C
        "optimal_humidity": 95.0,  # %
        "base_shelf_life": 288.0,  # hours (12 days at optimal)
        "q10": 2.8,                # Respiration acceleration
        "humidity_sensitivity": 0.4,
        "is_chilling_sensitive": False,
        "chilling_temp_threshold": 0.0,
    },
    "tomato": {
        "encode": 1,
        "display_name": "Tomato",
        "optimal_temp": 13.0,      # °C
        "safe_temp": 15.0,         # °C
        "optimal_humidity": 88.0,  # %
        "base_shelf_life": 360.0,  # hours (15 days at optimal)
        "q10": 2.2,                # Respiration acceleration
        "humidity_sensitivity": 0.25,
        "is_chilling_sensitive": True,
        "chilling_temp_threshold": 10.0,  # Below 10°C develops chilling injury
    },
    "strawberry": {
        "encode": 2,
        "display_name": "Strawberry",
        "optimal_temp": 1.5,       # °C
        "safe_temp": 4.0,          # °C
        "optimal_humidity": 92.0,  # %
        "base_shelf_life": 192.0,  # hours (8 days at optimal, matching Mendeley 7-10d)
        "q10": 2.5,                # Respiration acceleration from Mendeley Decay Profile
        "humidity_sensitivity": 0.35,
        "is_chilling_sensitive": False,
        "chilling_temp_threshold": 0.0,
    },
}

FEATURE_COLS = [
    "temperature",
    "humidity",
    "door_event",
    "batch_age_hours",
    "hours_in_cold_storage",
    "cumulative_heat_exposure",
    "time_above_safe_temperature",
    "temperature_rate_of_change",
    "produce_type",
    "batch_picked_temperature",
]
TARGET_COL = "remaining_shelf_life_hours"


def load_mendeley_reference_trajectories() -> dict:
    trajectories = {}
    files = {
        "sample_1do": "Sample1DO-Resampled-5days.xlsx",
        "sample_3do": "Sample3DO-Resampled-5days.xlsx",
        "sensor_feed": "SensorFeed.xlsx",
    }
    for key, fname in files.items():
        fpath = os.path.join(REFERENCE_DIR, fname)
        if os.path.exists(fpath):
            xl = pd.ExcelFile(fpath)
            sheet = xl.sheet_names[0]
            df = xl.parse(sheet)
            time_col = [c for c in df.columns if 'time' in str(c).lower()][0]
            temp_col = [c for c in df.columns if 'temp' in str(c).lower()][0]
            raw_t = df[time_col].values.astype(float)
            raw_temp = df[temp_col].values.astype(float)
            valid = ~(np.isnan(raw_t) | np.isnan(raw_temp))
            raw_t, raw_temp = raw_t[valid], raw_temp[valid]
            
            t_1min = np.arange(int(raw_t[0]), int(raw_t[-1]) + 1)
            interp_fn = interp1d(raw_t, raw_temp, kind='linear', fill_value='extrapolate')
            temp_1min = interp_fn(t_1min)
            trajectories[key] = {
                "time_min": t_1min,
                "temp": temp_1min,
                "source_file": fname,
            }
    return trajectories


def generate_single_batch(
    batch_id: str,
    produce_key: str,
    ref_trajectories: dict,
    duration_hours: float = 48.0,
    has_fault: bool = False,
    fault_start_ratio: float = 0.5,
) -> pd.DataFrame:
    profile = PRODUCE_PROFILES[produce_key]
    n_minutes = int(duration_hours * 60)
    
    # 1. Harvest & Pre-storage conditions
    picked_temp = round(random.uniform(21.0, 27.5), 1)  # Field heat
    delay_hours = round(random.uniform(1.2, 3.5), 2)    # Delay before cold store entry
    
    pre_storage_decay_rate = profile["q10"] ** ((picked_temp - profile["optimal_temp"]) / 10.0)
    pre_storage_loss_hours = delay_hours * pre_storage_decay_rate

    # Prior cold-storage history
    age_category = random.choices(["fresh", "mid", "late", "critical"], weights=[0.30, 0.35, 0.20, 0.15])[0]
    if age_category == "fresh":
        prior_hours = random.uniform(0.0, 0.25 * profile["base_shelf_life"])
    elif age_category == "mid":
        prior_hours = random.uniform(0.25 * profile["base_shelf_life"], 0.65 * profile["base_shelf_life"])
    elif age_category == "late":
        prior_hours = random.uniform(0.65 * profile["base_shelf_life"], 0.88 * profile["base_shelf_life"])
    else:  # critical (approaching 8–18h remaining)
        prior_hours = random.uniform(0.88 * profile["base_shelf_life"], 0.96 * profile["base_shelf_life"])

    prior_consumed_hours = prior_hours * 1.0

    # 2. Empirical reference temperature template
    ref_keys = list(ref_trajectories.keys())
    ref_choice = random.choice(ref_keys)
    ref_data = ref_trajectories[ref_choice]["temp"]
    
    if len(ref_data) > n_minutes:
        start_idx = random.randint(0, len(ref_data) - n_minutes - 1)
        base_temp_slice = ref_data[start_idx : start_idx + n_minutes].copy()
    else:
        repeats = int(np.ceil(n_minutes / len(ref_data)))
        tiled = np.tile(ref_data, repeats)
        base_temp_slice = tiled[:n_minutes].copy()

    # Shift empirical oscillation to product's optimal setpoint
    ref_median = np.median(base_temp_slice)
    oscillation = base_temp_slice - ref_median
    scale_factor = random.uniform(0.85, 1.15)
    temp_trajectory = profile["optimal_temp"] + (oscillation * scale_factor)

    # Steady sensor noise
    temp_trajectory += np.random.normal(0, 0.12, n_minutes)

    # 3. Door Openings
    door_events = np.zeros(n_minutes, dtype=int)
    humidity = np.full(n_minutes, profile["optimal_humidity"], dtype=float)
    
    num_door_openings = random.randint(1, 4)
    for _ in range(num_door_openings):
        d_start = random.randint(60, n_minutes - 180)
        d_duration = random.randint(5, 15)
        d_end = min(n_minutes, d_start + d_duration)
        door_events[d_start:d_end] = 1
        
        rise_rate = random.uniform(1.1, 1.4)  # ODTRR ~ 1.313°C/min
        peak_temp = min(22.0, temp_trajectory[d_start] + (rise_rate * d_duration))
        temp_trajectory[d_start:d_end] = np.linspace(temp_trajectory[d_start], peak_temp, d_end - d_start)
        
        recovery_duration = random.randint(30, 60)
        rec_end = min(n_minutes, d_end + recovery_duration)
        if rec_end > d_end:
            target_after_rec = profile["optimal_temp"] + random.uniform(-0.3, 0.5)
            rec_decay = np.exp(-np.linspace(0, 3.5, rec_end - d_end))
            temp_trajectory[d_end:rec_end] = target_after_rec + (peak_temp - target_after_rec) * rec_decay
        
        humidity[d_start:d_end] = np.linspace(profile["optimal_humidity"], random.uniform(62.0, 72.0), d_end - d_start)
        if rec_end > d_end:
            humidity[d_end:rec_end] = np.linspace(humidity[d_end-1], profile["optimal_humidity"], rec_end - d_end)

    # 4. Cooling Fault / Compressor Failure
    fault_minute = -1
    if has_fault:
        fault_minute = int(n_minutes * fault_start_ratio)
        t_out = random.uniform(23.0, 26.0)  # Mendeley Tout is 24.04°C
        k_warm = random.uniform(0.002, 0.0035)  # CDTRR ~ 0.125°C/min
        for m in range(fault_minute, n_minutes):
            dt = m - fault_minute
            asymptotic_temp = t_out - (t_out - temp_trajectory[fault_minute]) * np.exp(-k_warm * dt)
            temp_trajectory[m] = asymptotic_temp + np.random.normal(0, 0.1)
            humidity[m] = max(55.0, humidity[m] - (dt * 0.015))

    humidity = np.clip(humidity + np.random.normal(0, 1.2, n_minutes), 50.0, 99.0)

    # 5. Arctiq 10-Feature Computation (Strictly Causal / No Lookahead)
    batch_age_hours = delay_hours + prior_hours + (np.arange(n_minutes) / 60.0)
    hours_in_cold_storage = prior_hours + (np.arange(n_minutes) / 60.0)

    # Temperature rate of change (°C/min)
    temperature_rate_of_change = np.diff(temp_trajectory, prepend=temp_trajectory[0])

    # Time above safe temperature (hours)
    is_above_safe = (temp_trajectory > profile["safe_temp"]).astype(float)
    # Factor prior hours above safe if late/critical batch
    prior_time_above = (prior_hours * 0.15) if (age_category in ["late", "critical"] and has_fault) else 0.0
    time_above_safe_temperature = prior_time_above + (np.cumsum(is_above_safe) / 60.0)

    # Cumulative heat exposure (degree-hours)
    heat_excess = np.maximum(0.0, temp_trajectory - profile["safe_temp"])
    prior_heat_exp = prior_time_above * 2.5
    cumulative_heat_exposure = prior_heat_exp + (np.cumsum(heat_excess) / 60.0)

    # 6. Continuous Kinetic Target Calculation
    remaining_shelf_life = np.zeros(n_minutes, dtype=float)
    accumulated_cold_store_consumed = 0.0
    
    for m in range(n_minutes):
        t_curr = temp_trajectory[m]
        h_curr = humidity[m]
        
        r_resp = profile["q10"] ** ((t_curr - profile["optimal_temp"]) / 10.0)
        hum_deficit = max(0.0, profile["optimal_humidity"] - h_curr)
        hum_factor = 1.0 + (profile["humidity_sensitivity"] * (hum_deficit / 100.0))
        r_total = r_resp * hum_factor
        
        if profile["is_chilling_sensitive"] and t_curr < profile["chilling_temp_threshold"]:
            chill_excess = profile["chilling_temp_threshold"] - t_curr
            r_total += 0.20 * chill_excess
            
        accumulated_cold_store_consumed += (r_total / 60.0)
        total_consumed = pre_storage_loss_hours + prior_consumed_hours + accumulated_cold_store_consumed
        remaining_sl = max(0.0, profile["base_shelf_life"] - total_consumed)
        remaining_shelf_life[m] = round(remaining_sl, 2)

    df_batch = pd.DataFrame({
        "batch_id": batch_id,
        "minute": np.arange(n_minutes),
        "produce_type_name": produce_key,
        "temperature": np.round(temp_trajectory, 2),
        "humidity": np.round(humidity, 1),
        "door_event": door_events,
        "batch_age_hours": np.round(batch_age_hours, 2),
        "hours_in_cold_storage": np.round(hours_in_cold_storage, 2),
        "cumulative_heat_exposure": np.round(cumulative_heat_exposure, 3),
        "time_above_safe_temperature": np.round(time_above_safe_temperature, 3),
        "temperature_rate_of_change": np.round(temperature_rate_of_change, 3),
        "produce_type": profile["encode"],
        "batch_picked_temperature": picked_temp,
        "fault_active": (np.arange(n_minutes) >= fault_minute) if has_fault else False,
        "remaining_shelf_life_hours": remaining_shelf_life,
    })
    
    return df_batch


def build_full_dataset():
    print("=" * 70)
    print("Arctiq 10-Feature Sequence Dataset Generator")
    print("Empirically Grounded in Mendeley Dataset (DOI: 10.17632/kphtgxn3ff.4)")
    print("=" * 70)

    ref_trajectories = load_mendeley_reference_trajectories()
    print(f"Loaded {len(ref_trajectories)} Mendeley empirical trajectory templates.")

    all_batches = []
    batch_counter = 0

    train_batch_ids = set()
    test_batch_ids = set()

    for produce_key in PRODUCE_PROFILES.keys():
        print(f"Generating batches for {produce_key.upper()}...")
        for i in range(20):
            batch_counter += 1
            batch_id = f"BATCH_{produce_key[:3].upper()}_{batch_counter:03d}"
            duration = random.choice([48.0, 56.0, 64.0, 72.0])
            has_fault = (i % 3 == 0)
            fault_ratio = random.uniform(0.35, 0.70)
            
            df_b = generate_single_batch(
                batch_id=batch_id,
                produce_key=produce_key,
                ref_trajectories=ref_trajectories,
                duration_hours=duration,
                has_fault=has_fault,
                fault_start_ratio=fault_ratio,
            )
            all_batches.append(df_b)
            
            if i < 16:
                train_batch_ids.add(batch_id)
            else:
                test_batch_ids.add(batch_id)

    full_df = pd.concat(all_batches, ignore_index=True)
    train_df = full_df[full_df["batch_id"].isin(train_batch_ids)].copy().reset_index(drop=True)
    test_df = full_df[full_df["batch_id"].isin(test_batch_ids)].copy().reset_index(drop=True)

    train_csv_path = os.path.join(OUTPUT_DIR, "batch_data_train.csv")
    test_csv_path = os.path.join(OUTPUT_DIR, "batch_data_test.csv")
    train_df.to_csv(train_csv_path, index=False)
    test_df.to_csv(test_csv_path, index=False)
    print(f"Saved: {train_csv_path} ({len(train_df):,} rows)")
    print(f"Saved: {test_csv_path} ({len(test_df):,} rows)")

    # 360-step Sequence Extraction
    WINDOW_SIZE = 360
    STEP_STRIDE = 15

    def extract_sequences(df_split):
        X_list = []
        y_list = []
        for b_id, group in df_split.groupby("batch_id"):
            feat_arr = group[FEATURE_COLS].values
            target_arr = group[TARGET_COL].values
            n_steps = len(group)
            for end_t in range(WINDOW_SIZE, n_steps, STEP_STRIDE):
                start_t = end_t - WINDOW_SIZE
                X_seq = feat_arr[start_t:end_t]  # (360, 10)
                y_val = target_arr[end_t - 1]     # target at current step
                X_list.append(X_seq)
                y_list.append(y_val)
        return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)

    print("\nExtracting 360-minute sequences (stride=15 min)...")
    X_train, y_train = extract_sequences(train_df)
    X_test, y_test = extract_sequences(test_df)

    print(f"X_train shape: {X_train.shape}, y_train shape: {y_train.shape}")
    print(f"X_test shape:  {X_test.shape}, y_test shape:  {y_test.shape}")

    np.savez_compressed(
        os.path.join(OUTPUT_DIR, "train_sequences.npz"),
        X=X_train,
        y=y_train,
        feature_names=np.array(FEATURE_COLS),
    )
    np.savez_compressed(
        os.path.join(OUTPUT_DIR, "test_sequences.npz"),
        X=X_test,
        y=y_test,
        feature_names=np.array(FEATURE_COLS),
    )
    print("Saved train_sequences.npz and test_sequences.npz.")

    print("\nTarget Statistics by Produce Type (Train Split):")
    print(train_df.groupby("produce_type_name")[TARGET_COL].describe()[["count", "mean", "min", "max"]].to_string())

    return full_df, X_train, y_train, X_test, y_test


if __name__ == "__main__":
    build_full_dataset()
