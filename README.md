# ColdSense
**AI-powered cold-storage monitoring and recovery exchange dashboard** — Technova 2026 Hackathon Demo

---

## Problem Statement

Cold-storage facilities worldwide lose 15–35% of fresh produce to undetected spoilage events — cooling faults, door-left-open scenarios, and humidity spikes that go unnoticed until it's too late. **ColdSense** demonstrates how a lightweight AI system, reading inexpensive IoT sensors, can:

1. **Predict hours-until-spoilage risk** per produce batch in real time using a PyTorch LSTM sequence model.
2. **Monitor compressor health** using a simulation-based Arrhenius-degradation model.
3. **Create recovery listings** automatically when a batch approaches spoilage — connecting vendors to nearby buyers to recover economic value that would otherwise be lost.

---

## Architecture

```
Sequence Data           PyTorch LSTM Model        Live Backend          React Frontend
─────────────           ──────────────────        ────────────          ──────────────
Mendeley Calibrated →   train.py (LSTM)    →      FastAPI :8000   →     Vite :5173
 360-step windows        coldsense_lstm.pt         /api/readings         SensorChart
 10 features             scaler.joblib             /api/prediction       RiskBadge
 3 produce types         MAE ≈ 5.35 hrs            /api/compressor       FaultControl
                                                   /api/recovery/listings CompressorHealth
                                                   /api/recovery/buyers   RecoveryExchange
```

```
coldsense/
├── data_generator/generate.py          # Synthetic training data
├── model/
│   ├── train.py                        # PyTorch LSTM training + evaluation
│   ├── data/                           # Sequence datasets (train/test_sequences.npz)
│   ├── saved_model/                    # coldsense_lstm.pt, scaler.joblib, scaler_params.json, metrics.json
│   └── plots/
├── backend/
│   ├── main.py                         # FastAPI app + all endpoints
│   ├── simulator.py                    # Live sensor stream & 360-step sliding window buffer
│   ├── predictor.py                    # PyTorch LSTM model inference
│   ├── compressor_simulator.py         # Arrhenius-based compressor health model
│   ├── recovery_exchange.py            # Risk Stock / Recovery Exchange service
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                     # Main dashboard
│   │   ├── index.css                   # Industrial HMI design system
│   │   └── components/
│   │       ├── SensorChart.jsx         # Recharts dual-axis trend
│   │       ├── RiskBadge.jsx           # Safe/Watch/Critical indicator
│   │       ├── ValueMetric.jsx         # Value-preserved card
│   │       ├── BatchCard.jsx           # Batch metadata
│   │       ├── FaultControl.jsx        # Demo fault trigger panel
│   │       ├── CompressorHealth.jsx    # Compressor health monitoring card
│   │       └── RecoveryExchange.jsx    # Risk Stock / buyer interest module
│   ├── vite.config.js
│   └── package.json
└── README.md
```

---

## Currently Implemented

### Spoilage Prediction
1. **PyTorch LSTM Regressor** — active spoilage prediction model (2-layer LSTM + MLP head)
2. Simulated sensor/environmental data for three produce types
3. Temperature monitoring (per produce batch)
4. Humidity monitoring (per produce batch)
5. Door event simulation and monitoring
6. Live/simulated dashboard updates (4-second polling)
7. Spoilage risk classification: Safe / Watch / Critical

### Compressor Health Monitoring
8. Simulation-based compressor health monitoring subsystem
9. Compressor temperature simulation (mean-reverting, demand-influenced)
10. Compressor current simulation (on/off state × duty cycle)
11. Duty cycle monitoring (exponential moving average of on-time)
12. Runtime accumulation (continuous compressor-on time tracking)
13. Start-stop cycle tracking with hysteresis (no double-counting)
14. **Arrhenius-based temperature-dependent degradation** — see model note below
15. Cumulative degradation calculation (4-contributor model)
16. Compressor Health Score (0–100, derived from cumulative degradation)
17. Health status classification: Healthy / Warning / Critical
18. Demo mode: accelerated degradation for presentations

### Risk Stock / Recovery Exchange
19. Automatic Risk Stock listing creation when LSTM predicts Watch or Critical risk
20. Listing deduplication — updates existing listing rather than creating duplicates
21. Recovery Exchange prototype workflow (Active → Interested → Reserved → Sold)
22. Prototype recovery price heuristic (produce-specific INR pricing)
23. Simulated nearby buyers (5 buyer types: Juice Stall, Canteen, Animal Feed Vendor, etc.)
24. Buyer interest state machine (Pending → Interested / Not Interested → Reserved → Sold)
25. Buyer interest simulation (produce-preference-weighted probability)
26. Listing status management API
27. Buyer interest status API

---

## Future Hardware Integration

ColdSense is currently fully simulation-based. The path to real hardware integration is straightforward:

| Component | Purpose | Part |
|---|---|---|
| Temperature + Humidity | Primary spoilage sensor | **DHT22** or **SHT31** |
| Precise temperature | Produce core temperature | **DS18B20** (waterproof probe) |
| Door open detection | Cold-air loss event | **Magnetic reed switch** |
| Compressor current | Compressor health monitoring | **ACS712** current sensor |
| Edge compute + WiFi | Sensor hub + MQTT/HTTP | **ESP32** microcontroller |
| Relay/control interface | Future compressor control | Relay module (future scope) |

Replace `simulator.py`'s `_loop()` with an MQTT subscriber or HTTP polling loop reading from the ESP32. Replace `compressor_simulator.py`'s `_loop()` with ACS712 + DS18B20 readings. The rest of the backend and frontend are hardware-agnostic.

---

## Model Accuracy Note

| Property | Value |
|---|---|
| Spoilage model | PyTorch LSTM (2-layer LSTM + MLP head) |
| Input | 360 timesteps (6 hours @ 1-min resolution) × 10 features |
| Output | `remaining_shelf_life_hours` (continuous regression) |
| Training data | Mendeley-calibrated sequence datasets (3 produce types) |
| Validation MAE | ~5.36 hours |
| Test R² Score | 0.9893 |
| Risk thresholds | Low > 24h, Medium 12–24h, High ≤ 12h |

> **PyTorch LSTM Architecture:** The active model uses a 2-layer LSTM backbone (hidden dimension 64, dropout 0.20) coupled with a multi-layer perceptron regression head trained on 360-timestep sequence windows.

### Compressor Degradation Model Note

The compressor health model uses an **Arrhenius-based temperature stress factor**:

```
k(T) = A × exp(−Ea / (R × T))
temperature_stress_factor = k(T) / k(T_reference)
temperature_damage = BASE_RATE × temperature_stress_factor × delta_time
```

**Parameters are prototype simulation values. This is NOT manufacturer-calibrated compressor lifetime prediction.** The model is designed to demonstrate temperature-dependent degradation behaviour in a simulation context. It is not suitable for real predictive maintenance decisions without calibration against actual compressor failure data.

### Recovery Exchange Pricing Note

Recovery prices are calculated using a prototype heuristic:
```
recovery_price = batch_value × clip(remaining_hours / reference_window, 0.10, 0.80)
```
This is **not a validated market pricing algorithm**. Prices are illustrative only.

---

## Setup & Run

### Prerequisites
- Python 3.9+ (tested on 3.13.1)
- Node.js 18+ (tested on 24.x)

### Step 1 — Install Python dependencies

```bash
cd coldsense/backend
pip install fastapi "uvicorn[standard]" numpy torch scikit-learn joblib matplotlib pandas
```

### Step 2 — Train the model (one-time, if not already trained)

```bash
cd coldsense
python model/train.py
# → saves model/saved_model/coldsense_lstm.pt
# → saves model/saved_model/scaler.joblib & scaler_params.json
# → prints validation MAE (~5.36 hours, R² ≈ 0.989)
```

### Step 4 — Start the backend

```bash
cd coldsense/backend
uvicorn main:app --port 8000 --reload
# → API running at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

### Step 5 — Start the frontend

```bash
cd coldsense/frontend
# On Windows PowerShell:
powershell -ExecutionPolicy Bypass -Command "npm run dev"
# → Dashboard running at http://localhost:5173
```

---

## API Reference

### Existing Endpoints (unchanged)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System health check |
| GET | `/api/readings` | Live sensor readings (all batches) |
| GET | `/api/readings/{produce_type}` | Reading for one batch |
| GET | `/api/history/{produce_type}?n=30` | Last N readings for trend chart |
| GET | `/api/prediction` | PyTorch LSTM spoilage prediction for all batches (360-min window) |
| GET | `/api/prediction/{produce_type}` | Prediction for one batch |
| GET | `/api/value` | Value/loss-prevented metric |
| POST | `/api/trigger-fault` | Inject cooling fault (demo control) |
| POST | `/api/reset-fault` | Reset fault state |

### New Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/compressor` | Compressor health snapshot (Arrhenius model) |
| GET | `/api/recovery/listings` | Active Risk Stock listings |
| GET | `/api/recovery/listings/all` | All listings including SOLD/EXPIRED |
| GET | `/api/recovery/buyers` | Simulated nearby buyer dataset |
| GET | `/api/recovery/listings/{batch_id}/buyers` | Buyer interest for a listing |
| POST | `/api/recovery/listings/{batch_id}/interest?buyer_id=B001` | Simulate buyer interest |
| POST | `/api/recovery/listings/{batch_id}/status` | Update listing status |


---

## Produce Spoilage Profiles (Mendeley Calibrated)

Calibrated against empirical reefer data and respiration decay profiles from Mendeley Data ([DOI: 10.17632/kphtgxn3ff.4](https://data.mendeley.com/datasets/kphtgxn3ff/4)):

| Produce | Ideal Temp | Safe Temp | Ideal Humidity | Base Shelf Life | Respiration Q10 | Sensitivity & Behavior |
|---|---|---|---|---|---|---|
| **Spinach** | 2.0°C | 4.0°C | 95% | 288 hours (12 days) | 2.8 | Highly heat-sensitive leafy green |
| **Tomato** | 13.0°C | 15.0°C | 88% | 360 hours (15 days) | 2.2 | Chilling injury occurs below 10°C; heat-sensitive |
| **Strawberry** | 1.5°C | 4.0°C | 92% | 192 hours (8 days) | 2.5 | High perishability; rapid decay upon warming |

### 10-Feature Sequence Architecture (360 Timesteps)
1. `temperature` (°C)
2. `humidity` (%)
3. `door_event` (0 or 1)
4. `batch_age_hours`
5. `hours_in_cold_storage`
6. `cumulative_heat_exposure` (degree-hours)
7. `time_above_safe_temperature` (hours)
8. `temperature_rate_of_change` (°C/min)
9. `produce_type` (0: Spinach, 1: Tomato, 2: Strawberry)
10. `batch_picked_temperature` (°C)

### Spoilage Risk Thresholds
- **> 24 hours**: LOW RISK (Safe operational zone)
- **12–24 hours**: MEDIUM RISK (Intervention preparation zone)
- **≤ 12 hours**: HIGH RISK (Critical intervention / clearance sale zone)

> [!NOTE]
> **Scientific Operational Reference Disclaimer**: ColdSense provides operational decision support based on monitored temperature histories and kinetic respiration decay models. It does not claim to measure the exact cellular biological state of produce in situ without destructive testing.