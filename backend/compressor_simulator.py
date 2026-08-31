"""
ColdSense — Compressor Health Simulator
========================================
Simulates compressor operating conditions and calculates a health score
derived from an Arrhenius-based temperature-dependent degradation model
combined with runtime, duty-cycle, and start-stop cycle contributions.

ARCHITECTURE NOTE:
  This module is a simulation-based prototype.
  It is designed to be compatible with future hardware integration via:
    - ACS712 current sensor (current draw)
    - DS18B20 temperature probe (compressor body temperature)
    - Magnetic reed switch / relay state (on/off cycling)
    - ESP32 microcontroller (edge compute + WiFi/MQTT)

SIMULATION MODE:
  DEMO_MODE = True  → accelerated degradation, suitable for presentations
  DEMO_MODE = False → slow realistic degradation over many hours

ARRHENIUS MODEL (PROTOTYPE — NOT MANUFACTURER-CALIBRATED):
  k(T) = A * exp(-Ea / (R * T))
  temperature_stress_factor = k(T) / k(T_reference)

  The stress factor is normalized to a reference temperature so the
  Arrhenius rate is used relatively rather than as an absolute damage quantity.
  This avoids unrealistic instantaneous health loss from raw k(T) values.

  Parameters are prototype simulation values only.
"""

import math
import threading
import time
import random
from typing import Optional

# ── Simulation Mode ────────────────────────────────────────────────────────────
# Set DEMO_MODE = True for accelerated degradation during presentations.
# Set DEMO_MODE = False for realistic long-running simulation behaviour.
DEMO_MODE = True

# Scaling multiplier applied to all degradation contributions in DEMO mode.
# In NORMAL mode this is 1.0 (no scaling).
DEMO_SCALE = 180.0   # 180× — makes visible health change within ~60–120 seconds

# ── Tick interval ──────────────────────────────────────────────────────────────
# Must match or be compatible with the sensor simulator tick rate.
COMPRESSOR_TICK_INTERVAL = 3.0   # seconds

# ── Arrhenius Parameters (PROTOTYPE SIMULATION — NOT CALIBRATED) ───────────────
# k(T) = A * exp(-Ea / (R * T))
#
# A  : Pre-exponential / frequency factor (prototype value)
# Ea : Activation energy in J/mol (prototype simulation parameter)
# R  : Universal gas constant, J/(mol·K) — fixed physical constant
# T  : Absolute temperature in Kelvin (compressor body temp converted from °C)
#
# These values are NOT based on manufacturer lifetime data.
# They are chosen to produce plausible relative temperature-stress behaviour.
ARRHENIUS_A  = 1.0e6     # Pre-exponential factor (prototype)
ARRHENIUS_EA = 50_000.0  # Activation energy J/mol (prototype)
R_GAS        = 8.314      # Universal gas constant J/(mol·K)

# Reference compressor operating temperature (°C) — nominal healthy operating point.
# The stress factor is normalised to this temperature, so at T_ref the factor = 1.0.
T_REFERENCE_CELSIUS = 35.0

# ── Compressor Operating Envelope ─────────────────────────────────────────────
# Nominal simulated compressor temperatures (°C)
COMP_TEMP_NOMINAL   = 35.0   # Healthy baseline
COMP_TEMP_MAX       = 70.0   # Upper simulation bound
COMP_TEMP_MIN       = 25.0   # Lower simulation bound (pre-warmup or low demand)

# Nominal current draw (Amperes, simulated)
COMP_CURRENT_ON     = 2.80   # Current when compressor is running
COMP_CURRENT_OFF    = 0.05   # Standby / off-state leakage
COMP_CURRENT_NOISE  = 0.08   # Gaussian noise on current reading

# Duty cycle boundaries (fraction: 0.0–1.0)
DUTY_CYCLE_MIN      = 0.35   # Minimum realistic duty cycle under load
DUTY_CYCLE_MAX      = 0.95   # Maximum before thermal stress kicks in hard

# ── Degradation Contribution Rates (PROTOTYPE SIMULATION PARAMETERS) ───────────
# All rates are per second in NORMAL mode. Scaled by DEMO_SCALE in DEMO mode.

# A. Arrhenius temperature-driven base damage rate (at reference temperature)
#    Units: normalised degradation units per second
BASE_TEMP_DAMAGE_RATE   = 2.0e-8   # prototype

# B. Runtime damage rate (continuous wear from operation time)
#    Units: normalised degradation units per second of runtime
RUNTIME_DAMAGE_RATE     = 5.0e-9   # prototype

# C. Duty-cycle stress coefficient
#    High duty cycle (fraction near 1.0) amplifies this contribution.
#    Units: normalised degradation units per second, per unit duty cycle
DUTY_CYCLE_STRESS_RATE  = 1.5e-8   # prototype

# D. Start-stop cycle stress (mechanical fatigue per cycle)
#    Units: normalised degradation units per start-stop event
CYCLE_STRESS_PER_EVENT  = 5.0e-6   # prototype

# ── Health Score Thresholds ────────────────────────────────────────────────────
HEALTH_HEALTHY_THRESHOLD = 75.0    # >= 75 → Healthy
HEALTH_WARNING_THRESHOLD = 45.0    # 45–74 → Warning
# < 45 → Critical

# Initial cumulative damage at startup (simulates a unit already in service)
INITIAL_DAMAGE = 0.008   # ~0.8% accumulated, starts health at ~99.2

# ── Helper: Arrhenius rate ─────────────────────────────────────────────────────

def _arrhenius_rate(temp_celsius: float) -> float:
    """Return Arrhenius degradation rate k(T) for a given temperature in °C."""
    T_kelvin = temp_celsius + 273.15
    return ARRHENIUS_A * math.exp(-ARRHENIUS_EA / (R_GAS * T_kelvin))


# Pre-compute reference rate once
_K_REFERENCE = _arrhenius_rate(T_REFERENCE_CELSIUS)


def _temperature_stress_factor(temp_celsius: float) -> float:
    """
    Normalised Arrhenius stress factor relative to reference temperature.
    At T = T_REFERENCE_CELSIUS → factor = 1.0.
    Higher temperature → factor > 1.0 (more stress).
    Lower temperature  → factor < 1.0 (less stress).
    """
    k_T = _arrhenius_rate(temp_celsius)
    return k_T / _K_REFERENCE


# ── Compressor Health Model ────────────────────────────────────────────────────

def _health_status(score: float) -> str:
    """Return health status label from score (0–100)."""
    if score >= HEALTH_HEALTHY_THRESHOLD:
        return "Healthy"
    elif score >= HEALTH_WARNING_THRESHOLD:
        return "Warning"
    return "Critical"


class CompressorSimulator:
    """
    Simulation-based compressor health monitor.

    Models compressor operating conditions (temperature, current, duty cycle,
    runtime, start-stop cycles) and derives a health score via an Arrhenius-
    based cumulative degradation model.

    Integrates with the cold-storage sensor simulator:
    - When cooling fault is active, increases simulated demand/duty cycle/temp.
    - Otherwise mean-reverts toward nominal operating conditions.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # ── Operating state ────────────────────────────────────────────────────
        self.comp_temp: float   = COMP_TEMP_NOMINAL + random.uniform(-2.0, 2.0)
        self.is_running: bool   = True   # Is compressor motor currently on?
        self.duty_cycle: float  = 0.55   # Rolling duty cycle estimate

        # ── Accumulators ───────────────────────────────────────────────────────
        self.runtime_seconds: float     = random.uniform(600, 1800)  # Pre-seeded runtime
        self.start_stop_cycles: int     = random.randint(3, 12)      # Pre-seeded cycles
        self.cumulative_damage: float   = INITIAL_DAMAGE

        # Internal cycle tracking (hysteresis to avoid double-counting)
        self._prev_running: bool = True
        self._on_ticks: int  = 10   # Recent ticks spent running
        self._total_ticks: int = 18  # Total recent ticks for duty calc

        # ── External context ───────────────────────────────────────────────────
        # Set by main simulation loop to reflect cold-storage conditions.
        self._any_fault_active: bool = False
        self._avg_storage_temp: float = 5.0  # mean storage temp, drives demand

    # ── Public interface ───────────────────────────────────────────────────────

    def update_context(self, any_fault: bool, avg_storage_temp: float):
        """Called by the main simulation loop to pass current cold-storage state."""
        with self._lock:
            self._any_fault_active = any_fault
            self._avg_storage_temp = avg_storage_temp

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def get_status(self) -> dict:
        """Return a snapshot of current compressor health data."""
        with self._lock:
            stress = _temperature_stress_factor(self.comp_temp)
            score  = max(0.0, min(100.0, 100.0 - self.cumulative_damage * 100.0))
            return {
                "health_score":         round(score, 1),
                "health_status":        _health_status(score),
                "compressor_temperature": round(self.comp_temp, 1),
                "compressor_current":   self._current_reading(),
                "duty_cycle":           round(self.duty_cycle * 100.0, 1),
                "arrhenius_stress_factor": round(stress, 4),
                "cumulative_damage":    round(self.cumulative_damage, 6),
                "runtime_hours":        round(self.runtime_seconds / 3600.0, 2),
                "start_stop_cycles":    self.start_stop_cycles,
                "demo_mode":            DEMO_MODE,
                "simulation_note": (
                    "Prototype simulation — Arrhenius parameters are not "
                    "manufacturer-calibrated. Degradation rates are illustrative only."
                ),
            }

    # ── Internal simulation loop ───────────────────────────────────────────────

    def _loop(self):
        while self._running:
            with self._lock:
                self._tick()
            time.sleep(COMPRESSOR_TICK_INTERVAL)

    def _tick(self):
        """Advance compressor simulation by one time step."""
        dt = COMPRESSOR_TICK_INTERVAL  # seconds per tick
        scale = DEMO_SCALE if DEMO_MODE else 1.0

        # ── 1. Update compressor temperature ──────────────────────────────────
        # Higher cooling demand (fault, higher storage temp) pushes temperature up.
        demand_boost = 8.0 if self._any_fault_active else 0.0
        # Mean-revert toward (nominal + demand_boost)
        target_temp = COMP_TEMP_NOMINAL + demand_boost
        self.comp_temp += (target_temp - self.comp_temp) * 0.05
        self.comp_temp += random.gauss(0.0, 0.4)   # thermal noise
        self.comp_temp  = max(COMP_TEMP_MIN, min(COMP_TEMP_MAX, self.comp_temp))

        # ── 2. Update on/off cycling ───────────────────────────────────────────
        # Compressor is more likely to be running when demand is high.
        target_duty = 0.75 if self._any_fault_active else 0.55
        # Probabilistic state: running if random draw < current duty cycle
        should_run = random.random() < target_duty
        if should_run != self._prev_running:
            # State transition → count start-stop if transitioning to ON
            if should_run and not self._prev_running:
                self.start_stop_cycles += 1
        self.is_running   = should_run
        self._prev_running = should_run

        # ── 3. Update rolling duty cycle (window of recent ticks) ─────────────
        self._total_ticks += 1
        if self.is_running:
            self._on_ticks += 1
        # Use exponential moving average for duty cycle
        instant_duty = 1.0 if self.is_running else 0.0
        alpha = 0.12  # smoothing factor (higher = faster response)
        self.duty_cycle = alpha * instant_duty + (1.0 - alpha) * self.duty_cycle
        self.duty_cycle = max(DUTY_CYCLE_MIN * 0.5, min(1.0, self.duty_cycle))

        # ── 4. Runtime accumulation ────────────────────────────────────────────
        if self.is_running:
            self.runtime_seconds += dt

        # ── 5. Arrhenius temperature stress ───────────────────────────────────
        stress_factor = _temperature_stress_factor(self.comp_temp)
        temp_damage = BASE_TEMP_DAMAGE_RATE * stress_factor * dt

        # ── 6. Runtime contribution ────────────────────────────────────────────
        runtime_damage = RUNTIME_DAMAGE_RATE * dt if self.is_running else 0.0

        # ── 7. Duty cycle stress ───────────────────────────────────────────────
        duty_damage = DUTY_CYCLE_STRESS_RATE * self.duty_cycle * dt

        # ── 8. Accumulate total degradation ───────────────────────────────────
        # Cycle stress is accumulated on each new start event (tracked above).
        # Here we only add continuous damage. Cycle damage was added at event.
        tick_damage = (temp_damage + runtime_damage + duty_damage) * scale

        self.cumulative_damage += tick_damage

        # Clamp total damage so health score doesn't go below 0
        self.cumulative_damage = min(1.0, self.cumulative_damage)

    def _current_reading(self) -> float:
        """Simulated current draw in Amperes."""
        if self.is_running:
            base = COMP_CURRENT_ON + self.duty_cycle * 0.4
        else:
            base = COMP_CURRENT_OFF
        noise = random.gauss(0.0, COMP_CURRENT_NOISE)
        return round(max(0.0, base + noise), 2)

    # Start-stop cycle stress: applied at event time (in _tick above directly)
    # This method kept for documentation clarity.
    def _apply_cycle_stress(self):
        self.cumulative_damage += CYCLE_STRESS_PER_EVENT * (DEMO_SCALE if DEMO_MODE else 1.0)


# Singleton instance
compressor_sim = CompressorSimulator()
