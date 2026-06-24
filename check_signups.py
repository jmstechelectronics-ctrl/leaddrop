#!/usr/bin/env python3
"""
LeadDrop Signup Checker
======================
Polled by cron every 10 minutes. Checks Stripe for new LeadDrop checkout
sessions, sends welcome emails, notifies admin, updates subscriber DB.
"""
import json
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta

STRIPE_KEY_FILE = Path.home() / ".config/leaddrop/stripe-live-key.txt"
SUBSCRIBERS_FILE = Path.home() / "kramer-data/state/leaddrop-subscribers.json"
EMAIL_ENGINE = Path.home() / "projects/leaddrop/email_engine.py"
ADMIN_EMAIL = "josh@jmstechsupport.com.au"
LEADDROP_PRICE_PREFIX = "price_1Tlea"  # All 4 LeadDrop price IDs start with this

def stripe(method, path, data=None):
    api_key = STRIPE_KEY_FILE.read_text().strip()
    url = f"https://api.stripe.com/v1{path}"
    headers = {"Authorization": f"Bearer {api_key}"}
    if data:
        data = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k,v in data.items()).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())

def load_subscribers():
    if SUBSCRIBERS_FILE.exists():
        return json.loads(SUBSCRIBERS_FILE.read_text())
    return []

def save_subscriber(sub):
    subs = load_subscribers()
    subs.append(sub)
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps(subs, indent=2) + "\n")

def send_email(template, email, **kwargs):
    args = ["python3", str(EMAIL_ENGINE), template, "--email", email]
    for k, v in kwargs.items():
        if v:
            args.extend([f"--{k}", str(v)])
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    print(f"  {template}: {result.stdout.strip()}")

def main():
    print(f"[{datetime.now().strftime('%H:%M')}] Checking LeadDrop signups...")
    
    # Get recent completed checkout sessions
    created_since = int((datetime.now() - timedelta(minutes=30)).timestamp())
    sessions = stripe("GET", "/checkout/sessions", {
        "limit": 50,
        "created[gte]": created_since,
        "status": "complete",
    })
    
    subs = load_subscribers()
    seen_ids = {s.get("stripe_session_id", "") for s in subs}
    new = 0
    
    for session in sessions.get("data", []):
        sid = session["id"]
        if sid in seen_ids:
            continue
        
        # Check if this is a LeadDrop session
        line_items = stripe("GET", f"/checkout/sessions/{sid}/line_items")
        is_leaddrop = False
        for item in line_items.get("data", []):
            if (item.get("price", {}).get("id", "").startswith(LEADDROP_PRICE_PREFIX)):
                is_leaddrop = True
                break
        
        if not is_leaddrop:
            continue
        
        details = session.get("customer_details", {}) or {}
        metadata = session.get("metadata", {}) or {}
        name = details.get("name", "there")
        email = details.get("email", "")
        amount = (session.get("amount_total", 0) or 0) / 100
        business = metadata.get("business_name", "")
        phone = metadata.get("phone", "")
        categories = metadata.get("categories", "")
        cat_count = metadata.get("category_count", "0")
        
        if not email:
            continue
        
        print(f"  NEW: {name} ({email}) — ${amount:.0f}/mo — {categories}")
        
        # Send welcome
        send_email("welcome", email,
            name=name, categories=categories, category_count=cat_count)
        
        # Notify admin
        send_email("admin-signup", ADMIN_EMAIL,
            name=name, email=email, business=business,
            phone=phone, categories=categories,
            category_count=cat_count, amount=str(int(amount)))
        
        # Save
        save_subscriber({
            "name": name,
            "email": email,
            "business_name": business,
            "phone": phone,
            "categories": categories,
            "amount": amount,
            "subscribed_at": datetime.now(timezone.utc).isoformat(),
            "stripe_session_id": sid,
        })
        new += 1
    
    if new == 0:
        print("  No new signups.")
    else:
        total = len(load_subscribers())
        print(f"  Done: {new} new, {total} total subscribers.")
    
    return new

if __name__ == "__main__":
    main()
