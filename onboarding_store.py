"""Durable LeadDrop onboarding storage shared by the web endpoint and Stripe webhook."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIR = Path(os.environ.get("LEADDROP_DATA_DIR", Path.home() / "kramer-data" / "state"))
DB_PATH = Path(os.environ.get("LEADDROP_ONBOARDING_DB", STATE_DIR / "leaddrop-onboarding.sqlite3"))

STRIPE_LINKS = {
    (False, False): "https://buy.stripe.com/bJe6oJcxZ508gC47veg7e09",
    (True, False): "https://buy.stripe.com/eVqaEZ2Xp0JS3Pi7veg7e0a",
    (False, True): "https://buy.stripe.com/3cIdRb55x2S01Ha5n6g7e0b",
    (True, True): "https://buy.stripe.com/aFa00lapRfEMbhKbLug7e0c",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialise() -> None:
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS onboarding_records (
                onboarding_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                name TEXT NOT NULL,
                business_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                service_area TEXT NOT NULL,
                service_radius_km INTEGER NOT NULL,
                primary_category TEXT NOT NULL,
                preferred_services TEXT NOT NULL,
                work_type TEXT NOT NULL,
                exclusions TEXT NOT NULL,
                sms_addon INTEGER NOT NULL,
                category_addon INTEGER NOT NULL,
                additional_categories TEXT NOT NULL,
                monthly_total_aud INTEGER NOT NULL,
                stripe_payment_link TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                stripe_checkout_session_id TEXT UNIQUE,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS onboarding_status_idx ON onboarding_records(status)")
        # Coordinates are cached separately from onboarding records.  A suburb name
        # alone is not sufficient evidence to make a radius decision.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS geo_locations (
                query TEXT PRIMARY KEY,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                resolved_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_deliveries (
                onboarding_id TEXT NOT NULL,
                lead_fingerprint TEXT NOT NULL,
                delivered_at TEXT NOT NULL,
                channel TEXT NOT NULL,
                PRIMARY KEY (onboarding_id, lead_fingerprint, channel),
                FOREIGN KEY (onboarding_id) REFERENCES onboarding_records(onboarding_id)
            )
            """
        )


def create_record(record: dict[str, Any]) -> None:
    initialise()
    columns = [
        "onboarding_id", "status", "name", "business_name", "email", "phone", "service_area",
        "service_radius_km", "primary_category", "preferred_services", "work_type", "exclusions",
        "sms_addon", "category_addon", "additional_categories", "monthly_total_aud", "stripe_payment_link",
        "source", "created_at", "paid_at", "stripe_checkout_session_id", "stripe_customer_id", "stripe_subscription_id",
    ]
    values = [record.get(column) for column in columns]
    with connection() as conn:
        conn.execute(
            "INSERT INTO onboarding_records (" + ", ".join(columns) + ") VALUES (" + ", ".join("?" for _ in columns) + ")",
            values,
        )


def payment_link(sms_addon: bool, category_addon: bool) -> tuple[int, str]:
    return 31 + (10 if sms_addon else 0) + (10 if category_addon else 0), STRIPE_LINKS[(sms_addon, category_addon)]


def reconcile_checkout_session(session: dict[str, Any]) -> dict[str, str]:
    """Mark the matching onboarding record paid. Safe to call repeatedly for a Stripe event."""
    onboarding_id = str(session.get("client_reference_id") or "").strip()
    checkout_id = str(session.get("id") or "").strip()
    if not onboarding_id or not checkout_id:
        return {"result": "unmatched", "onboarding_id": onboarding_id}

    initialise()
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status, stripe_checkout_session_id FROM onboarding_records WHERE onboarding_id = ?",
            (onboarding_id,),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return {"result": "unmatched", "onboarding_id": onboarding_id}
        if row["stripe_checkout_session_id"] == checkout_id:
            conn.execute("COMMIT")
            return {"result": "idempotent", "onboarding_id": onboarding_id}
        if row["stripe_checkout_session_id"]:
            conn.execute("ROLLBACK")
            return {"result": "conflict", "onboarding_id": onboarding_id}

        subscription = session.get("subscription")
        conn.execute(
            """
            UPDATE onboarding_records
            SET status = ?, paid_at = ?, stripe_checkout_session_id = ?, stripe_customer_id = ?, stripe_subscription_id = ?
            WHERE onboarding_id = ?
            """,
            (
                "paid_pending_setup", now_iso(), checkout_id,
                str(session.get("customer") or "") or None,
                str(subscription or "") or None,
                onboarding_id,
            ),
        )
        conn.execute("COMMIT")
    return {"result": "updated", "onboarding_id": onboarding_id}


def additional_categories_json(categories: list[str]) -> str:
    return json.dumps(categories, ensure_ascii=False, separators=(",", ":"))
