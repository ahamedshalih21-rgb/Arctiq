"""
Automated Verification Suite for ColdSense LSTM Upgrade
======================================================
Tests:
  1. Mendeley dataset calibration & reference files
  2. 10-feature, 360-timestep sequence dataset validity
  3. PyTorch LSTM model loading and inference
  4. Deterministic Spoilage Risk threshold validation (12h/24h)
  5. Simulator 360-step window buffer & fault evolution
  6. WhatsApp / notification debouncing logic
"""

import os
import sys
import numpy as np
import torch
import joblib

# Add backend and root to sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, ROOT_DIR)

from simulator import simulator, PRODUCE_CONFIGS, CANONICAL_KEYS
from predictor import predictor, hours_to_risk, ColdSenseLSTM
from services.early_warning_service import determine_operational_state, assess_early_warning
from services.notification_service import notification_service, WARNING_SEVERITY


def test_mendeley_reference_files_exist():
    """Verify downloaded Mendeley files exist in reference folder."""
    ref_dir = os.path.join(ROOT_DIR, "data", "reference", "mendeley")
    assert os.path.exists(ref_dir), f"Reference directory {ref_dir} does not exist"
    expected_files = [
        "FruitData.xlsx",
        "SensorFeed.xlsx",
        "Sample1DO-Resampled-5days.xlsx",
        "Sample3DO-Resampled-5days.xlsx",
        "SysIDSetupData.xlsx",
        "DATASET_FINDINGS.md",
    ]
    for fname in expected_files:
        fpath = os.path.join(ref_dir, fname)
        assert os.path.exists(fpath), f"Expected reference file {fname} not found"


def test_sequence_datasets_valid():
    """Verify pre-extracted sequences have 10 features and 360 timesteps."""
    data_dir = os.path.join(ROOT_DIR, "model", "data")
    train_npz = np.load(os.path.join(data_dir, "train_sequences.npz"))
    test_npz = np.load(os.path.join(data_dir, "test_sequences.npz"))

    X_train, y_train = train_npz["X"], train_npz["y"]
    X_test, y_test = test_npz["X"], test_npz["y"]

    assert X_train.ndim == 3 and X_train.shape[1] == 360 and X_train.shape[2] == 10
    assert X_test.ndim == 3 and X_test.shape[1] == 360 and X_test.shape[2] == 10
    assert len(y_train) == len(X_train)
    assert len(y_test) == len(X_test)

    # Check for NaN / Inf
    assert not np.isnan(X_train).any(), "X_train contains NaNs"
    assert not np.isnan(y_train).any(), "y_train contains NaNs"
    assert not np.isnan(X_test).any(), "X_test contains NaNs"


def test_pytorch_lstm_model_loading_and_inference():
    """Verify model loads and runs inference on a (360, 10) sequence."""
    predictor.load()
    assert predictor._loaded is True
    assert predictor.model is not None
    assert predictor.scaler is not None

    sample_input = np.zeros((360, 10), dtype=np.float32)
    sample_input[:, 0] = 2.0   # temp
    sample_input[:, 1] = 95.0  # humidity
    sample_input[:, 8] = 0.0   # spinach

    result = predictor.predict(sample_input)
    assert "hours_remaining" in result
    assert "model_hours_remaining" in result
    assert "risk_level" in result
    assert "warning_stage" in result
    assert result["hours_remaining"] >= 0.0


def test_deterministic_spoilage_risk_thresholds():
    """
    Verify the strict threshold requirements:
    > 24 hours -> LOW
    12–24 hours -> MEDIUM
    <= 12 hours -> HIGH
    Specifically: 16.0h must be MEDIUM, 11.8h must be HIGH.
    """
    assert hours_to_risk(30.0) == "LOW"
    assert hours_to_risk(24.5) == "LOW"
    assert hours_to_risk(24.0) == "MEDIUM"
    assert hours_to_risk(16.0) == "MEDIUM", "16.0h must be MEDIUM risk!"
    assert hours_to_risk(12.5) == "MEDIUM"
    assert hours_to_risk(12.0) == "HIGH", "12.0h must be HIGH risk!"
    assert hours_to_risk(11.8) == "HIGH", "11.8h must be HIGH risk!"
    assert hours_to_risk(4.0) == "HIGH"
    assert hours_to_risk(0.0) == "HIGH"


def test_early_warning_state_thresholds():
    """Verify operational warning state triggers at 12 hours."""
    # 16 hours with flat trend -> WATCH or EARLY_WARNING (MEDIUM risk tier)
    state_16 = determine_operational_state(model_hours=16.0, projected_horizon=16.0)
    assert state_16 in ("WATCH", "EARLY_WARNING")
    # 11.8 hours with flat trend -> CRITICAL / HIGH_RISK (HIGH risk tier <= 12h)
    state_11 = determine_operational_state(model_hours=11.8, projected_horizon=11.8)
    assert state_11 in ("CRITICAL", "HIGH_RISK")


def test_simulator_360_buffering_and_produce_types():
    """Verify simulator maintains 360-step windows and canonical produce types."""
    for pt in CANONICAL_KEYS:
        assert pt in simulator.batches
        w = simulator.get_window_360(pt)
        assert isinstance(w, np.ndarray)
        assert w.shape == (360, 10), f"Window shape for {pt} was {w.shape}"

    # Verify Spinach, Tomato, Strawberry configs
    assert PRODUCE_CONFIGS["spinach"]["display_name"] == "Spinach"
    assert PRODUCE_CONFIGS["tomato"]["display_name"] == "Tomato"
    assert PRODUCE_CONFIGS["strawberry"]["display_name"] == "Strawberry"


def test_fault_injection_progression():
    """Verify that fault injection dynamically increases temp and cumulative heat."""
    batch = simulator.batches["spinach"]
    initial_temp = batch.temp
    initial_heat = batch.cumulative_heat_exposure

    # Trigger fault
    batch.trigger_fault(speed=5.0)
    assert batch.fault_active is True

    # Advance 10 ticks
    for _ in range(10):
        batch.tick()

    assert batch.temp > initial_temp, "Temperature did not rise under fault condition"
    assert batch.cumulative_heat_exposure >= initial_heat, "Cumulative heat did not accumulate"

    # Reset fault
    batch.reset_fault()
    assert batch.fault_active is False


async def test_notification_debouncing():
    """Verify alert debouncing suppresses repeated notifications for same stage."""
    rec = {
        "display_name": "Spinach",
        "batch_id": "TEST_SP_01",
        "model_hours_remaining": 11.5,
        "projected_risk_horizon_hours": 10.0,
        "sell_priority_score": 85.0,
        "recommended_price_per_kg": 40.0,
        "market_price_per_kg": 80.0,
        "quantity_kg": 100.0,
        "expected_waste_inr": 4000.0,
    }

    # First evaluation in alertable stage (CRITICAL)
    res1 = await notification_service.evaluate_and_notify(
        batch_id="TEST_SP_01",
        current_stage="CRITICAL",
        recommendation=rec,
        force_alert=False,
    )
    # Notice: even if telegram token is not set, state machine records attempt or reason
    state = notification_service.alert_state.get("TEST_SP_01", {})
    assert state.get("last_stage") == "CRITICAL"

    # Second evaluation in the EXACT same stage -> MUST be suppressed as duplicate
    res2 = await notification_service.evaluate_and_notify(
        batch_id="TEST_SP_01",
        current_stage="CRITICAL",
        recommendation=rec,
        force_alert=False,
    )
    assert res2["sent"] is False
    assert "Duplicate alert suppressed" in res2["reason"] or "already notified" in res2["reason"]


def run_all_tests():
    import asyncio
    print("=" * 60)
    print("Running ColdSense LSTM Automated Test Suite...")
    print("=" * 60)

    tests = [
        ("Mendeley Reference Files", test_mendeley_reference_files_exist),
        ("Sequence Datasets (360x10)", test_sequence_datasets_valid),
        ("PyTorch LSTM Inference", test_pytorch_lstm_model_loading_and_inference),
        ("Spoilage Risk Thresholds (>24h, 12-24h, <=12h)", test_deterministic_spoilage_risk_thresholds),
        ("Early Warning Operational State", test_early_warning_state_thresholds),
        ("Simulator 360 Buffering & Produce Configs", test_simulator_360_buffering_and_produce_types),
        ("Fault Injection & Thermal Progression", test_fault_injection_progression),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name} -> {e}")

    try:
        asyncio.run(test_notification_debouncing())
        print("  PASS: Notification Debouncing State Machine")
        passed += 1
    except Exception as e:
        print(f"  FAIL: Notification Debouncing State Machine -> {e}")

    print("=" * 60)
    print(f"Test Suite Finished: {passed}/{len(tests) + 1} passed.")
    print("=" * 60)
    if passed < len(tests) + 1:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
