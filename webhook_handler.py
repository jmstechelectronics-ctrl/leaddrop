#!/usr/bin/env python3
"""
LeadDrop Stripe Webhook Handler
===============================
Listens for Stripe checkout.session.completed events.
On new subscription: extracts customer details, sends welcome email,
notifies admin via email, saves to subscriber database.

Run as a Netlify Function or standalone Flask server.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

LEADDROP_DIR = Path(__file__).parent
EMAIL_ENGINE = LEADDROP_DIR / "email_engine.py"
SUBSCRIBERS_FILE = Path(os.path.expanduser("~/kramer-data/state/leaddrop-subscribers.json"))
ADMIN_EMAIL = "josh@jmstechsupport.com.au"

# ── Stripe event handler ─────────────────────────────────────
def handle_checkout_completed(event: dict) -> dict:
    """Process a checkout.session.completed event."""
    session = event.get("data", {}).get("object", {})
    metadata = session.get("metadata", {}) or {}
    customer_details = session.get("customer_details", {}) or {}
    amount_total = (session.get("amount_total", 0) or 0) / 100
    customer_email = customer_details.get("email", "")
    customer_name = customer_details.get("name", "")

    # Extract signup form data from metadata
    business_name = metadata.get("business_name", "")
    phone = metadata.get("phone", "")
    categories = metadata.get("categories", "")
    category_count = len(categories.split(",")) if categories else 0

    print(f"New subscriber: {customer_name} ({customer_email})")
    print(f"  Plan: ${amount_total}/mo | Categories: {categories}")
    print(f"  Business: {business_name} | Phone: {phone}")

    # Save subscriber
    save_subscriber({
        "name": customer_name,
        "email": customer_email,
        "business_name": business_name,
        "phone": phone,
        "categories": categories,
        "amount": amount_total,
        "subscribed_at": datetime.now(timezone.utc).isoformat(),
        "stripe_session_id": session.get("id", ""),
    })

    # Send welcome email
    subprocess.run([
        "python3", str(EMAIL_ENGINE), "welcome",
        "--email", customer_email,
        "--name", customer_name,
        "--categories", categories,
        "--category-count", str(category_count),
    ], check=False)

    # Notify admin
    subprocess.run([
        "python3", str(EMAIL_ENGINE), "admin-signup",
        "--email", ADMIN_EMAIL,
        "--name", customer_name,
        "--business", business_name,
        "--phone", phone,
        "--categories", categories,
        "--category-count", str(category_count),
        "--amount", str(int(amount_total)),
    ], check=False)

    return {"status": "ok", "email": customer_email}

# ── Subscriber DB ────────────────────────────────────────────
def load_subscribers() -> list[dict]:
    if SUBSCRIBERS_FILE.exists():
        return json.loads(SUBSCRIBERS_FILE.read_text())
    return []

def save_subscriber(sub: dict):
    subs = load_subscribers()
    subs.append(sub)
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps(subs, indent=2) + "\n")
    print(f"Saved to {SUBSCRIBERS_FILE}")

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    # Accept JSON from stdin (for webhook piping)
    if not sys.stdin.isatty():
        payload = json.load(sys.stdin)
        event_type = payload.get("type", "")
        if event_type == "checkout.session.completed":
            result = handle_checkout_completed(payload)
            print(json.dumps(result))
        else:
            print(json.dumps({"status": "ignored", "type": event_type}))
    else:
        print("Usage: stripe listen --forward-to 'python3 webhook_handler.py'")
