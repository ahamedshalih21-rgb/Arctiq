"""
ColdSense — Live Sensor Simulator
Generates continuously updating sensor readings for three produce batches.
Supports: manual fault injection via trigger_fault(), speed multiplier.
"""

import threading
import time
import random
import math
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

# ── Produce configurations ─────────────────────────────────────────────────────
PRODUCE_CONFIGS = {
    "leafy_greens": {
        "encode": 0,
        "display_name": "Leafy Greens",
        "ideal_temp": 3.0,
        "ideal_humidity": 92.0,
        "temp_noise": 0.15,
        "humidity_noise": 0.6,
        "door_open_prob": 0.04,
        "base_shelf_life": 72.0,
        "heat_weight": 4.5,
        "humidity_weight": 1.5,
        "batch_weight_kg": 120.0,
        "value_per_kg": 3.50,  # USD
        "color": "#4ECDC4",
        "emoji": "🥬",
    },
    "tomatoes": {
        "encode": 1,
        "display_name": "Tomatoes",
        "ideal_temp": 13.0,
        "ideal_humidity": 87.0,
        "temp_noise": 0.20,
        "humidity_noise": 0.8,
        "door_open_prob": 0.03,
        "base_shelf_life": 120.0,
        "heat_weight": 2.5,
        "humidity_weight": 2.0,
        "batch_weight_kg": 200.0,
        "value_per_kg": 2.20,
        "color": "#FF6B6B",
        "emoji": "🍅",
    },
    "potatoes": {
        "encode": 2,
        "display_name": "Potatoes",
        "ideal_temp": 7.0,
        "ideal_humidity": 87.0,
        "temp_noise": 0.12,
        "humidity_noise": 0.9,
        "door_open_prob": 0.02,
        "base_shelf_life": 240.0,
        "heat_weight": 1.2,
        "humidity_weight": 3.8,
        "batch_weight_kg": 350.0,
        "value_per_kg": 0.90,
        "color": "#F7B731",
        "emoji": "🥔",
    },
}

HISTORY_LEN = 60        # number of readings kept per batch
TICK_INTERVAL = 3.0     # seconds between real-time ticks


class ProduceBatch:
    def __init__(self, produce_type: str, batch_id: str):
        cfg = PRODUCE_CONFIGS[produce_type]
        self.produce_type = produce_type
        self.batch_id = batch_id
        self.cfg = cfg
        self.storage_since = datetime.utcnow() - timedelta(hours=random.uniform(2, 8))

        # Initialize near-ideal conditions
        self.temp = cfg["ideal_temp"] + random.uniform(-0.5, 0.5)
        self.humidity = cfg["ideal_humidity"] + random.uniform(-2, 2)

        # Fault state
        self.fault_active = False
        self.fault_speed = 1.0
        self.temp_drift = 0.0
        self.humidity_drift = 0.0

        # Cumulative exposure (for label estimation)
        self.cumulative_exposure = 0.0

        # History ring buffer
        self.history: deque = deque(maxlen=HISTORY_LEN)

        # Generate initial history (last 24 readings, stable)
        self._fill_initial_history()

    def _fill_initial_history(self):
        for _ in range(24):
            t = self.temp + random.gauss(0, self.cfg["temp_noise"])
            h = self.humidity + random.gauss(0, self.cfg["humidity_noise"])
            d = 1 if random.random() < self.cfg["door_open_prob"] else 0
            self.history.append({
                "temperature": round(t, 2),
                "humidity": round(min(100, max(50, h)), 2),
                "door_open_event": d,
                "produce_type": self.cfg["encode"],
                "timestamp": None,  # filled on tick
            })

    def trigger_fault(self, speed: float = 1.0):
        """Inject a cooling fault — temperature rises, humidity fluctuates."""
        self.fault_active = True
        self.fault_speed = max(0.5, min(speed, 20.0))
        # Leafy greens: heat fault; potatoes: humidity fault; tomatoes: mixed
        cfg = self.cfg
        if self.produce_type == "leafy_greens":
            self.temp_drift = 0.35 * self.fault_speed
            self.humidity_drift = -0.20 * self.fault_speed
        elif self.produce_type == "potatoes":
            self.temp_drift = 0.10 * self.fault_speed
            self.humidity_drift = 0.55 * self.fault_speed
        else:  # tomatoes
            self.temp_drift = 0.25 * self.fault_speed
            self.humidity_drift = 0.30 * self.fault_speed

    def reset_fault(self):
        self.fault_active = False
        self.fault_speed = 1.0
        self.temp_drift = 0.0
        self.humidity_drift = 0.0

    def tick(self):
        """Advance simulator one step. Returns the new reading dict."""
        cfg = self.cfg
        # Random walk
        self.temp += random.gauss(0, cfg["temp_noise"])
        self.humidity += random.gauss(0, cfg["humidity_noise"])

        # Apply fault drift
        if self.fault_active:
            self.temp += self.temp_drift
            self.humidity += self.humidity_drift

        # Gentle mean-reversion when no fault
        else:
            self.temp += (cfg["ideal_temp"] - self.temp) * 0.02
            self.humidity += (cfg["ideal_humidity"] - self.humidity) * 0.02

        # Clamp
        self.temp = round(max(cfg["ideal_temp"] - 5, min(cfg["ideal_temp"] + 20, self.temp)), 2)
        self.humidity = round(max(50.0, min(100.0, self.humidity)), 2)

        door_event = 1 if random.random() < cfg["door_open_prob"] else 0
        ts = datetime.utcnow().isoformat() + "Z"

        reading = {
            "temperature": self.temp,
            "humidity": self.humidity,
            "door_open_event": door_event,
            "produce_type": cfg["encode"],
            "timestamp": ts,
        }
        self.history.append(reading)

        # Update cumulative exposure
        heat_excess = max(0.0, self.temp - cfg["ideal_temp"])
        hum_dev = abs(self.humidity - cfg["ideal_humidity"])
        self.cumulative_exposure += (
            cfg["heat_weight"] * heat_excess
            + cfg["humidity_weight"] * hum_dev * 0.1
            + 0.5 * door_event
        )

        return reading

    @property
    def last_reading(self) -> dict:
        if self.history:
            return dict(self.history[-1])
        return {}

    def get_window(self, size: int = 24) -> list:
        """Return last `size` readings as list, padded with oldest if needed."""
        h = list(self.history)
        if len(h) >= size:
            return h[-size:]
        # Pad with first element
        pad = [h[0]] * (size - len(h)) if h else []
        return pad + h

    @property
    def metadata(self) -> dict:
        cfg = self.cfg
        return {
            "produce_type": self.produce_type,
            "display_name": cfg["display_name"],
            "batch_id": self.batch_id,
            "batch_weight_kg": cfg["batch_weight_kg"],
            "value_per_kg": cfg["value_per_kg"],
            "storage_since": self.storage_since.isoformat() + "Z",
            "fault_active": self.fault_active,
            "fault_speed": self.fault_speed,
            "color": cfg["color"],
            "emoji": cfg["emoji"],
        }


class SensorSimulator:
    def __init__(self):
        self.batches: dict[str, ProduceBatch] = {
            "leafy_greens": ProduceBatch("leafy_greens", "LG-001"),
            "tomatoes": ProduceBatch("tomatoes", "TM-001"),
            "potatoes": ProduceBatch("potatoes", "PT-001"),
        }
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
                for batch in self.batches.values():
                    batch.tick()
            time.sleep(TICK_INTERVAL)

    def trigger_fault(self, produce_type: str, speed: float = 1.0):
        with self._lock:
            if produce_type in self.batches:
                self.batches[produce_type].trigger_fault(speed)
                return True
        return False

    def trigger_all_faults(self, speed: float = 1.0):
        with self._lock:
            for batch in self.batches.values():
                batch.trigger_fault(speed)

    def reset_fault(self, produce_type: str):
        with self._lock:
            if produce_type in self.batches:
                self.batches[produce_type].reset_fault()

    def get_readings(self) -> dict:
        with self._lock:
            return {pt: b.last_reading for pt, b in self.batches.items()}

    def get_history(self, produce_type: str, n: int = 30) -> list:
        with self._lock:
            if produce_type not in self.batches:
                return []
            return list(self.batches[produce_type].history)[-n:]

    def get_window(self, produce_type: str) -> list:
        with self._lock:
            if produce_type not in self.batches:
                return []
            return self.batches[produce_type].get_window(24)

    def get_metadata(self) -> dict:
        with self._lock:
            return {pt: b.metadata for pt, b in self.batches.items()}

    def get_batch_metadata(self, produce_type: str) -> dict:
        with self._lock:
            if produce_type not in self.batches:
                return {}
            return self.batches[produce_type].metadata


# Singleton instance
simulator = SensorSimulator()
