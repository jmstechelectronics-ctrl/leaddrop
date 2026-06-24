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
ADMIN_EMAIL = "josh@jmstechsupport.com.au"

def load_json(path: Path) -> list:
    if path.exists():
        return json.loads(path.read_text())
    return []

def main():
    subs = load_json(SUBSCRIBERS_FILE)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Count new today
    new_today = [s for s in subs if s.get("subscribed_at", "")[:10] == now.strftime("%Y-%m-%d")]
    total = len(subs)
    mrr = sum(s.get("amount", 0) for s in subs)
    
    # Lead stats
    leads = load_json(LEADS_FILE)
    leads_today = [l for l in leads if l.get("scraped_at", "")[:10] == now.strftime("%Y-%m-%d")]
    
    # Build summary
    subject = f"📊 LeadDrop Daily — {now.strftime('%b %d')}"
    body = f"""
    <p style="color:#7a7a75;font-size:16px;line-height:1.7;margin:0 0 20px;">
      Daily summary for {now.strftime('%A, %B %d, %Y')}.
    </p>
    
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
      <tr>
        <td style="padding:12px 16px;background:#18191b;border-radius:6px;">
          <span style="color:#5c5c57;font-size:12px;">New today</span><br>
          <span style="color:#eab308;font-size:24px;font-weight:700;">{len(new_today)}</span>
        </td>
        <td width="12"></td>
        <td style="padding:12px 16px;background:#18191b;border-radius:6px;">
          <span style="color:#5c5c57;font-size:12px;">Total subscribers</span><br>
          <span style="color:#f0f0ec;font-size:24px;font-weight:700;">{total}</span>
        </td>
        <td width="12"></td>
        <td style="padding:12px 16px;background:#18191b;border-radius:6px;">
          <span style="color:#5c5c57;font-size:12px;">MRR</span><br>
          <span style="color:#eab308;font-size:24px;font-weight:700;">${mrr:.0f}</span>
        </td>
      </tr>
    </table>
    
    <table width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0;">
      <tr>
        <td style="padding:12px 16px;background:#18191b;border-radius:6px;">
          <span style="color:#5c5c57;font-size:12px;">Leads detected today</span><br>
          <span style="color:#f0f0ec;font-size:24px;font-weight:700;">{len(leads_today)}</span>
        </td>
      </tr>
    </table>
    """
    
    if new_today:
        body += '<p style="color:#7a7a75;font-size:14px;margin:20px 0 8px;">New signups today:</p>'
        for s in new_today:
            body += f"""
            <p style="color:#f0f0ec;font-size:14px;margin:4px 0;padding:8px 12px;background:#18191b;border-radius:4px;">
              <strong>{s.get('name','?')}</strong> &mdash; {s.get('business_name','?')}<br>
              <span style="color:#7a7a75;font-size:12px;">{s.get('categories','?')} &middot; ${s.get('amount',0)}/mo</span>
            </p>
            """

    # Send admin report
    subprocess.run([
        "python3", str(EMAIL_ENGINE),
        "--email", ADMIN_EMAIL,
    ], input=body.encode(), check=False)
    
    print(f"Daily report: {len(new_today)} new, {total} total, ${mrr:.0f} MRR")
    print(subject)
    print(body)

if __name__ == "__main__":
    main()
