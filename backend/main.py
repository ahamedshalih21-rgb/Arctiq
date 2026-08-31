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
from compressor_simulator import compressor_sim
from recovery_exchange import recovery_exchange

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coldsense")

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ColdSense API",
    description="Cold-storage spoilage prediction backend",
    version="2.0.0",
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

    logger.info("Starting compressor simulator...")
    compressor_sim.start()
    logger.info("Compressor simulator running.")

    logger.info("Starting recovery exchange service...")
    recovery_exchange.start()
    logger.info("Recovery exchange running.")


@app.on_event("shutdown")
async def shutdown_event():
    simulator.stop()
    compressor_sim.stop()
    recovery_exchange.stop()


# ── Models ─────────────────────────────────────────────────────────────────────
class FaultTriggerRequest(BaseModel):
    produce_type: Optional[str] = None   # None → trigger all
    speed: Optional[float] = 1.0


class FaultResetRequest(BaseModel):
    produce_type: Optional[str] = None


class ListingStatusRequest(BaseModel):
    new_status: str   # ACTIVE | INTERESTED | RESERVED | SOLD | EXPIRED


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


def _sync_compressor_context():
    """
    Update compressor simulator with current cold-storage context.
    Called after reading the latest simulator state so the compressor
    simulation reflects real-time conditions.
    """
    readings = simulator.get_readings()
    any_fault = any(r.get("fault_active", False) for r in readings.values())
    # Compute average storage temperature across all batches
    temps = [r.get("temperature", 5.0) for r in readings.values() if r]
    avg_temp = sum(temps) / len(temps) if temps else 5.0
    compressor_sim.update_context(any_fault=any_fault, avg_storage_temp=avg_temp)


def _sync_recovery_exchange():
    """
    Process current predictions through the recovery exchange.
    Creates or updates Risk Stock listings based on GBR output.
    Called on each prediction poll so listings stay current.
    """
    if not predictor._loaded:
        return
    meta_all = simulator.get_metadata()
    for pt in VALID_PRODUCE:
        pred = build_prediction_for(pt)
        if not pred:
            continue
        meta = meta_all.get(pt, {})
        recovery_exchange.process_prediction(
            batch_id=meta.get("batch_id", pt),
            produce_type=pt,
            display_name=meta.get("display_name", pt),
            risk_level=pred.get("risk_level", "Safe"),
            remaining_hours=pred.get("hours_remaining", 999.0),
            batch_weight_kg=meta.get("batch_weight_kg", 100.0),
        )


# ── Existing Endpoints (unchanged) ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded": predictor._loaded,
        "model_type": predictor.model_type,
        "simulator_running": simulator._running,
        "compressor_running": compressor_sim._running,
        "timestamp": time.time(),
    }


@app.get("/api/readings")
def get_readings():
    """Latest sensor readings for all produce batches."""
    _sync_compressor_context()
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
    _sync_recovery_exchange()
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


# ── New Endpoints: Compressor Health ───────────────────────────────────────────

@app.get("/api/compressor")
def get_compressor_health():
    """
    Current compressor health data derived from simulation-based
    Arrhenius temperature-dependent degradation model.

    All values are simulation-based. Parameters are prototype values only.
    Not manufacturer-calibrated.
    """
    _sync_compressor_context()
    return compressor_sim.get_status()


# ── New Endpoints: Risk Stock / Recovery Exchange ──────────────────────────────

@app.get("/api/recovery/listings")
def get_recovery_listings():
    """
    Active Risk Stock listings.
    Listings are auto-created when GBR predicts WATCH or CRITICAL risk levels.
    """
    _sync_recovery_exchange()
    listings = recovery_exchange.get_active_listings()
    return {
        "count": len(listings),
        "listings": listings,
    }


@app.get("/api/recovery/listings/all")
def get_all_recovery_listings():
    """All listings including SOLD and EXPIRED (for audit/history)."""
    return {
        "listings": recovery_exchange.get_all_listings(),
    }


@app.get("/api/recovery/buyers")
def get_nearby_buyers():
    """Simulated nearby buyers dataset."""
    return {
        "buyers": recovery_exchange.get_all_buyers(),
        "note": "Prototype simulation — buyers are simulated. No real external APIs used.",
    }


@app.get("/api/recovery/listings/{batch_id}/buyers")
def get_listing_buyers(batch_id: str):
    """Buyers and their current interest status for a specific listing."""
    buyers = recovery_exchange.get_buyers_for_listing(batch_id)
    return {
        "batch_id": batch_id,
        "buyers": buyers,
    }


@app.post("/api/recovery/listings/{batch_id}/interest")
def simulate_buyer_interest(batch_id: str, buyer_id: str = Query(...)):
    """Manually simulate buyer interest for a specific buyer/listing pair."""
    result = recovery_exchange.simulate_buyer_interest(batch_id, buyer_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Listing '{batch_id}' or buyer '{buyer_id}' not found."
        )
    return {"batch_id": batch_id, "buyer": result}


@app.post("/api/recovery/listings/{batch_id}/status")
def update_listing_status(batch_id: str, body: ListingStatusRequest):
    """Update the status of a Risk Stock listing (e.g. mark RESERVED or SOLD)."""
    success = recovery_exchange.update_listing_status(batch_id, body.new_status)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Listing '{batch_id}' not found or invalid status '{body.new_status}'."
        )
    return {"batch_id": batch_id, "new_status": body.new_status}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
