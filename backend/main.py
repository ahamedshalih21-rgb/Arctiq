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
from services.smartsell_service import generate_smartsell_recommendation
from services.notification_service import notification_service
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("coldsense")

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ColdSense API",
    description="Cold-storage spoilage prediction and smart inventory management backend",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def monitoring_loop():
    """Background task to monitor predictions and send Telegram alerts."""
    while True:
        try:
            if predictor._loaded and notification_service.enabled:
                meta_all = simulator.get_metadata()
                for pt in VALID_PRODUCE:
                    pred = build_prediction_for(pt)
                    if not pred:
                        continue
                    meta = meta_all.get(pt, {})
                    
                    # Generate recommendation for message formatting
                    rec = generate_smartsell_recommendation(
                        produce_type=pt,
                        display_name=meta.get("display_name", pt),
                        batch_id=meta.get("batch_id", pt),
                        model_hours=pred.get("model_hours_remaining", pred.get("hours_remaining", 99.0)),
                        warning_stage=pred.get("warning_stage", "SAFE"),
                        projected_horizon=pred.get("projected_risk_horizon_hours", 99.0),
                        quantity_kg=meta.get("quantity_kg", meta.get("batch_weight_kg", 100.0)),
                        purchase_cost_per_kg=meta.get("purchase_cost_per_kg", 30.0),
                        market_price_per_kg=meta.get("market_price_per_kg", 60.0),
                        demand_score=meta.get("demand_score", 60.0),
                    )
                    
                    await notification_service.evaluate_and_notify(
                        batch_id=meta.get("batch_id", pt),
                        current_stage=pred.get("warning_stage", "SAFE"),
                        recommendation=rec,
                        force_alert=False
                    )
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
        
        await asyncio.sleep(10)  # Check every 10 seconds


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

    logger.info("Starting monitoring loop...")
    asyncio.create_task(monitoring_loop())


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
VALID_PRODUCE = ["spinach", "tomato", "strawberry"]

PRODUCE_KEY_MAP = {
    "spinach": "spinach",
    "tomato": "tomato",
    "strawberry": "strawberry",
    "leafy_greens": "spinach",
    "tomatoes": "tomato",
    "milk": "strawberry",
}


def canonical_produce(produce_type: str) -> str:
    return PRODUCE_KEY_MAP.get(produce_type, produce_type)


def validate_produce(produce_type: str) -> str:
    key = canonical_produce(produce_type)
    if key not in VALID_PRODUCE:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid produce_type '{produce_type}'. Must be one of: {VALID_PRODUCE}"
        )
    return key


def build_prediction_for(produce_type: str) -> dict:
    """
    Run PyTorch LSTM prediction for a single produce type using its 360-step window.
    Passes full history and produce_config to predictor for trend assessment.
    """
    pt = canonical_produce(produce_type)
    window = simulator.get_window_360(pt)
    if len(window) == 0:
        return {}

    cfg = PRODUCE_CONFIGS.get(pt, {})
    history = simulator.get_history(pt, n=60)

    prediction = predictor.predict(
        window=window,
        history=history,
        produce_config={
            "produce_type":         pt,
            "ideal_temp":           cfg.get("ideal_temp", 2.0),
            "ideal_humidity":       cfg.get("ideal_humidity", 90.0),
            "perishability_factor": cfg.get("perishability_factor", 1.0),
        },
    )

    meta = simulator.get_batch_metadata(pt)
    value = predictor.predict_value(
        prediction,
        meta.get("batch_weight_kg", 100),
        meta.get("value_per_kg", 1.0),
    )

    return {
        "produce_type": pt,
        "batch_id":     meta.get("batch_id"),
        **prediction,
        "value":        value,
    }


def _sync_compressor_context():
    """Update compressor with current cold-storage context."""
    readings = simulator.get_readings()
    any_fault = any(r.get("fault_active", False) for r in readings.values())
    temps     = [r.get("temperature", 5.0) for r in readings.values() if r]
    avg_temp  = sum(temps) / len(temps) if temps else 5.0
    compressor_sim.update_context(any_fault=any_fault, avg_storage_temp=avg_temp)


def _sync_recovery_exchange():
    """Process current predictions through the recovery exchange."""
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


# ── Existing Endpoints (preserved) ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_loaded":      predictor._loaded,
        "model_type":        predictor.model_type,
        "simulator_running": simulator._running,
        "compressor_running": compressor_sim._running,
        "active_produce":    VALID_PRODUCE,
        "timestamp":         time.time(),
    }


@app.get("/api/readings")
def get_readings():
    """Latest sensor readings for all produce batches."""
    _sync_compressor_context()
    readings = simulator.get_readings()
    meta     = simulator.get_metadata()
    result   = {}
    for pt, reading in readings.items():
        result[pt] = {
            **reading,
            "batch_id":      meta[pt]["batch_id"],
            "display_name":  meta[pt]["display_name"],
            "fault_active":  meta[pt]["fault_active"],
            "fault_speed":   meta[pt]["fault_speed"],
            "storage_since": meta[pt]["storage_since"],
            "quantity_kg":   meta[pt]["quantity_kg"],
            "demand_score":  meta[pt]["demand_score"],
        }
    # Backward compatibility aliases
    if "spinach" in result:
        result["leafy_greens"] = result["spinach"]
    if "tomato" in result:
        result["tomatoes"] = result["tomato"]
    if "strawberry" in result:
        result["milk"] = result["strawberry"]
    return result


@app.get("/api/readings/{produce_type}")
def get_reading_for(produce_type: str):
    """Latest reading for a specific produce type."""
    pt = validate_produce(produce_type)
    readings = simulator.get_readings()
    meta     = simulator.get_batch_metadata(pt)
    return {**readings.get(pt, {}), **meta}


@app.get("/api/history/{produce_type}")
def get_history(produce_type: str, n: int = Query(30, ge=1, le=100)):
    """Last N readings for trend chart (default 30)."""
    pt = validate_produce(produce_type)
    history = simulator.get_history(pt, n)
    return {"produce_type": pt, "count": len(history), "readings": history}


@app.get("/api/prediction")
def get_all_predictions():
    """Model prediction for all batches (includes two-stage warning fields)."""
    if not predictor._loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet. Check server logs.")
    result = {}
    for pt in VALID_PRODUCE:
        result[pt] = build_prediction_for(pt)
    # Backward compatibility aliases
    if "spinach" in result:
        result["leafy_greens"] = result["spinach"]
    if "tomato" in result:
        result["tomatoes"] = result["tomato"]
    if "strawberry" in result:
        result["milk"] = result["strawberry"]
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
    result         = {}
    total_preserved = 0.0
    total_at_risk   = 0.0
    for pt in VALID_PRODUCE:
        p           = build_prediction_for(pt)
        result[pt]  = p.get("value", {})
        total_preserved += p.get("value", {}).get("value_preserved_usd", 0)
        total_at_risk   += p.get("value", {}).get("value_at_risk_usd", 0)
    result["_totals"] = {
        "total_preserved_usd": round(total_preserved, 2),
        "total_at_risk_usd":   round(total_at_risk, 2),
    }
    return result


@app.post("/api/trigger-fault")
async def trigger_fault(body: FaultTriggerRequest):
    """
    Trigger a cooling fault for demo purposes.
    produce_type: specific batch, or null/omitted for all batches.
    speed: multiplier (1.0 = real-time drift, 5.0 = 5x faster, max 20).
    """
    speed = max(0.5, min(20.0, body.speed or 1.0))

    if body.produce_type:
        validate_produce(body.produce_type)
        success = simulator.trigger_fault(body.produce_type, speed)
        if not success:
            raise HTTPException(status_code=404, detail="Produce type not found in simulator.")
            
        # Explicitly force a Telegram alert for the triggered fault
        pred = build_prediction_for(body.produce_type)
        if pred:
            meta_all = simulator.get_metadata()
            meta = meta_all.get(body.produce_type, {})
            rec = generate_smartsell_recommendation(
                produce_type=body.produce_type,
                display_name=meta.get("display_name", body.produce_type),
                batch_id=meta.get("batch_id", body.produce_type),
                model_hours=pred.get("model_hours_remaining", pred.get("hours_remaining", 99.0)),
                warning_stage=pred.get("warning_stage", "HIGH_RISK"), # Force a higher stage text
                projected_horizon=pred.get("projected_risk_horizon_hours", 99.0),
                quantity_kg=meta.get("quantity_kg", meta.get("batch_weight_kg", 100.0)),
                purchase_cost_per_kg=meta.get("purchase_cost_per_kg", 30.0),
                market_price_per_kg=meta.get("market_price_per_kg", 60.0),
                demand_score=meta.get("demand_score", 60.0),
            )
            asyncio.create_task(notification_service.evaluate_and_notify(
                batch_id=meta.get("batch_id", body.produce_type),
                current_stage="HIGH_RISK", # Fake the stage just for the forced alert so it bypasses SAFE filter
                recommendation=rec,
                force_alert=True
            ))

        return {
            "status":       "fault_triggered",
            "produce_type": body.produce_type,
            "speed":        speed,
            "message":      f"Fault injected for {body.produce_type} at {speed}x speed",
        }
    else:
        simulator.trigger_all_faults(speed)
        # We could also loop and notify here, but background loop will catch it.
        return {
            "status":       "fault_triggered",
            "produce_type": "all",
            "speed":        speed,
            "message":      f"Fault injected for all batches at {speed}x speed",
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

    result   = {}
    readings = simulator.get_readings()
    meta     = simulator.get_metadata()

    for pt in VALID_PRODUCE:
        pred = build_prediction_for(pt)
        result[pt] = {
            "reading":  readings.get(pt, {}),
            "metadata": meta.get(pt, {}),
            "prediction": {
                "hours_remaining":              pred.get("hours_remaining"),
                "risk_level":                   pred.get("risk_level"),
                "confidence":                   pred.get("confidence"),
                "warning_stage":                pred.get("warning_stage"),
                "projected_risk_horizon_hours": pred.get("projected_risk_horizon_hours"),
                "early_warning_active":         pred.get("early_warning_active"),
                "critical_action_active":       pred.get("critical_action_active"),
                "warning_description":          pred.get("warning_description"),
            },
            "value": pred.get("value", {}),
        }
    return result


# ── Compressor Health ───────────────────────────────────────────────────────────

@app.get("/api/compressor")
def get_compressor_health():
    """
    Current compressor health data derived from simulation-based
    Arrhenius temperature-dependent degradation model.
    All values are simulation-based. Not manufacturer-calibrated.
    """
    _sync_compressor_context()
    return compressor_sim.get_status()


# ── Risk Stock / Recovery Exchange ────────────────────────────────────────────

@app.get("/api/recovery/listings")
def get_recovery_listings():
    """
    Active Risk Stock listings.
    Listings are auto-created when model predicts WATCH or CRITICAL risk levels.
    """
    _sync_recovery_exchange()
    listings = recovery_exchange.get_active_listings()
    return {"count": len(listings), "listings": listings}


@app.get("/api/recovery/listings/all")
def get_all_recovery_listings():
    """All listings including SOLD and EXPIRED (for audit/history)."""
    return {"listings": recovery_exchange.get_all_listings()}


@app.get("/api/recovery/buyers")
def get_nearby_buyers():
    """Simulated nearby buyers dataset."""
    return {
        "buyers": recovery_exchange.get_all_buyers(),
        "note":   "Prototype simulation — buyers are simulated. No real external APIs used.",
    }


@app.get("/api/recovery/listings/{batch_id}/buyers")
def get_listing_buyers(batch_id: str):
    """Buyers and their current interest status for a specific listing."""
    buyers = recovery_exchange.get_buyers_for_listing(batch_id)
    return {"batch_id": batch_id, "buyers": buyers}


@app.post("/api/recovery/listings/{batch_id}/interest")
def simulate_buyer_interest(batch_id: str, buyer_id: str = Query(...)):
    """Manually simulate buyer interest for a specific buyer/listing pair."""
    result = recovery_exchange.simulate_buyer_interest(batch_id, buyer_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Listing '{batch_id}' or buyer '{buyer_id}' not found.",
        )
    return {"batch_id": batch_id, "buyer": result}


@app.post("/api/recovery/listings/{batch_id}/status")
def update_listing_status(batch_id: str, body: ListingStatusRequest):
    """Update the status of a Risk Stock listing (e.g. mark RESERVED or SOLD)."""
    success = recovery_exchange.update_listing_status(batch_id, body.new_status)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Listing '{batch_id}' not found or invalid status '{body.new_status}'.",
        )
    return {"batch_id": batch_id, "new_status": body.new_status}


# ── Notifications ─────────────────────────────────────────────────────────────

@app.post("/api/notifications/test-telegram")
async def test_telegram_notification():
    """Send a test message via Telegram to verify configuration."""
    status = notification_service.get_status()
    if not status.get("configured"):
        raise HTTPException(
            status_code=400,
            detail="Telegram is not configured. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env",
        )

    result = await notification_service.send_test_message()
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test message: {result.get('error')}",
        )
    return result


# ── SmartSell Recommendations ─────────────────────────────────────────────────

@app.get("/api/smartsell/recommendations")
def get_smartsell_recommendations():
    """
    SmartSell ranked recommendations for all batches.

    Returns all batches sorted by sell_priority_score (highest first).
    Each recommendation includes:
      - warning_stage and model_hours_remaining (from PyTorch LSTM)
      - projected_risk_horizon_hours (trend-based early warning)
      - Sell priority score (0–100) and priority_action
      - Dynamic recommended selling price, discount, margin
      - Explainable reason_factors

    Demand scores and quantities are stateful (from simulator batch state)
    and evolve gradually — they do not regenerate on each request.

    Note on horizon distinction:
      model_hours_remaining = PyTorch LSTM model-driven operational reference
      projected_risk_horizon_hours = trend-based early warning estimate
    """
    if not predictor._loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet.")

    recommendations = []
    meta_all        = simulator.get_metadata()

    for pt in VALID_PRODUCE:
        pred = build_prediction_for(pt)
        if not pred:
            continue
        meta = meta_all.get(pt, {})

        rec = generate_smartsell_recommendation(
            produce_type=pt,
            display_name=meta.get("display_name", pt),
            batch_id=meta.get("batch_id", pt),
            model_hours=pred.get("model_hours_remaining", pred.get("hours_remaining", 99.0)),
            warning_stage=pred.get("warning_stage", "SAFE"),
            projected_horizon=pred.get("projected_risk_horizon_hours", 99.0),
            quantity_kg=meta.get("quantity_kg", meta.get("batch_weight_kg", 100.0)),
            purchase_cost_per_kg=meta.get("purchase_cost_per_kg", 30.0),
            market_price_per_kg=meta.get("market_price_per_kg", 60.0),
            demand_score=meta.get("demand_score", 60.0),
        )
        recommendations.append(rec)

    # Sort by sell_priority_score descending (highest urgency first)
    recommendations.sort(key=lambda r: r["sell_priority_score"], reverse=True)

    # Add rank
    for i, rec in enumerate(recommendations):
        rec["rank"] = i + 1

    return {
        "recommendations": recommendations,
        "count":           len(recommendations),
        "generated_at":    time.time(),
        "note": (
            "model_hours_remaining = PyTorch LSTM model-driven operational reference. "
            "projected_risk_horizon_hours = trend-based early warning estimate "
            "(not the LSTM model's validated prediction output)."
        ),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
