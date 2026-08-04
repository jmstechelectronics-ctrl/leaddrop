#!/usr/bin/env python3
"""Match classified leads to paid LeadDrop profiles by real geographic distance.

This command is deliberately fail-closed: if either a customer's service area or
the lead location cannot be resolved to coordinates, the lead is not delivered.
Run it from the existing scheduler with ``--send`` only after SMTP delivery has
been verified. Without --send it reports eligible matches and changes nothing.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from onboarding_store import DB_PATH, initialise, now_iso

LEADS_PATH = Path(os.environ.get("LEADDROP_LEADS_FILE", Path.home() / "kramer-data" / "state" / "trade-leads-accumulated.json"))
GEOCODER_URL = os.environ.get("LEADDROP_GEOCODER_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = os.environ.get("LEADDROP_GEOCODER_USER_AGENT", "LeadDrop/1.0 (info@leaddrop.com.au)")
TRADE_ALIASES = {
    "electrical": {"electrician", "electrical"}, "electrician": {"electrician", "electrical"},
    "plumbing": {"plumber", "plumbing"}, "plumber": {"plumber", "plumbing"},
    "air conditioning": {"aircon", "air conditioning", "hvac"}, "cleaning": {"cleaner", "cleaning"},
}


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance, used only after both locations are resolved."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2-lon1)/2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def location_query(value: str) -> str:
    value = " ".join(value.split()).strip(" ,")
    if not value or value.lower() in {"unknown", "n/a", "none"}:
        return ""
    # Locations emitted by the classifier are Australian suburbs/towns.
    return value if "australia" in value.lower() else f"{value}, Australia"


def resolve_location(conn: sqlite3.Connection, raw: str) -> tuple[float, float] | None:
    query = location_query(raw)
    if not query:
        return None
    cached = conn.execute("SELECT latitude, longitude FROM geo_locations WHERE query = ?", (query,)).fetchone()
    if cached:
        return float(cached["latitude"]), float(cached["longitude"])
    params = urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": "1", "countrycodes": "au"})
    request = urllib.request.Request(f"{GEOCODER_URL}?{params}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result:
            return None
        point = (float(result[0]["lat"]), float(result[0]["lon"]))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Could not resolve location '{raw}': {exc}", file=sys.stderr)
        return None
    conn.execute("INSERT OR REPLACE INTO geo_locations(query, latitude, longitude, resolved_at) VALUES (?, ?, ?, ?)", (*point, now_iso()))
    conn.commit()
    # Public Nominatim requires no more than one request per second.
    time.sleep(1.05)
    return point


def trade_matches(profile_category: str, lead_trade: str) -> bool:
    profile = profile_category.casefold().strip()
    lead = lead_trade.casefold().strip()
    return lead == profile or lead in TRADE_ALIASES.get(profile, {profile})


def load_leads() -> list[dict[str, Any]]:
    if not LEADS_PATH.exists():
        return []
    data = json.loads(LEADS_PATH.read_text())
    return [lead for lead in data.get("leads", {}).values() if str(lead.get("is_lead")) == "True"]


def eligible_matches(conn: sqlite3.Connection) -> list[tuple[sqlite3.Row, dict[str, Any], float]]:
    # A payment is not an activation. Profiles must be reviewed before they are
    # eligible to receive leads, so only records explicitly marked active match.
    profiles = conn.execute("SELECT * FROM onboarding_records WHERE status = 'active'").fetchall()
    matches: list[tuple[sqlite3.Row, dict[str, Any], float]] = []
    for profile in profiles:
        centre = resolve_location(conn, profile["service_area"])
        if centre is None:
            print(f"Skipping {profile['onboarding_id']}: service area cannot be resolved", file=sys.stderr)
            continue
        for lead in load_leads():
            if not trade_matches(profile["primary_category"], str(lead.get("trade", ""))):
                continue
            lead_point = resolve_location(conn, str(lead.get("location", "")))
            if lead_point is None:
                continue
            km = distance_km(centre, lead_point)
            if km <= int(profile["service_radius_km"]):
                matches.append((profile, lead, km))
    return matches


def already_delivered(conn: sqlite3.Connection, onboarding_id: str, fingerprint: str) -> bool:
    return conn.execute("SELECT 1 FROM lead_deliveries WHERE onboarding_id = ? AND lead_fingerprint = ? AND channel = 'email'", (onboarding_id, fingerprint)).fetchone() is not None


def send_match(profile: sqlite3.Row, lead: dict[str, Any]) -> bool:
    # Reuse the deployed email renderer/sender; no customer information is placed
    # in a third-party analytics or geocoding request.
    from email_engine import render, send
    subject, html = render("lead", category=profile["primary_category"], lead=lead.get("summary", ""), location=lead.get("location", ""), permalink=lead.get("post_link", ""), time_ago="recently")
    return send(profile["email"], subject, html)


def main() -> int:
    parser = argparse.ArgumentParser(description="Find radius-eligible paid LeadDrop leads")
    parser.add_argument("--send", action="store_true", help="Send email and record delivery. Default is a no-change report.")
    parser.add_argument("--activate", metavar="ONBOARDING_ID", help="Mark one paid, reviewed profile active before matching.")
    args = parser.parse_args()
    initialise()
    with db() as conn:
        if args.activate:
            result = conn.execute(
                "UPDATE onboarding_records SET status = 'active' WHERE onboarding_id = ? AND status = 'paid_pending_setup'",
                (args.activate,),
            )
            conn.commit()
            if result.rowcount != 1:
                print("Profile was not activated: it must exist and be paid_pending_setup.", file=sys.stderr)
                return 1
            print(f"Activated {args.activate}")
            return 0
        matches = eligible_matches(conn)
        delivered = 0
        for profile, lead, km in matches:
            fingerprint = str(lead.get("fingerprint", ""))
            if not fingerprint or already_delivered(conn, profile["onboarding_id"], fingerprint):
                continue
            print(f"{profile['onboarding_id']} <- {lead.get('trade')} in {lead.get('location')} ({km:.1f} km)")
            if args.send and send_match(profile, lead):
                conn.execute("INSERT INTO lead_deliveries(onboarding_id, lead_fingerprint, delivered_at, channel) VALUES (?, ?, ?, 'email')", (profile["onboarding_id"], fingerprint, now_iso()))
                conn.commit()
                delivered += 1
        print(f"Eligible matches: {len(matches)}; emails sent: {delivered}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
