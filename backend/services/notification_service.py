"""
Arctiq — Telegram Notification Service
===========================================
Dedicated Telegram alert notification service for cold storage monitoring.
Supports:
  - Structured Telegram Bot API integration (HTTPS POST)
  - Severity-based state machine and deduplication
  - Automatic escalation alerts (SAFE -> EARLY_WARNING -> HIGH_RISK -> CRITICAL -> SPOILED)
  - Recovery tracking (allows re-alerting when conditions deteriorate after recovering)
  - Reusable test endpoint and structured responses
"""

import os
import time
import logging
from typing import Optional, Dict, Any
import httpx
from dotenv import load_dotenv

# Load local environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = logging.getLogger("arctiq.notifications")

# ── Warning Severity Hierarchy ────────────────────────────────────────────────
WARNING_SEVERITY: Dict[str, int] = {
    "SAFE": 0,
    "MONITOR": 1,
    "WATCH": 2,
    "EARLY_WARNING": 3,
    "HIGH_RISK": 4,
    "CRITICAL": 5,
    "SPOILED": 6,
}

# Alerting thresholds (stages that qualify for alert dispatch)
ALERTABLE_STAGES = {"EARLY_WARNING", "HIGH_RISK", "CRITICAL", "SPOILED"}


def build_alert_message(recommendation: dict, warning_stage: str) -> str:
    """
    Build HTML-formatted Telegram notification messages using
    SmartSell recommendation and early-warning data.
    """
    product = recommendation.get("display_name", "Unknown Product")
    batch_id = recommendation.get("batch_id", "Unknown Batch")
    model_hours = recommendation.get("model_hours_remaining", 0.0)
    proj_hours = recommendation.get("projected_risk_horizon_hours", 0.0)
    priority_score = recommendation.get("sell_priority_score", 0.0)
    rec_price = recommendation.get("recommended_price_per_kg", 0.0)
    mkt_price = recommendation.get("market_price_per_kg", 0.0)
    quantity = recommendation.get("quantity_kg", 0.0)
    expected_waste = recommendation.get("expected_waste_inr", 0.0)

    # Decision factors / reason
    factors = recommendation.get("reason_factors", [])
    reason_str = factors[0] if factors else "High spoilage risk and inventory exposure"

    if warning_stage == "EARLY_WARNING":
        return (
            "⚠️ <b>ARCTIQ EARLY WARNING</b>\n\n"
            f"<b>Product:</b> {product}\n"
            f"<b>Batch:</b> {batch_id}\n\n"
            "<b>Projected Risk Horizon:</b>\n"
            f"Approximately {proj_hours:.0f} hours (trend-based projection)\n\n"
            "<b>Action:</b>\n"
            "Prepare this batch for priority sale.\n\n"
            "<b>SmartSell Priority:</b>\n"
            f"{priority_score:.0f}/100"
        )

    elif warning_stage == "HIGH_RISK":
        return (
            "⚠️ <b>ARCTIQ HIGH RISK ALERT</b>\n\n"
            f"<b>Product:</b> {product}\n"
            f"<b>Batch:</b> {batch_id}\n\n"
            "<b>Model Hours Remaining:</b>\n"
            f"{model_hours:.1f} hours\n\n"
            "<b>Recommended Action:</b>\n"
            "SELL SOON\n\n"
            "<b>Recommended Price:</b>\n"
            f"₹{rec_price:.2f}/kg\n\n"
            "<b>Priority Score:</b>\n"
            f"{priority_score:.0f}/100"
        )

    elif warning_stage == "CRITICAL":
        return (
            "🚨 <b>ARCTIQ CRITICAL ALERT</b>\n\n"
            "<b>ACTION: SELL NOW</b>\n\n"
            f"<b>Product:</b> {product}\n"
            f"<b>Batch:</b> {batch_id}\n\n"
            "<b>Model Hours Remaining:</b>\n"
            f"{model_hours:.1f} hours\n\n"
            "<b>Quantity:</b>\n"
            f"{quantity:.1f} kg\n\n"
            "<b>Market Price:</b>\n"
            f"₹{mkt_price:.2f}/kg\n\n"
            "<b>Recommended Price:</b>\n"
            f"₹{rec_price:.2f}/kg\n\n"
            "<b>Expected Waste Risk:</b>\n"
            f"₹{expected_waste:,.2f}\n\n"
            "<b>SmartSell Priority:</b>\n"
            f"{priority_score:.0f}/100\n\n"
            "<b>Reason:</b>\n"
            f"{reason_str}"
        )

    elif warning_stage == "SPOILED":
        val_affected = quantity * mkt_price
        return (
            "☠️ <b>ARCTIQ SPOILAGE ALERT</b>\n\n"
            f"<b>Product:</b> {product}\n"
            f"<b>Batch:</b> {batch_id}\n\n"
            "<b>Status:</b> SPOILED\n\n"
            "<b>Action Required:</b>\n"
            "Remove this batch from active inventory.\n\n"
            "<b>Estimated Value Affected:</b>\n"
            f"₹{val_affected:,.2f}"
        )

    else:
        return (
            "ℹ️ <b>ARCTIQ STATUS UPDATE</b>\n\n"
            f"<b>Product:</b> {product}\n"
            f"<b>Batch:</b> {batch_id}\n"
            f"<b>Stage:</b> {warning_stage}\n"
            f"<b>Model Hours Remaining:</b> {model_hours:.1f}h"
        )


class TelegramNotificationService:
    def __init__(self):
        self._reload_config()
        # In-memory alert state manager for deduplication
        # batch_id -> { "last_stage": str, "last_sent_stage": Optional[str], "last_sent_at": Optional[float] }
        self.alert_state: Dict[str, Dict[str, Any]] = {}

    def _reload_config(self):
        """Reload configuration from environment variables."""
        self.enabled = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
        self.bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        self.chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

    def is_configured(self) -> bool:
        """Check whether valid Telegram credentials are present."""
        self._reload_config()
        return bool(self.enabled and self.bot_token and self.chat_id)

    def get_status(self) -> dict:
        """Return structured configuration and readiness status."""
        self._reload_config()
        if not self.enabled:
            return {
                "provider": "telegram",
                "enabled": False,
                "configured": bool(self.bot_token and self.chat_id),
                "status": "DISABLED",
            }
        if not (self.bot_token and self.chat_id):
            return {
                "provider": "telegram",
                "enabled": True,
                "configured": False,
                "status": "NOT_CONFIGURED",
            }
        return {
            "provider": "telegram",
            "enabled": True,
            "configured": True,
            "status": "READY",
        }

    async def send_message(self, message: str) -> dict:
        """
        Send an HTML-formatted message via the official Telegram Bot API.
        Never throws unhandled exceptions; returns structured status.
        """
        self._reload_config()

        if not self.enabled:
            return {
                "success": False,
                "status": "DISABLED",
                "provider": "telegram",
                "error": "Telegram notifications are disabled",
            }

        if not self.bot_token or not self.chat_id:
            return {
                "success": False,
                "status": "NOT_CONFIGURED",
                "provider": "telegram",
                "error": "Telegram credentials are missing (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)",
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                resp_json = response.json()

                if response.status_code == 200 and resp_json.get("ok"):
                    msg_id = resp_json.get("result", {}).get("message_id")
                    logger.info(f"Telegram notification sent successfully (message_id={msg_id})")
                    return {
                        "success": True,
                        "status": "SENT",
                        "provider": "telegram",
                        "message_id": msg_id,
                    }
                else:
                    err_desc = resp_json.get("description", f"HTTP {response.status_code}")
                    logger.error(f"Telegram API error: {err_desc}")
                    return {
                        "success": False,
                        "status": "FAILED",
                        "provider": "telegram",
                        "error": f"Telegram API error: {err_desc}",
                    }
        except httpx.TimeoutException:
            logger.error("Telegram API request timed out (10s)")
            return {
                "success": False,
                "status": "FAILED",
                "provider": "telegram",
                "error": "Telegram API request timed out",
            }
        except Exception as e:
            logger.error(f"Telegram notification network error: {e}")
            return {
                "success": False,
                "status": "FAILED",
                "provider": "telegram",
                "error": str(e),
            }

    async def send_test_message(self) -> dict:
        """Send a standard verification message to test Telegram setup."""
        test_text = (
            "🚀 <b>ARCTIQ TEST ALERT</b>\n\n"
            "Telegram automatic notification system is working correctly.\n"
            f"<b>Timestamp:</b> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n"
            "<b>System:</b> Arctiq Smart Inventory Decision Engine"
        )
        return await self.send_message(test_text)

    async def evaluate_and_notify(
        self,
        batch_id: str,
        current_stage: str,
        recommendation: dict,
        force_alert: bool = False,
    ) -> dict:
        """
        State machine evaluation and deduplicated alert dispatch.

        Transitions that trigger notifications:
          - Escalation into an alertable stage (EARLY_WARNING, HIGH_RISK, CRITICAL, SPOILED)
          - Escalation to a higher severity level than previously alerted (e.g. EARLY_WARNING -> CRITICAL)
          - Manual fault injection with force_alert=True (if in an alertable stage)

        Deduplication rules:
          - If the current stage is the same as the last sent stage, duplicate alert is suppressed.
          - If conditions recover (drop to SAFE/MONITOR/WATCH), the state is reset so future
            escalations will trigger fresh notifications.
        """
        # Ensure state entry exists
        if batch_id not in self.alert_state:
            self.alert_state[batch_id] = {
                "last_stage": "SAFE",
                "last_sent_stage": None,
                "last_sent_at": None,
            }

        state = self.alert_state[batch_id]
        prev_stage = state["last_stage"]
        last_sent = state["last_sent_stage"]

        curr_severity = WARNING_SEVERITY.get(current_stage, 0)
        prev_severity = WARNING_SEVERITY.get(prev_stage, 0)
        last_sent_severity = WARNING_SEVERITY.get(last_sent, -1) if last_sent else -1

        # Update last known stage
        state["last_stage"] = current_stage

        # Recovery check: if dropped below alertable threshold, reset last_sent_stage
        if current_stage not in ALERTABLE_STAGES:
            if last_sent is not None:
                logger.info(f"Batch {batch_id} recovered from {last_sent} to {current_stage}. Resetting alert latch.")
                state["last_sent_stage"] = None
            return {
                "attempted": False,
                "sent": False,
                "reason": f"Non-alertable stage ({current_stage})",
                "warning_stage": current_stage,
                "batch_id": batch_id,
            }

        # Check if an alert is required
        should_alert = False
        alert_reason = ""

        if force_alert:
            # Explicit trigger (e.g. Trigger Fault button)
            should_alert = True
            alert_reason = "Manual fault injection"
        elif last_sent is None and current_stage in ALERTABLE_STAGES:
            # First time entering an alertable stage
            should_alert = True
            alert_reason = f"Escalated from {prev_stage} to {current_stage}"
        elif curr_severity > last_sent_severity:
            # Escalation to higher severity (e.g. EARLY_WARNING -> HIGH_RISK -> CRITICAL)
            should_alert = True
            alert_reason = f"Severity escalated from {last_sent} to {current_stage}"
        else:
            # Same or lower severity already notified
            should_alert = False
            alert_reason = f"Duplicate alert suppressed (already notified for {last_sent})"

        if not should_alert:
            return {
                "attempted": False,
                "sent": False,
                "reason": alert_reason,
                "warning_stage": current_stage,
                "batch_id": batch_id,
            }

        # Format and send Telegram alert
        message = build_alert_message(recommendation, current_stage)
        result = await self.send_message(message)

        if result.get("success"):
            state["last_sent_stage"] = current_stage
            state["last_sent_at"] = time.time()
            return {
                "attempted": True,
                "sent": True,
                "provider": "telegram",
                "message_id": result.get("message_id"),
                "warning_stage": current_stage,
                "batch_id": batch_id,
                "reason": alert_reason,
            }
        else:
            return {
                "attempted": True,
                "sent": False,
                "provider": "telegram",
                "error": result.get("error"),
                "status": result.get("status"),
                "warning_stage": current_stage,
                "batch_id": batch_id,
                "reason": alert_reason,
            }


# Singleton instance
notification_service = TelegramNotificationService()
