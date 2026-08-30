"""
ColdSense — Model Predictor
Loads the pre-trained LSTM (or GBR fallback) at startup and provides inference.
"""

import os
import json
import numpy as np
from typing import Optional

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "model", "saved_model")
KERAS_PATH = os.path.join(MODEL_DIR, "coldsense_model.keras")
GBR_PATH = os.path.join(MODEL_DIR, "coldsense_model.joblib")
NORM_PATH = os.path.join(MODEL_DIR, "norm_params.json")

SAFE_THRESHOLD = 48.0
WATCH_THRESHOLD = 24.0

# Value/loss parameters (per produce type)
RISK_FACTORS = {"Safe": 0.05, "Watch": 0.35, "Critical": 0.85}


def hours_to_risk(hours: float) -> str:
    if hours > SAFE_THRESHOLD:
        return "Safe"
    elif hours > WATCH_THRESHOLD:
        return "Watch"
    return "Critical"


class ColdSensePredictor:
    def __init__(self):
        self.model = None
        self.norm = None
        self.model_type: str = "none"
        self._loaded = False

    def load(self):
        if self._loaded:
            return

        # Load normalization params
        if not os.path.exists(NORM_PATH):
            raise FileNotFoundError(
                f"norm_params.json not found at {NORM_PATH}. "
                "Run model/train.py first."
            )
        with open(NORM_PATH) as f:
            self.norm = json.load(f)

        self.model_type = self.norm.get("model_type", "lstm")

        if self.model_type == "gbr":
            self._load_gbr()
        else:
            self._load_lstm()

        self._loaded = True
        print(f"[Predictor] Loaded {self.model_type.upper()} model from {MODEL_DIR}")

    def _load_lstm(self):
        if not os.path.exists(KERAS_PATH):
            raise FileNotFoundError(
                f"LSTM model not found at {KERAS_PATH}. Run model/train.py first."
            )
        import tensorflow as tf
        self.model = tf.keras.models.load_model(KERAS_PATH)

    def _load_gbr(self):
        if not os.path.exists(GBR_PATH):
            raise FileNotFoundError(
                f"GBR model not found at {GBR_PATH}. Run model/train.py first."
            )
        import joblib
        self.model = joblib.load(GBR_PATH)

    def _preprocess_window(self, window: list) -> np.ndarray:
        """
        window: list of 24 dicts with keys: temperature, humidity, door_open_event, produce_type
        Returns: np.ndarray of shape (1, 24, 4) for LSTM or (1, 96) for GBR.
        """
        n = self.norm
        arr = []
        for r in window:
            temp_norm = (r["temperature"] - n["temp_mean"]) / n["temp_std"]
            hum_norm = (r["humidity"] - n["hum_mean"]) / n["hum_std"]
            door = float(r["door_open_event"])
            pt = float(r["produce_type"]) / 2.0
            arr.append([temp_norm, hum_norm, door, pt])

        X = np.array(arr, dtype=np.float32)  # (24, 4)
        return X

    def predict(self, window: list) -> dict:
        """
        Returns dict with: hours_remaining (float), risk_level (str), confidence (float)
        """
        if not self._loaded:
            self.load()

        X = self._preprocess_window(window)
        n = self.norm

        if self.model_type == "gbr":
            X_flat = X.reshape(1, -1)
            pred_raw = float(self.model.predict(X_flat)[0])
            hours = max(0.0, pred_raw)
            confidence = 0.82
        else:
            X_lstm = X[np.newaxis, ...]  # (1, 24, 4)
            pred_norm = float(self.model.predict(X_lstm, verbose=0)[0][0])
            hours = max(0.0, pred_norm * n["label_std"] + n["label_mean"])
            confidence = 0.88

        risk = hours_to_risk(hours)
        return {
            "hours_remaining": round(hours, 1),
            "risk_level": risk,
            "confidence": confidence,
        }

    def predict_value(self, prediction: dict, batch_weight_kg: float, value_per_kg: float) -> dict:
        """
        Computes estimated value/loss-prevented.
        Logic: The at-risk value ($ that would be lost if spoilage occurs) is
        batch_value × risk_factor. Value saved = batch_value × (1 - risk_factor).
        """
        batch_value = batch_weight_kg * value_per_kg
        risk_factor = RISK_FACTORS[prediction["risk_level"]]
        value_at_risk = round(batch_value * risk_factor, 2)
        value_saved = round(batch_value * (1 - risk_factor), 2)
        total_value = round(batch_value, 2)

        return {
            "total_batch_value_usd": total_value,
            "value_at_risk_usd": value_at_risk,
            "value_preserved_usd": value_saved,
            "risk_factor_pct": round(risk_factor * 100, 1),
        }


# Singleton
predictor = ColdSensePredictor()
