"""WSGI application for POST /api/leaddrop-onboarding.

Deploy behind the existing web server at the production domain. Set LEADDROP_DATA_DIR
to a persistent directory shared with the Stripe webhook process.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from collections import defaultdict, deque
from typing import Any
from wsgiref.simple_server import make_server

from onboarding_store import additional_categories_json, create_record, now_iso, payment_link

ALLOWED_ORIGIN = "https://leaddrop.com.au"
RADIUS_VALUES = {20, 30, 40, 60, 100}
WORK_TYPES = {"residential", "commercial", "both"}
MAX_BODY_BYTES = 12_000
RATE_LIMIT = 8
RATE_WINDOW_SECONDS = 60
_requests: dict[str, deque[float]] = defaultdict(deque)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message


def response(start_response, status: str, body: dict[str, Any], headers: list[tuple[str, str]] | None = None):
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    base_headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(payload))), ("Cache-Control", "no-store")]
    start_response(status, base_headers + (headers or []))
    return [payload]


def rate_limited(remote_addr: str) -> bool:
    now = time.monotonic()
    bucket = _requests[remote_addr or "unknown"]
    while bucket and bucket[0] <= now - RATE_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT:
        return True
    bucket.append(now)
    return False


def text(data: dict[str, Any], field: str, maximum: int, required: bool = False) -> str:
    value = data.get(field, "")
    if not isinstance(value, str):
        raise ValidationError(field, "Please check this field.")
    value = value.strip()
    if required and not value:
        raise ValidationError(field, "This field is required.")
    if len(value) > maximum:
        raise ValidationError(field, "This field is too long.")
    return value


def boolean(data: dict[str, Any], field: str) -> bool:
    value = data.get(field, False)
    if not isinstance(value, bool):
        raise ValidationError(field, "Please check this selection.")
    return value


def validate(data: dict[str, Any]) -> dict[str, Any]:
    name = text(data, "name", 120, True)
    business_name = text(data, "business_name", 160, True)
    email = text(data, "email", 254, True).lower()
    phone = text(data, "phone", 40, True)
    if not EMAIL_RE.match(email):
        raise ValidationError("email", "Enter a valid email address.")
    if not 8 <= len(re.sub(r"\D", "", phone)) <= 20:
        raise ValidationError("phone", "Enter a valid phone number.")
    try:
        radius = int(data.get("service_radius_km"))
    except (TypeError, ValueError):
        raise ValidationError("service_radius_km", "Choose a valid service radius.")
    if radius not in RADIUS_VALUES:
        raise ValidationError("service_radius_km", "Choose a valid service radius.")
    work_type = text(data, "work_type", 20, True)
    if work_type not in WORK_TYPES:
        raise ValidationError("work_type", "Choose a valid work type.")
    sms_addon = boolean(data, "sms_addon")
    category_addon = boolean(data, "category_addon")
    categories = data.get("additional_categories", [])
    if not isinstance(categories, list) or len(categories) > 10 or not all(isinstance(item, str) and 0 < len(item.strip()) <= 80 for item in categories):
        raise ValidationError("additional_categories", "Please check additional categories.")
    if not category_addon:
        categories = []
    total, stripe_link = payment_link(sms_addon, category_addon)
    return {
        "onboarding_id": "ld_" + secrets.token_urlsafe(18), "status": "pending_payment",
        "name": name, "business_name": business_name, "email": email, "phone": phone,
        "service_area": text(data, "service_area", 120, True), "service_radius_km": radius,
        "primary_category": text(data, "primary_category", 100, True),
        "preferred_services": text(data, "preferred_services", 500), "work_type": work_type,
        "exclusions": text(data, "exclusions", 500), "sms_addon": int(sms_addon),
        "category_addon": int(category_addon), "additional_categories": additional_categories_json([item.strip() for item in categories]),
        "monthly_total_aud": total, "stripe_payment_link": stripe_link,
        "source": "LeadDrop website signup", "created_at": now_iso(), "paid_at": None,
        "stripe_checkout_session_id": None, "stripe_customer_id": None, "stripe_subscription_id": None,
    }


def application(environ, start_response):
    if environ.get("PATH_INFO") != "/api/leaddrop-onboarding":
        return response(start_response, "404 Not Found", {"success": False, "message": "Not found."})
    if environ.get("REQUEST_METHOD") == "OPTIONS":
        origin = environ.get("HTTP_ORIGIN")
        if origin != ALLOWED_ORIGIN:
            return response(start_response, "403 Forbidden", {"success": False, "message": "Not allowed."})
        return response(start_response, "204 No Content", {}, [("Access-Control-Allow-Origin", ALLOWED_ORIGIN), ("Access-Control-Allow-Methods", "POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type")])
    if environ.get("REQUEST_METHOD") != "POST":
        return response(start_response, "405 Method Not Allowed", {"success": False, "message": "Method not allowed."}, [("Allow", "POST, OPTIONS")])
    origin = environ.get("HTTP_ORIGIN")
    if origin and origin != ALLOWED_ORIGIN:
        return response(start_response, "403 Forbidden", {"success": False, "message": "Not allowed."})
    if rate_limited(environ.get("REMOTE_ADDR", "")):
        return response(start_response, "429 Too Many Requests", {"success": False, "message": "Please wait a moment and try again."})
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        length = 0
    if length <= 0 or length > MAX_BODY_BYTES:
        return response(start_response, "400 Bad Request", {"success": False, "field": "form", "message": "Please check your setup and try again."})
    if not (environ.get("CONTENT_TYPE") or "").startswith("application/json"):
        return response(start_response, "415 Unsupported Media Type", {"success": False, "message": "Please try again."})
    try:
        data = json.loads(environ["wsgi.input"].read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        record = validate(data)
    except ValidationError as error:
        return response(start_response, "400 Bad Request", {"success": False, "field": error.field, "message": error.message})
    except (ValueError, UnicodeDecodeError, KeyError):
        return response(start_response, "400 Bad Request", {"success": False, "field": "form", "message": "Please check your setup and try again."})
    try:
        create_record(record)
    except Exception:
        return response(start_response, "500 Internal Server Error", {"success": False, "message": "We could not save your setup. Please try again."})
    return response(start_response, "201 Created", {"success": True, "onboarding_id": record["onboarding_id"], "stripe_payment_link": record["stripe_payment_link"]})


if __name__ == "__main__":
    make_server("127.0.0.1", 8000, application).serve_forever()
