"""
ColdSense — Live Sensor Simulator (10-Feature 360-Minute Buffering)
==================================================================
Empirically calibrated to Mendeley Dataset (DOI: 10.17632/kphtgxn3ff.4).

Products:
  - spinach:    Spinach (optimal 2°C, safe 4°C, 95% RH, baseline 288h / 12 days)
  - tomato:     Tomato (optimal 13°C, safe 15°C, 88% RH, baseline 360h / 15 days, chilling-sensitive)
  - strawberry: Strawberry (optimal 1.5°C, safe 4°C, 92% RH, baseline 192h / 8 days, Mendeley fruit baseline)

Feature Vector (10 features per timestep):
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
"""

import threading
import time
import random
import math
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import numpy as np

# ── Produce configurations ─────────────────────────────────────────────────────
PRODUCE_CONFIGS = {
    "spinach": {
        "encode": 0,
        "display_name": "Spinach",
        "ideal_temp": 2.0,
        "safe_temp": 4.0,
        "ideal_humidity": 95.0,
        "temp_noise": 0.08,
        "humidity_noise": 0.35,
        "door_open_prob": 0.04,
        "base_shelf_life": 288.0,
        "q10": 2.8,
        "batch_weight_kg": 120.0,
        "value_per_kg": 3.50,        # USD
        "color": "#4ECDC4",
        "demand_init_range": (60, 90),
        "purchase_cost_per_kg": 45.0,
        "market_price_per_kg": 80.0,
        "perishability_factor": 1.5,
    },
    "tomato": {
        "encode": 1,
        "display_name": "Tomato",
        "ideal_temp": 13.0,
        "safe_temp": 15.0,
        "ideal_humidity": 88.0,
        "temp_noise": 0.10,
        "humidity_noise": 0.40,
        "door_open_prob": 0.03,
        "base_shelf_life": 360.0,
        "q10": 2.2,
        "batch_weight_kg": 200.0,
        "value_per_kg": 2.20,
        "color": "#FF6B6B",
        "demand_init_range": (50, 80),
        "purchase_cost_per_kg": 30.0,
        "market_price_per_kg": 55.0,
        "perishability_factor": 1.0,
    },
    "strawberry": {
        "encode": 2,
        "display_name": "Strawberry",
        "ideal_temp": 1.5,
        "safe_temp": 4.0,
        "ideal_humidity": 92.0,
        "temp_noise": 0.07,
        "humidity_noise": 0.35,
        "door_open_prob": 0.04,
        "base_shelf_life": 192.0,
        "q10": 2.5,
        "batch_weight_kg": 80.0,
        "value_per_kg": 5.50,
        "color": "#E056FD",
        "demand_init_range": (65, 95),
        "purchase_cost_per_kg": 60.0,
        "market_price_per_kg": 110.0,
        "perishability_factor": 1.8,
    },
}

# Aliases for backward compatibility
PRODUCE_CONFIGS["leafy_greens"] = PRODUCE_CONFIGS["spinach"]
PRODUCE_CONFIGS["tomatoes"]     = PRODUCE_CONFIGS["tomato"]
PRODUCE_CONFIGS["milk"]         = PRODUCE_CONFIGS["strawberry"]

CANONICAL_KEYS = ["spinach", "tomato", "strawberry"]

HISTORY_LEN = 100       # readings kept for UI charts
WINDOW_LEN = 360        # 360 timesteps for LSTM input
TICK_INTERVAL = 3.0     # seconds between ticks
EMA_ALPHA = 0.30
DEMAND_DRIFT_MAX = 2.0


class ProduceBatch:
    def __init__(self, produce_type: str, batch_id: str):
        cfg = PRODUCE_CONFIGS[produce_type]
        self.produce_type = produce_type
        self.batch_id = batch_id
        self.cfg = cfg
        
        # Simulated harvest metadata
        self.picked_temp = round(random.uniform(22.0, 26.5), 1)
        self.delay_hours = round(random.uniform(1.5, 3.0), 2)
        
        # Start storage time
        self.storage_since = datetime.utcnow() - timedelta(hours=random.uniform(8.0, 24.0))
        self.hours_in_cold_storage = (datetime.utcnow() - self.storage_since).total_seconds() / 3600.0
        self.batch_age_hours = self.delay_hours + self.hours_in_cold_storage

        # Current temperature and humidity states
        self.temp = cfg["ideal_temp"] + random.uniform(-0.2, 0.2)
        self.humidity = cfg["ideal_humidity"] + random.uniform(-1.0, 1.0)
        self.temp_ema = self.temp
        self.humidity_ema = self.humidity
        self.prev_temp = self.temp

        # Cumulative tracking
        self.cumulative_heat_exposure = 0.0
        self.time_above_safe_temperature = 0.0

        # Fault state
        self.fault_active = False
        self.fault_speed = 1.0
        self.fault_start_time = None

        # SmartSell inventory state
        self.quantity_kg = cfg["batch_weight_kg"] + random.uniform(
            -cfg["batch_weight_kg"] * 0.05,
             cfg["batch_weight_kg"] * 0.05
        )
        lo, hi = cfg["demand_init_range"]
        self.demand_score = random.uniform(lo, hi)
        self.purchase_cost_per_kg = cfg["purchase_cost_per_kg"] * random.uniform(0.95, 1.05)
        self.market_price_per_kg = cfg["market_price_per_kg"]

        # Buffers
        self.history: deque = deque(maxlen=HISTORY_LEN)
        self.window_360: deque = deque(maxlen=WINDOW_LEN)

        # Backfill initial 360 timesteps with realistic baseline readings
        self._backfill_360_window()

    def _backfill_360_window(self):
        """Pre-populates the 360-minute window with realistic historical sequence."""
        cfg = self.cfg
        t = self.temp
        h = self.humidity
        
        # Generate 360 historical timesteps stepping up to the current moment
        for i in range(WINDOW_LEN):
            hist_fraction = (i - WINDOW_LEN) / 60.0  # hours in the past
            hist_storage_hours = max(0.0, self.hours_in_cold_storage + hist_fraction)
            hist_age_hours = self.delay_hours + hist_storage_hours
            
            # Oscillate realistically around ideal temp (Mendeley ~12.5 min cycle)
            cycle_phase = (i % 13) / 13.0 * 2 * math.pi
            cycle_offset = 0.35 * math.sin(cycle_phase)
            t = cfg["ideal_temp"] + cycle_offset + random.gauss(0, 0.08)
            h = cfg["ideal_humidity"] + random.gauss(0, 0.3)
            
            door = 1 if (i % 90 == 0) else 0  # occasional door opening
            if door:
                t += 2.5
                h -= 10.0
            
            t_rate = 0.0 if i == 0 else random.gauss(0, 0.05)
            
            # 10-feature row
            feat_row = [
                round(t, 2),
                round(h, 1),
                door,
                round(hist_age_hours, 2),
                round(hist_storage_hours, 2),
                round(self.cumulative_heat_exposure, 3),
                round(self.time_above_safe_temperature, 3),
                round(t_rate, 3),
                cfg["encode"],
                self.picked_temp,
            ]
            self.window_360.append(feat_row)
            
            # Also fill history for UI chart
            if i >= WINDOW_LEN - HISTORY_LEN:
                self.history.append({
                    "temperature": round(t, 2),
                    "humidity": round(h, 1),
                    "door_open_event": door,
                    "produce_type": cfg["encode"],
                    "timestamp": None,
                })

    def trigger_fault(self, speed: float = 1.0):
        """Inject cooling fault — temperature climbs steadily toward ambient."""
        self.fault_active = True
        self.fault_speed = max(0.5, min(speed, 20.0))
        self.fault_start_time = time.time()

    def reset_fault(self):
        """Reset fault — cooling restores and temperature recovers."""
        self.fault_active = False
        self.fault_speed = 1.0
        self.fault_start_time = None

    def _update_demand(self):
        drift = random.uniform(-DEMAND_DRIFT_MAX, DEMAND_DRIFT_MAX)
        self.demand_score = max(20.0, min(100.0, self.demand_score + drift))

    def tick(self):
        """Advance simulation by 1 timestep (~1 simulated minute)."""
        cfg = self.cfg
        self.prev_temp = self.temp

        # Advance storage age
        step_hours = (TICK_INTERVAL / 60.0)
        self.hours_in_cold_storage += step_hours
        self.batch_age_hours += step_hours

        # Thermal evolution
        if self.fault_active:
            # Compressor failed: temperature rises toward Tout = 24.04°C (Mendeley)
            # CDTRR = 0.125°C/min scaled by fault_speed
            rise = 0.125 * self.fault_speed * (TICK_INTERVAL / 3.0)
            target_ambient = 24.04
            self.temp += (target_ambient - self.temp) * 0.02 * self.fault_speed + random.gauss(0, 0.05)
            self.temp = min(25.0, self.temp)
            # Humidity drifts down
            self.humidity = max(55.0, self.humidity - (0.15 * self.fault_speed))
        else:
            # Normal cooling cycling: mean-reversion toward ideal temp
            cycle_phase = (len(self.history) % 13) / 13.0 * 2 * math.pi
            cycle_offset = 0.25 * math.sin(cycle_phase)
            target_t = cfg["ideal_temp"] + cycle_offset
            self.temp += (target_t - self.temp) * 0.15 + random.gauss(0, cfg["temp_noise"])
            self.humidity += (cfg["ideal_humidity"] - self.humidity) * 0.10 + random.gauss(0, cfg["humidity_noise"])

        # EMA smoothing for chart display
        alpha = EMA_ALPHA if not self.fault_active else min(EMA_ALPHA * 2.0, 0.8)
        self.temp_ema = alpha * self.temp + (1 - alpha) * self.temp_ema
        self.humidity_ema = alpha * self.humidity + (1 - alpha) * self.humidity_ema

        # Door event (probabilistic)
        door_event = 1 if (random.random() < cfg["door_open_prob"] and not self.fault_active) else 0
        if door_event:
            self.temp += random.uniform(1.2, 2.5)  # ODTRR ~ 1.313°C/min
            self.humidity = max(60.0, self.humidity - random.uniform(8.0, 15.0))

        # Update cumulative heat metrics
        if self.temp > cfg["safe_temp"]:
            excess = self.temp - cfg["safe_temp"]
            self.cumulative_heat_exposure += (excess * step_hours)
            self.time_above_safe_temperature += step_hours

        temp_derivative = round(self.temp - self.prev_temp, 3)
        ts = datetime.utcnow().isoformat() + "Z"

        reading = {
            "temperature": round(self.temp_ema, 2),
            "humidity": round(self.humidity_ema, 1),
            "door_open_event": door_event,
            "produce_type": cfg["encode"],
            "timestamp": ts,
        }
        self.history.append(reading)

        # Append 10-feature vector to 360-timestep window
        feat_vector = [
            round(self.temp, 2),
            round(self.humidity, 1),
            door_event,
            round(self.batch_age_hours, 2),
            round(self.hours_in_cold_storage, 2),
            round(self.cumulative_heat_exposure, 3),
            round(self.time_above_safe_temperature, 3),
            temp_derivative,
            cfg["encode"],
            self.picked_temp,
        ]
        self.window_360.append(feat_vector)

        self._update_demand()
        return reading

    @property
    def last_reading(self) -> dict:
        if self.history:
            return dict(self.history[-1])
        return {}

    def get_window_360(self) -> np.ndarray:
        """Return exactly (360, 10) numpy array for PyTorch LSTM input."""
        arr = np.array(list(self.window_360), dtype=np.float32)
        if len(arr) < WINDOW_LEN:
            pad = np.repeat(arr[:1], WINDOW_LEN - len(arr), axis=0)
            arr = np.vstack([pad, arr])
        return arr[-WINDOW_LEN:]

    def get_window(self, size: int = 24) -> list:
        """Legacy compatibility method."""
        return list(self.history)[-size:]

    @property
    def metadata(self) -> dict:
        cfg = self.cfg
        return {
            "produce_type": self.produce_type,
            "display_name": cfg["display_name"],
            "batch_id": self.batch_id,
            "batch_weight_kg": cfg["batch_weight_kg"],
            "quantity_kg": round(self.quantity_kg, 1),
            "value_per_kg": cfg["value_per_kg"],
            "purchase_cost_per_kg": round(self.purchase_cost_per_kg, 2),
            "market_price_per_kg": round(self.market_price_per_kg, 2),
            "demand_score": round(self.demand_score, 1),
            "storage_since": self.storage_since.isoformat() + "Z",
            "fault_active": self.fault_active,
            "fault_speed": self.fault_speed,
            "color": cfg["color"],
            "perishability_factor": cfg["perishability_factor"],
        }


class SensorSimulator:
    def __init__(self):
        self.batches: Dict[str, ProduceBatch] = {
            "spinach":    ProduceBatch("spinach",    "SP-001"),
            "tomato":     ProduceBatch("tomato",     "TM-001"),
            "strawberry": ProduceBatch("strawberry", "SB-001"),
        }
        # Backward compatibility pointers
        self.batches["leafy_greens"] = self.batches["spinach"]
        self.batches["tomatoes"]     = self.batches["tomato"]
        self.batches["milk"]         = self.batches["strawberry"]

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            with self._lock:
                for k in CANONICAL_KEYS:
                    self.batches[k].tick()
            time.sleep(TICK_INTERVAL)

    def trigger_fault(self, produce_type: Optional[str] = None, speed: float = 1.0):
        with self._lock:
            if produce_type and produce_type in self.batches:
                self.batches[produce_type].trigger_fault(speed)
                return True
            elif not produce_type:
                for k in CANONICAL_KEYS:
                    self.batches[k].trigger_fault(speed)
                return True
        return False

    def trigger_all_faults(self, speed: float = 1.0):
        return self.trigger_fault(None, speed)

    def reset_fault(self, produce_type: Optional[str] = None):
        with self._lock:
            if produce_type and produce_type in self.batches:
                self.batches[produce_type].reset_fault()
            elif not produce_type:
                for k in CANONICAL_KEYS:
                    self.batches[k].reset_fault()

    def get_readings(self) -> dict:
        with self._lock:
            return {k: self.batches[k].last_reading for k in CANONICAL_KEYS}

    def get_history(self, produce_type: str, n: int = 30) -> list:
        with self._lock:
            if produce_type not in self.batches:
                return []
            return list(self.batches[produce_type].history)[-n:]

    def get_window_360(self, produce_type: str) -> np.ndarray:
        with self._lock:
            if produce_type not in self.batches:
                return np.zeros((WINDOW_LEN, 10), dtype=np.float32)
            return self.batches[produce_type].get_window_360()

    def get_window(self, produce_type: str) -> list:
        with self._lock:
            if produce_type not in self.batches:
                return []
            return self.batches[produce_type].get_window(24)

    def get_metadata(self) -> dict:
        with self._lock:
            return {k: self.batches[k].metadata for k in CANONICAL_KEYS}

    def get_batch_metadata(self, produce_type: str) -> dict:
        with self._lock:
            if produce_type not in self.batches:
                return {}
            return self.batches[produce_type].metadata

    def get_demand_score(self, produce_type: str) -> float:
        with self._lock:
            if produce_type not in self.batches:
                return 50.0
            return self.batches[produce_type].demand_score

    def get_quantity(self, produce_type: str) -> float:
        with self._lock:
            if produce_type not in self.batches:
                return 0.0
            return self.batches[produce_type].quantity_kg


# Singleton instance
simulator = SensorSimulator()
