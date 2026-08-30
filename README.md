# ColdSense 🧊

**AI-powered cold-storage spoilage prediction dashboard** — Technova 2026 Hackathon Demo

---

## Problem Statement

Cold-storage facilities worldwide lose 15–35% of fresh produce to undetected spoilage events — cooling faults, door-left-open scenarios, and humidity spikes that go unnoticed until it's too late. **ColdSense** demonstrates how a lightweight AI system, reading inexpensive IoT sensors, can predict hours-until-spoilage risk per produce batch in real time — giving operators a window to intervene before loss occurs. In a simulated demo, ColdSense predicts across three produce types (leafy greens, tomatoes, potatoes) with a pre-trained Gradient Boosting model achieving **~6.4-hour MAE**, and visualises the Safe → Watch → Critical progression live on a polished React dashboard.

---

## Architecture

```
Synthetic Data          Pre-trained Model         Live Backend          React Frontend
──────────────          ─────────────────         ────────────          ──────────────
generate.py      →      train.py (GBR)     →      FastAPI :8000   →     Vite :5173
 6,000 sequences         saved .joblib              /api/readings         SensorChart
 144,000 rows            norm_params.json           /api/prediction       RiskBadge
 3 produce types         MAE ≈ 6.4 hrs             /api/trigger-fault    FaultControl
                                                    Simulator thread      ValueMetric
```

```
coldsense/
├── data_generator/generate.py      # Synthetic training data
├── model/
│   ├── train.py                    # GBR training + evaluation
│   ├── data/training_data.csv      # Generated dataset (144k rows)
│   ├── saved_model/                # coldsense_model.joblib + norm_params.json
│   └── plots/                      # loss_curve.png, sample_predictions.png
├── backend/
│   ├── main.py                     # FastAPI app
│   ├── simulator.py                # Live sensor stream
│   ├── predictor.py                # Model inference
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Main dashboard
│   │   ├── index.css               # Dark glassmorphism design
│   │   └── components/
│   │       ├── SensorChart.jsx     # Recharts dual-axis trend
│   │       ├── RiskBadge.jsx       # Safe/Watch/Critical indicator
│   │       ├── ValueMetric.jsx     # Value-preserved card
│   │       ├── BatchCard.jsx       # Batch metadata
│   │       └── FaultControl.jsx    # Demo fault trigger panel
│   ├── vite.config.js
│   └── package.json
└── README.md
```

---

## Setup & Run

### Prerequisites
- Python 3.9+ (tested on 3.13.1)
- Node.js 18+ (tested on 24.x)

### Step 1 — Install Python dependencies

```bash
cd coldsense/backend
pip install fastapi "uvicorn[standard]" numpy scikit-learn joblib matplotlib pandas
```

### Step 2 — Generate training data (one-time)

```bash
cd coldsense
python data_generator/generate.py
# → creates model/data/training_data.csv (144,000 rows)
```

### Step 3 — Train the model (one-time)

```bash
python model/train.py
# → saves model/saved_model/coldsense_model.joblib
# → saves model/plots/sample_predictions.png
# → prints validation MAE (~6.4 hours)
```

> **Note:** TensorFlow is optional. The training script automatically falls back to a `GradientBoostingRegressor` if TF is unavailable. The backend/frontend work identically either way.

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

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System health check |
| GET | `/api/readings` | Live sensor readings (all batches) |
| GET | `/api/readings/{produce_type}` | Reading for one batch |
| GET | `/api/history/{produce_type}?n=30` | Last N readings for trend chart |
| GET | `/api/prediction` | Model prediction for all batches |
| GET | `/api/prediction/{produce_type}` | Prediction for one batch |
| GET | `/api/value` | Value/loss-prevented metric |
| POST | `/api/trigger-fault` | **Inject cooling fault (demo control)** |
| POST | `/api/reset-fault` | Reset fault state |

**Trigger fault example:**
```bash
curl -X POST http://localhost:8000/api/trigger-fault \
  -H "Content-Type: application/json" \
  -d '{"produce_type": "leafy_greens", "speed": 5}'
```

- `produce_type`: `"leafy_greens"` / `"tomatoes"` / `"potatoes"` / `null` (all)
- `speed`: drift multiplier `1`–`20` (5 = 5× faster than real-time)

---

## Demo Recording Guide

1. Start backend + frontend as above
2. Allow 10–15 seconds for initial stable readings to appear
3. Select **Leafy Greens** tab (fastest spoiler, most dramatic)
4. In the **Demo Control** panel (bottom-right):
   - Set speed to **5×**
   - Click **⚡ Trigger Cooling Fault**
5. Watch temperature drift up, risk transition Safe → Watch → Critical within ~60–90 seconds
6. Repeat for Tomatoes/Potatoes as time allows
7. Use **↺ Reset Fault** to return to stable for a clean before/after

---

## Model Details

| Property | Value |
|---|---|
| Model type | GradientBoostingRegressor (scikit-learn) |
| Input | 24-hour rolling window × [temp, humidity, door_event, produce_type] |
| Output | `hours_until_spoilage_risk` (regression) |
| Training data | 6,000 sequences × 24 timesteps = 144,000 rows (synthetic) |
| Validation MAE | ~6.4 hours |
| Risk thresholds | Safe > 48h, Watch > 24h, Critical ≤ 24h |
| Training time | ~25 seconds (CPU) |

---

## Path to Real IoT Hardware

ColdSense is currently fully simulation-based. The path to real hardware integration is straightforward:

| Component | Purpose | Part |
|---|---|---|
| Temperature + Humidity | Primary spoilage sensor | **DHT22** or **SHT31** |
| Precise temperature | Produce core temp | **DS18B20** (waterproof probe) |
| Door open detection | Cold-air loss event | **Magnetic reed switch** |
| Compressor health | Cooling system fault | **ACS712** current sensor |
| Edge compute + WiFi | Sensor hub + MQTT/HTTP | **ESP32** microcontroller |

Replace `simulator.py`'s `_loop()` with an MQTT subscriber or HTTP polling loop reading from the ESP32. The rest of the backend and frontend are hardware-agnostic.

---

## Produce Spoilage Profiles

| Produce | Ideal Temp | Ideal Humidity | Base Shelf Life | Main Risk |
|---|---|---|---|---|
| 🥬 Leafy Greens | 3°C | 92% | 72 hours | Heat (fast spoiler) |
| 🍅 Tomatoes | 13°C | 87% | 120 hours | Heat + humidity |
| 🥔 Potatoes | 7°C | 87% | 240 hours | Humidity (hardy) |

---

*Built for Technova 2026 · All sensor data is simulated · No real hardware required*
