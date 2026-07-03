#!/usr/bin/env python3
"""
LeadDrop Daily Reporter
=======================
Generates and emails a daily summary of LeadDrop activity.
- New signups today
- Total subscribers
- Monthly recurring revenue
- Leads delivered
- Any issues

Run via cron: 0 8 * * * python3 ~/projects/leaddrop/daily_report.py
"""
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

LEADDROP_DIR = Path(__file__).parent
EMAIL_ENGINE = LEADDROP_DIR / "email_engine.py"
SUBSCRIBERS_FILE = Path.home() / "kramer-data/state/leaddrop-subscribers.json"
LEADS_FILE = Path.home() / "kramer-data/state/trade-leads-accumulated.json"
DIGEST_EMAIL = "josh@jmstechsupport.com.au"

def load_json(path: Path) -> list:
    if path.exists():
        return json.loads(path.read_text())
    return []

def load_lead_records(path: Path) -> list[dict]:
    data = load_json(path)
    if isinstance(data, dict):
        leads = data.get("leads", [])
        if isinstance(leads, dict):
            return [v for v in leads.values() if isinstance(v, dict)]
        if isinstance(leads, list):
            return [v for v in leads if isinstance(v, dict)]
    if isinstance(data, list):
        return [v for v in data if isinstance(v, dict)]
    return []

def main():
    subs = load_json(SUBSCRIBERS_FILE)
    now = datetime.now(timezone.utc)

    # Count new today
    new_today = [s for s in subs if s.get("subscribed_at", "")[:10] == now.strftime("%Y-%m-%d")]
    total = len(subs)
    mrr = sum(s.get("amount", 0) for s in subs)
    
    # Lead stats
    leads = load_lead_records(LEADS_FILE)
    leads_today = len(leads)
    
    new_signup_block = ""
    if new_today:
        new_signup_block = '<p style="color:#7a7a75;font-size:14px;margin:20px 0 8px;">New signups today:</p>'
        for s in new_today:
            new_signup_block += (
                f'<p style="color:#f0f0ec;font-size:14px;margin:4px 0;padding:8px 12px;background:#18191b;border-radius:4px;">'
                f'<strong>{s.get("name","?")}</strong> &mdash; {s.get("business_name","?")}<br>'
                f'<span style="color:#7a7a75;font-size:12px;">{s.get("categories","?")} &middot; ${s.get("amount",0)}/mo</span>'
                f'</p>'
            )

    subprocess.run([
        "python3", str(EMAIL_ENGINE),
        "daily-digest",
        "--email", DIGEST_EMAIL,
        "--date", now.strftime("%A, %B %d, %Y"),
        "--new-today", str(len(new_today)),
        "--total-subscribers", str(total),
        "--mrr", f"{mrr:.0f}",
        "--leads-today", str(leads_today),
        "--new-signup-block", new_signup_block,
    ], check=False)

    print(f"Daily report sent to {DIGEST_EMAIL}: {len(new_today)} new, {total} total, ${mrr:.0f} MRR")

if __name__ == "__main__":
    main()
