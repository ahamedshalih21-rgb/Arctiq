"""
Arctiq — Risk Stock / Recovery Exchange Service
===================================================
Manages at-risk produce listings and simulated nearby buyer interactions.

OVERVIEW:
  When a produce batch transitions to WATCH or CRITICAL risk level (as
  determined by the PyTorch LSTM spoilage prediction model), this service automatically
  creates a Risk Stock listing — representing produce that still has recoverable
  economic value but must be sold, moved, or used before total spoilage occurs.

  Nearby buyers are simulated. No real WhatsApp, SMS, or external messaging
  APIs are used. Buyer interest follows a controlled state machine.

PRODUCE PRICING (INR):
  Produce-specific pricing table. These are prototype simulation values
  used to calculate suggested recovery prices. They are illustrative only.

RECOVERY PRICE HEURISTIC (PROTOTYPE):
  suggested_price = base_value * recovery_fraction
  recovery_fraction = clip(remaining_hours / reference_window_hours, MIN, MAX)

  As remaining hours decrease, recovery price decreases proportionally.
  Floor: 10% of batch value. Ceiling: 80% of batch value.

LISTING DEDUPLICATION:
  If a batch is already listed, the existing listing is updated (risk level,
  remaining hours, price, status) rather than creating a new duplicate.

BUYER STATE MACHINE:
  PENDING → INTERESTED or NOT_INTERESTED → (if INTERESTED) RESERVED → SOLD
  States only transition on meaningful simulation events, not every tick.
  Interest decisions are made once per buyer per listing exposure window.

THREAD SAFETY:
  All shared listing and buyer state is protected by a threading.Lock.
"""

import threading
import random
import time
from datetime import datetime, timezone
from typing import Optional

# ── Risk trigger configuration ─────────────────────────────────────────────────
# Batches at these risk levels will generate/update Risk Stock listings.
RECOVERY_TRIGGER_LEVELS = ["Watch", "Critical"]

# ── Recovery price heuristic parameters ───────────────────────────────────────
RECOVERY_PRICE_FRACTION_MIN = 0.10   # Floor: 10% of batch value
RECOVERY_PRICE_FRACTION_MAX = 0.80   # Ceiling: 80% of batch value

# ── Produce pricing table (INR) — prototype simulation values ─────────────────
# value_per_kg_inr: base value per kilogram in Indian Rupees
# reference_recovery_window_hours: time horizon used in price fraction calc.
#   At this many hours remaining, the listing price is at the ceiling (80%).
#   Below this, it scales down proportionally toward the floor.
PRODUCE_PRICING = {
    "spinach": {
        "value_per_kg_inr": 65.0,             # Rs 65/kg
        "reference_recovery_window_hours": 48.0,
    },
    "tomato": {
        "value_per_kg_inr": 45.0,             # Rs 45/kg
        "reference_recovery_window_hours": 72.0,
    },
    "strawberry": {
        "value_per_kg_inr": 120.0,            # Rs 120/kg
        "reference_recovery_window_hours": 36.0,  # highly perishable
    },
    # Backward compatibility aliases
    "leafy_greens": {
        "value_per_kg_inr": 65.0,
        "reference_recovery_window_hours": 48.0,
    },
    "tomatoes": {
        "value_per_kg_inr": 45.0,
        "reference_recovery_window_hours": 72.0,
    },
    "milk": {
        "value_per_kg_inr": 55.0,
        "reference_recovery_window_hours": 30.0,
    },
}

# ── Listing state constants ────────────────────────────────────────────────────
STATUS_ACTIVE      = "ACTIVE"
STATUS_INTERESTED  = "INTERESTED"
STATUS_RESERVED    = "RESERVED"
STATUS_SOLD        = "SOLD"
STATUS_EXPIRED     = "EXPIRED"

# ── Buyer interest state machine ───────────────────────────────────────────────
BUYER_PENDING        = "PENDING"
BUYER_INTERESTED     = "INTERESTED"
BUYER_NOT_INTERESTED = "NOT_INTERESTED"
BUYER_RESERVED       = "RESERVED"
BUYER_SOLD           = "SOLD"

# Probability that a buyer transitions from PENDING to INTERESTED (vs NOT_INTERESTED)
# Applied once per buyer per listing, not on every tick.
BUYER_INTEREST_PROBABILITY = 0.65

# Seconds between buyer state evaluation cycles
BUYER_EVAL_INTERVAL = 30.0   # evaluate buyer interest every 30 seconds

# ── Simulated nearby buyer dataset ────────────────────────────────────────────
# This is a fixed dataset of prototype simulated buyers.
# In a real system, this would be a database of registered recovery buyers.
SIMULATED_BUYERS = [
    {
        "buyer_id":   "B001",
        "buyer_name": "Green Juice Corner",
        "buyer_type": "Juice Stall",
        "distance_km": 0.6,
        "preferred_produce": ["leafy_greens", "tomatoes"],
    },
    {
        "buyer_id":   "B002",
        "buyer_name": "City Canteen",
        "buyer_type": "Canteen",
        "distance_km": 1.2,
        "preferred_produce": ["leafy_greens", "tomatoes", "milk"],
    },
    {
        "buyer_id":   "B003",
        "buyer_name": "Daily Dairy Vendor",
        "buyer_type": "Dairy Distributor",
        "distance_km": 1.8,
        "preferred_produce": ["milk"],
    },
    {
        "buyer_id":   "B004",
        "buyer_name": "FreshBite Juice Bar",
        "buyer_type": "Juice Stall",
        "distance_km": 2.1,
        "preferred_produce": ["leafy_greens", "tomatoes", "milk"],
    },
    {
        "buyer_id":   "B005",
        "buyer_name": "Metro Food Processing",
        "buyer_type": "Food Processing Buyer",
        "distance_km": 3.4,
        "preferred_produce": ["tomatoes", "milk"],
    },
]


# ── Recovery price calculation ─────────────────────────────────────────────────

def _calculate_recovery_price(
    produce_type: str,
    batch_weight_kg: float,
    remaining_hours: float,
) -> float:
    """
    Prototype recovery price heuristic.
    Price scales with remaining safe time as a fraction of the reference window.
    Clamped to [FLOOR, CEILING] × base batch value.
    """
    pricing = PRODUCE_PRICING.get(produce_type, {
        "value_per_kg_inr": 30.0,
        "reference_recovery_window_hours": 48.0,
    })
    base_value = batch_weight_kg * pricing["value_per_kg_inr"]
    ref_window = pricing["reference_recovery_window_hours"]
    fraction = remaining_hours / ref_window
    fraction = max(RECOVERY_PRICE_FRACTION_MIN, min(RECOVERY_PRICE_FRACTION_MAX, fraction))
    return round(base_value * fraction, 2)


# ── Recovery Exchange Service ──────────────────────────────────────────────────

class RecoveryExchangeService:
    """
    Manages Risk Stock listings and simulated buyer interactions.

    Thread-safe. All public methods acquire the internal lock.
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Active listings keyed by batch_id
        # { batch_id: listing_dict }
        self._listings: dict = {}

        # Buyer interest state per listing
        # { batch_id: { buyer_id: buyer_status } }
        self._buyer_states: dict = {}

        # Tracks last buyer evaluation time per listing
        self._last_buyer_eval: dict = {}

        # Background thread for buyer state machine
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._buyer_state_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ── Listing management ─────────────────────────────────────────────────────

    def process_prediction(
        self,
        batch_id: str,
        produce_type: str,
        display_name: str,
        risk_level: str,
        remaining_hours: float,
        batch_weight_kg: float,
    ):
        """
        Called after each PyTorch LSTM spoilage prediction.
        Creates or updates a Risk Stock listing if the batch is at trigger level.
        Safe (non-trigger) batches expire existing listings if they were downgraded.
        """
        with self._lock:
            if risk_level in RECOVERY_TRIGGER_LEVELS:
                self._upsert_listing(
                    batch_id, produce_type, display_name,
                    risk_level, remaining_hours, batch_weight_kg,
                )
            else:
                # If batch recovered to Safe, mark any existing active listing expired
                if batch_id in self._listings:
                    existing = self._listings[batch_id]
                    if existing["listing_status"] not in (STATUS_SOLD, STATUS_EXPIRED):
                        existing["listing_status"] = STATUS_EXPIRED
                        existing["updated_at"] = _now_iso()

    def _upsert_listing(
        self,
        batch_id: str,
        produce_type: str,
        display_name: str,
        risk_level: str,
        remaining_hours: float,
        batch_weight_kg: float,
    ):
        """Create or update a Risk Stock listing. Must be called with lock held."""
        price = _calculate_recovery_price(produce_type, batch_weight_kg, remaining_hours)
        now   = _now_iso()

        if batch_id in self._listings:
            # Update existing listing (do NOT create duplicate)
            listing = self._listings[batch_id]
            listing["risk_level"]      = risk_level
            listing["remaining_hours"] = round(remaining_hours, 1)
            listing["suggested_recovery_price"] = price
            listing["updated_at"]      = now
            # If previously expired, reactivate
            if listing["listing_status"] == STATUS_EXPIRED:
                listing["listing_status"] = STATUS_ACTIVE
            # Escalate: if listing was ACTIVE and risk went to CRITICAL, keep visible
        else:
            # Create new listing
            listing = {
                "batch_id":                  batch_id,
                "produce_type":              produce_type,
                "display_name":              display_name,
                "risk_level":                risk_level,
                "remaining_hours":           round(remaining_hours, 1),
                "batch_weight_kg":           batch_weight_kg,
                "suggested_recovery_price":  price,
                "listing_status":            STATUS_ACTIVE,
                "created_at":                now,
                "updated_at":                now,
                "pricing_note": (
                    "Prototype recovery price heuristic — "
                    "not a validated market pricing algorithm."
                ),
            }
            self._listings[batch_id] = listing
            # Initialise buyer states for this listing
            self._buyer_states[batch_id] = {
                b["buyer_id"]: BUYER_PENDING for b in SIMULATED_BUYERS
            }
            self._last_buyer_eval[batch_id] = 0.0

    def get_active_listings(self) -> list:
        """Return listings that are not SOLD or EXPIRED."""
        with self._lock:
            result = []
            for listing in self._listings.values():
                if listing["listing_status"] not in (STATUS_SOLD, STATUS_EXPIRED):
                    result.append(dict(listing))
            return sorted(result, key=lambda x: x["remaining_hours"])

    def get_all_listings(self) -> list:
        """Return all listings including SOLD and EXPIRED (for audit)."""
        with self._lock:
            return [dict(v) for v in self._listings.values()]

    def get_buyers_for_listing(self, batch_id: str) -> list:
        """Return simulated buyers with their current interest status for a listing."""
        with self._lock:
            states = self._buyer_states.get(batch_id, {})
            result = []
            for buyer in SIMULATED_BUYERS:
                bid = buyer["buyer_id"]
                result.append({
                    **buyer,
                    "interest_status": states.get(bid, BUYER_PENDING),
                })
            return result

    def get_all_buyers(self) -> list:
        """Return all simulated buyers (without listing-specific interest state)."""
        return [dict(b) for b in SIMULATED_BUYERS]

    def update_listing_status(self, batch_id: str, new_status: str) -> bool:
        """Manually update a listing status (e.g. mark SOLD or RESERVED)."""
        valid_statuses = {STATUS_ACTIVE, STATUS_INTERESTED, STATUS_RESERVED,
                          STATUS_SOLD, STATUS_EXPIRED}
        if new_status not in valid_statuses:
            return False
        with self._lock:
            if batch_id not in self._listings:
                return False
            self._listings[batch_id]["listing_status"] = new_status
            self._listings[batch_id]["updated_at"] = _now_iso()
            return True

    def simulate_buyer_interest(self, batch_id: str, buyer_id: str) -> Optional[dict]:
        """
        Manually trigger a buyer interest event for a specific buyer/listing pair.
        Returns updated buyer record or None if not found.
        """
        with self._lock:
            if batch_id not in self._buyer_states:
                return None
            if buyer_id not in {b["buyer_id"] for b in SIMULATED_BUYERS}:
                return None
            # Advance state machine one step
            current = self._buyer_states[batch_id].get(buyer_id, BUYER_PENDING)
            new_state = _advance_buyer_state(current, produce_type=None, preferred=True)
            self._buyer_states[batch_id][buyer_id] = new_state
            # Update listing status to reflect interest
            if new_state == BUYER_INTERESTED:
                if self._listings.get(batch_id, {}).get("listing_status") == STATUS_ACTIVE:
                    self._listings[batch_id]["listing_status"] = STATUS_INTERESTED
                    self._listings[batch_id]["updated_at"] = _now_iso()
            buyer_info = next((b for b in SIMULATED_BUYERS if b["buyer_id"] == buyer_id), {})
            return {**buyer_info, "interest_status": new_state}

    # ── Background buyer state machine ─────────────────────────────────────────

    def _buyer_state_loop(self):
        """Periodically advance buyer interest states for active listings."""
        while self._running:
            time.sleep(BUYER_EVAL_INTERVAL)
            with self._lock:
                self._evaluate_buyer_states()

    def _evaluate_buyer_states(self):
        """
        Advance buyer states for active listings.
        Called with lock held.

        Each buyer's state transitions once per evaluation window.
        PENDING buyers are resolved (INTERESTED or NOT_INTERESTED) based on
        produce preference and a configurable probability.
        """
        now_ts = time.time()
        for batch_id, listing in self._listings.items():
            if listing["listing_status"] in (STATUS_SOLD, STATUS_EXPIRED):
                continue

            last_eval = self._last_buyer_eval.get(batch_id, 0.0)
            if now_ts - last_eval < BUYER_EVAL_INTERVAL:
                continue
            self._last_buyer_eval[batch_id] = now_ts

            produce_type = listing["produce_type"]
            buyer_states = self._buyer_states.get(batch_id, {})

            any_interested = False
            for buyer in SIMULATED_BUYERS:
                bid = buyer["buyer_id"]
                current_state = buyer_states.get(bid, BUYER_PENDING)
                if current_state == BUYER_PENDING:
                    # Decide interest based on produce preference + probability
                    prefers = produce_type in buyer.get("preferred_produce", [])
                    p_interest = BUYER_INTEREST_PROBABILITY if prefers else (
                        BUYER_INTEREST_PROBABILITY * 0.4
                    )
                    if random.random() < p_interest:
                        buyer_states[bid] = BUYER_INTERESTED
                    else:
                        buyer_states[bid] = BUYER_NOT_INTERESTED
                # INTERESTED and NOT_INTERESTED states are stable
                # until a manual action (reserve/sell) occurs.
                if buyer_states.get(bid) == BUYER_INTERESTED:
                    any_interested = True

            self._buyer_states[batch_id] = buyer_states

            # Update listing status to reflect interest if at least one buyer responded
            if any_interested and listing["listing_status"] == STATUS_ACTIVE:
                listing["listing_status"] = STATUS_INTERESTED
                listing["updated_at"] = _now_iso()


def _advance_buyer_state(current: str, produce_type: Optional[str], preferred: bool) -> str:
    """
    State machine for a single buyer's interest status.
    PENDING → INTERESTED or NOT_INTERESTED (based on preference + probability)
    INTERESTED → (stays, until manually reserved/sold)
    """
    if current == BUYER_PENDING:
        p = BUYER_INTEREST_PROBABILITY if preferred else BUYER_INTEREST_PROBABILITY * 0.4
        return BUYER_INTERESTED if random.random() < p else BUYER_NOT_INTERESTED
    return current  # All other states stable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Singleton instance
recovery_exchange = RecoveryExchangeService()
