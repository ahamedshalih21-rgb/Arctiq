"""
Arctiq — Model Predictor (PyTorch LSTM)
==========================================
Loads the pre-trained Arctiq PyTorch LSTM model and StandardScaler at startup.
Inference receives a 360-timestep sequence of 10 features:
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

Deterministic Spoilage Risk Layer:
  - > 24 hours    -> LOW
  - 12–24 hours   -> MEDIUM
  - <= 12 hours   -> HIGH (12-hour intervention window)
"""

import os
import json
import numpy as np
import joblib
from typing import Optional, Union, List

import torch
import torch.nn as nn

MODEL_DIR          = os.path.join(os.path.dirname(__file__), "..", "model", "saved_model")
LSTM_PATH          = os.path.join(MODEL_DIR, "arctiq_lstm.pt")
SCALER_PATH        = os.path.join(MODEL_DIR, "scaler.joblib")
SCALER_PARAMS_PATH = os.path.join(MODEL_DIR, "scaler_params.json")
METRICS_PATH       = os.path.join(MODEL_DIR, "metrics.json")

FEATURE_NAMES = [
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

# ── Spoilage risk calculation (separate deterministic layer) ───────────────────
def hours_to_risk(hours: float) -> str:
    """
    > 24 hours -> LOW
    12–24 hours -> MEDIUM
    <= 12 hours -> HIGH
    """
    if hours > 24.0:
        return "LOW"
    elif hours > 12.0:
        return "MEDIUM"
    return "HIGH"


# ── PyTorch LSTM Model Architecture ───────────────────────────────────────────
class ArctiqLSTM(nn.Module):
    def __init__(self, input_dim: int = 10, hidden_dim: int = 64, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.fc_block = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
        )

    def forward(self, x):
        # x shape: (batch_size, 360, 10)
        lstm_out, _ = self.lstm(x)
        last_timestep = lstm_out[:, -1, :]
        out = self.fc_block(last_timestep)
        return out.squeeze(-1)


# ── ArctiqPredictor ────────────────────────────────────────────────────────────
class ArctiqPredictor:
    def __init__(self):
        self.model: Optional[ArctiqLSTM] = None
        self.scaler = None
        self.scaler_params = {}
        self.metrics = {}
        self.model_type: str = "lstm"
        self._loaded = False
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def load(self):
        if self._loaded:
            return

        if not os.path.exists(LSTM_PATH):
            raise FileNotFoundError(
                f"LSTM checkpoint not found at {LSTM_PATH}. Run 'python model/train.py' first."
            )
        if not os.path.exists(SCALER_PATH):
            raise FileNotFoundError(
                f"Scaler not found at {SCALER_PATH}. Run 'python model/train.py' first."
            )

        # Load scaler
        self.scaler = joblib.load(SCALER_PATH)

        # Load checkpoint
        checkpoint = torch.load(LSTM_PATH, map_location=self.device, weights_only=False)
        self.model = ArctiqLSTM(
            input_dim=checkpoint.get("input_dim", 10),
            hidden_dim=checkpoint.get("hidden_dim", 64),
            num_layers=checkpoint.get("num_layers", 2),
        ).to(self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()

        if os.path.exists(SCALER_PARAMS_PATH):
            try:
                with open(SCALER_PARAMS_PATH) as f:
                    self.scaler_params = json.load(f)
            except Exception:
                pass

        if os.path.exists(METRICS_PATH):
            try:
                with open(METRICS_PATH) as f:
                    self.metrics = json.load(f)
            except Exception:
                pass

        self._loaded = True
        print(f"[Predictor] Loaded PyTorch LSTM model and StandardScaler on {self.device}")

    def _preprocess_window(self, window: Union[List, np.ndarray]) -> np.ndarray:
        """
        Takes either a numpy array of shape (360, 10) or a list of dicts/lists.
        Returns: normalized np.ndarray of shape (1, 360, 10).
        """
        if isinstance(window, np.ndarray):
            if window.ndim == 2:
                # Shape (360, 10)
                arr = window
            elif window.ndim == 3:
                arr = window[0]
            else:
                raise ValueError(f"Unexpected window array shape: {window.shape}")
        elif isinstance(window, list):
            if len(window) == 0:
                raise ValueError("Empty window provided to predictor")
            
            # If list of dicts
            if isinstance(window[0], dict):
                rows = []
                for r in window:
                    row = [
                        float(r.get("temperature", 4.0)),
                        float(r.get("humidity", 90.0)),
                        float(r.get("door_event", r.get("door_open_event", 0))),
                        float(r.get("batch_age_hours", 24.0)),
                        float(r.get("hours_in_cold_storage", 20.0)),
                        float(r.get("cumulative_heat_exposure", 0.0)),
                        float(r.get("time_above_safe_temperature", 0.0)),
                        float(r.get("temperature_rate_of_change", r.get("temp_derivative", 0.0))),
                        float(r.get("produce_type", 0)),
                        float(r.get("batch_picked_temperature", 24.0)),
                    ]
                    rows.append(row)
                arr = np.array(rows, dtype=np.float32)
            else:
                arr = np.array(window, dtype=np.float32)
        else:
            raise TypeError(f"Unsupported window type: {type(window)}")

        # Ensure exact shape (360, 10)
        if len(arr) < 360:
            # Pad front with earliest reading
            pad_count = 360 - len(arr)
            pad_rows = np.repeat(arr[:1], pad_count, axis=0)
            arr = np.vstack([pad_rows, arr])
        elif len(arr) > 360:
            arr = arr[-360:]

        # Transform using StandardScaler
        arr_scaled = self.scaler.transform(arr.reshape(-1, 10)).reshape(1, 360, 10).astype(np.float32)
        return arr_scaled

    def predict(
        self,
        window: Union[List, np.ndarray],
        history: Optional[list] = None,
        produce_config: Optional[dict] = None,
    ) -> dict:
        """
        Runs PyTorch LSTM inference and integrates early warning evaluation.
        """
        if not self._loaded:
            self.load()

        X_scaled = self._preprocess_window(window)
        with torch.no_grad():
            tensor_in = torch.from_numpy(X_scaled).to(self.device)
            raw_hours = float(self.model(tensor_in).item())

        hours = max(0.0, raw_hours)
        risk = hours_to_risk(hours)

        # ── Integrate early warning assessment ────────────────────────────────
        from services.early_warning_service import assess_early_warning

        cfg = produce_config or {}
        ideal_temp           = cfg.get("ideal_temp", 2.0)
        ideal_humidity       = cfg.get("ideal_humidity", 90.0)
        perishability_factor = cfg.get("perishability_factor", 1.0)
        produce_type         = cfg.get("produce_type", "")

        use_history = history or (window if isinstance(window, list) and isinstance(window[0], dict) else [])
        last = use_history[-1] if use_history else {}
        current_temp     = last.get("temperature", ideal_temp)
        current_humidity = last.get("humidity", ideal_humidity)

        ew = assess_early_warning(
            produce_type=produce_type,
            model_hours=hours,
            history=use_history,
            ideal_temp=ideal_temp,
            ideal_humidity=ideal_humidity,
            current_temp=current_temp,
            current_humidity=current_humidity,
            perishability_factor=perishability_factor,
        )

        return {
            "hours_remaining":              round(hours, 1),
            "model_hours_remaining":        round(hours, 1),
            "risk_level":                   risk,
            "confidence":                   0.95,
            # Two-stage warning fields
            "warning_stage":                ew["warning_stage"],
            "projected_risk_horizon_hours": ew["projected_risk_horizon_hours"],
            "temp_slope_per_tick":          ew["temp_slope_per_tick"],
            "humidity_slope_per_tick":      ew["humidity_slope_per_tick"],
            "temp_excursion_c":             ew["temp_excursion_c"],
            "humidity_deviation_pct":       ew["humidity_deviation_pct"],
            "early_warning_active":         ew["early_warning_active"],
            "critical_action_active":       ew["critical_action_active"],
            "warning_description":          ew["warning_description"],
            "horizon_note":                 ew["horizon_note"],
        }

    def predict_value(
        self,
        prediction: dict,
        batch_weight_kg: float,
        value_per_kg: float,
    ) -> dict:
        """
        Computes estimated batch value and value at risk.
        > 24h (LOW): 5% at risk
        12–24h (MEDIUM): 35% at risk
        <= 12h (HIGH): 85% at risk
        """
        risk = prediction.get("risk_level", "LOW")
        risk_map = {
            "LOW": 0.05,
            "MEDIUM": 0.35,
            "HIGH": 0.85,
            # Backward compatibility aliases
            "Safe": 0.05,
            "Watch": 0.35,
            "Critical": 0.85,
        }
        risk_factor = risk_map.get(risk, 0.20)
        batch_value = batch_weight_kg * value_per_kg
        value_at_risk = round(batch_value * risk_factor, 2)
        value_saved = round(batch_value * (1.0 - risk_factor), 2)
        total_value = round(batch_value, 2)

        return {
            "total_batch_value_usd": total_value,
            "value_at_risk_usd":     value_at_risk,
            "value_preserved_usd":   value_saved,
            "risk_factor_pct":       round(risk_factor * 100, 1),
        }


# Singleton
predictor = ArctiqPredictor()
