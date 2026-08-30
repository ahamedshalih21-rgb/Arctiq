"""
ColdSense — FastAPI Backend
Run: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import time
import logging

from simulator import simulator, PRODUCE_CONFIGS
from predictor import predictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coldsense")

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ColdSense API",
    description="Cold-storage spoilage prediction backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    logger.info("Loading model...")
    try:
        predictor.load()
        logger.info("Model loaded successfully.")
    except FileNotFoundError as e:
        logger.error(f"Model not found: {e}")
        logger.error("Run 'python model/train.py' to train the model first.")

    logger.info("Starting sensor simulator...")
    simulator.start()
    logger.info("Simulator running.")


@app.on_event("shutdown")
async def shutdown_event():
    simulator.stop()


# ── Models ─────────────────────────────────────────────────────────────────────
class FaultTriggerRequest(BaseModel):
    produce_type: Optional[str] = None   # None → trigger all
    speed: Optional[float] = 1.0


class FaultResetRequest(BaseModel):
    produce_type: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────
VALID_PRODUCE = list(PRODUCE_CONFIGS.keys())

def validate_produce(produce_type: str):
    if produce_type not in VALID_PRODUCE:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid produce_type. Must be one of: {VALID_PRODUCE}"
        )


def build_prediction_for(produce_type: str) -> dict:
    window = simulator.get_window(produce_type)
    if not window:
        return {}
    prediction = predictor.predict(window)
    meta = simulator.get_batch_metadata(produce_type)
    value = predictor.predict_value(
        prediction,
        meta.get("batch_weight_kg", 100),
        meta.get("value_per_kg", 1.0),
    )
    return {
        "produce_type": produce_type,
        "batch_id": meta.get("batch_id"),
        **prediction,
        "value": value,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": predictor._loaded,
        "model_type": predictor.model_type,
        "simulator_running": simulator._running,
        "timestamp": time.time(),
    }


@app.get("/api/readings")
def get_readings():
    """Latest sensor readings for all produce batches."""
    readings = simulator.get_readings()
    meta = simulator.get_metadata()
    result = {}
    for pt, reading in readings.items():
        result[pt] = {
            **reading,
            "batch_id": meta[pt]["batch_id"],
            "display_name": meta[pt]["display_name"],
            "emoji": meta[pt]["emoji"],
            "fault_active": meta[pt]["fault_active"],
            "fault_speed": meta[pt]["fault_speed"],
            "storage_since": meta[pt]["storage_since"],
        }
    return result


@app.get("/api/readings/{produce_type}")
def get_reading_for(produce_type: str):
    """Latest reading for a specific produce type."""
    validate_produce(produce_type)
    readings = simulator.get_readings()
    meta = simulator.get_batch_metadata(produce_type)
    return {**readings.get(produce_type, {}), **meta}


@app.get("/api/history/{produce_type}")
def get_history(produce_type: str, n: int = Query(30, ge=1, le=60)):
    """Last N readings for trend chart (default 30)."""
    validate_produce(produce_type)
    history = simulator.get_history(produce_type, n)
    return {"produce_type": produce_type, "count": len(history), "readings": history}


@app.get("/api/prediction")
def get_all_predictions():
    """Model prediction for all batches."""
    if not predictor._loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet. Check server logs.")
    result = {}
    for pt in VALID_PRODUCE:
        result[pt] = build_prediction_for(pt)
    return result


@app.get("/api/prediction/{produce_type}")
def get_prediction_for(produce_type: str):
    """Model prediction for a specific produce type."""
    validate_produce(produce_type)
    if not predictor._loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")
    return build_prediction_for(produce_type)


@app.get("/api/value")
def get_value():
    """Estimated value/loss-prevented for all batches."""
    if not predictor._loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")
    result = {}
    total_preserved = 0.0
    total_at_risk = 0.0
    for pt in VALID_PRODUCE:
        p = build_prediction_for(pt)
        result[pt] = p.get("value", {})
        total_preserved += p.get("value", {}).get("value_preserved_usd", 0)
        total_at_risk += p.get("value", {}).get("value_at_risk_usd", 0)
    result["_totals"] = {
        "total_preserved_usd": round(total_preserved, 2),
        "total_at_risk_usd": round(total_at_risk, 2),
    }
    return result


@app.post("/api/trigger-fault")
def trigger_fault(body: FaultTriggerRequest):
    """
    Trigger a cooling fault for demo purposes.
    - produce_type: specific batch, or null/omitted for all batches
    - speed: multiplier (1.0 = real-time drift, 5.0 = 5x faster, max 20)
    """
    speed = max(0.5, min(20.0, body.speed or 1.0))

    if body.produce_type:
        validate_produce(body.produce_type)
        success = simulator.trigger_fault(body.produce_type, speed)
        if not success:
            raise HTTPException(status_code=404, detail="Produce type not found in simulator.")
        return {
            "status": "fault_triggered",
            "produce_type": body.produce_type,
            "speed": speed,
            "message": f"Fault injected for {body.produce_type} at {speed}x speed"
        }
    else:
        simulator.trigger_all_faults(speed)
        return {
            "status": "fault_triggered",
            "produce_type": "all",
            "speed": speed,
            "message": f"Fault injected for all batches at {speed}x speed"
        }


@app.post("/api/reset-fault")
def reset_fault(body: FaultResetRequest):
    """Reset fault state for a batch (or all)."""
    if body.produce_type:
        validate_produce(body.produce_type)
        simulator.reset_fault(body.produce_type)
        return {"status": "reset", "produce_type": body.produce_type}
    else:
        for pt in VALID_PRODUCE:
            simulator.reset_fault(pt)
        return {"status": "reset", "produce_type": "all"}


@app.get("/api/status")
def get_status():
    """Full system status snapshot — readings + predictions + metadata."""
    if not predictor._loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")

    result = {}
    readings = simulator.get_readings()
    meta = simulator.get_metadata()

    for pt in VALID_PRODUCE:
        pred = build_prediction_for(pt)
        result[pt] = {
            "reading": readings.get(pt, {}),
            "metadata": meta.get(pt, {}),
            "prediction": {
                "hours_remaining": pred.get("hours_remaining"),
                "risk_level": pred.get("risk_level"),
                "confidence": pred.get("confidence"),
            },
            "value": pred.get("value", {}),
        }
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
