#!/usr/bin/env python3
"""
LeadDrop Email Engine
=====================
Builds HTML emails from templates, sends via VentraIP SMTP (info@leaddrop.com.au).
Templates use {key} placeholders. Layout wraps body in branded HTML shell.

Usage:
    python3 email_engine.py welcome --name "John" --email "john@example.com" --categories "Plumbing"
    python3 email_engine.py lead --email "john@example.com" --category "Plumbing" \\
        --lead "Anyone know a good plumber?" --location "Yamba" --permalink "https://..."
    python3 email_engine.py admin-signup --name "John" --business "Smith Electrical" \\
        --email "john@example.com" --phone "0412..." --categories "Plumbing, Electrical" \\
        --amount 49
"""
import argparse
import json
import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime

EMAILS_DIR = Path(__file__).parent / "emails"
LAYOUT_PATH = EMAILS_DIR / "layout.html"
SMTP_HOST = "ventraip.email"
SMTP_PORT = 465
FROM_EMAIL = "LeadDrop <info@leaddrop.com.au>"
FROM_ADDR = "info@leaddrop.com.au"
PASS_FILE = Path(os.path.expanduser("~/.config/leaddrop/smtp-pass.txt"))

# ── Template engine ──────────────────────────────────────────
def load_template(name: str) -> dict:
    """Load template file, return {subject, body}."""
    path = EMAILS_DIR / f"{name}.txt"
    text = path.read_text()
    # Parse {subject}...{/subject} and {body}...{/body}
    subj = re.search(r'\{subject\}\s*(.+?)\{/subject\}', text, re.DOTALL)
    body = re.search(r'\{body\}\s*(.+?)\{/body\}', text, re.DOTALL)
    return {
        "subject": subj.group(1).strip().replace('\n', ' ') if subj else "",
        "body": body.group(1).strip() if body else text,
    }

def render(template_name: str, **kwargs) -> tuple[str, str]:
    """Render template with kwargs, return (subject, html)."""
    tmpl = load_template(template_name)
    layout = LAYOUT_PATH.read_text()
    subject = tmpl["subject"]
    body = tmpl["body"]
    for k, v in kwargs.items():
        subject = subject.replace("{" + k + "}", str(v))
        body = body.replace("{" + k + "}", str(v))
    # Remove unused placeholders
    subject = re.sub(r'\{[^}]+\}', '', subject).strip()
    body = re.sub(r'\{/?if[^}]*\}', '', body)
    body = re.sub(r'\{/?multiple\}', '', body)
    body = re.sub(r'\{[^}]+\}', '', body).strip()
    # Insert body into layout
    html = layout.replace("{subject}", subject).replace("{body}", body)
    return subject, html

# ── SMTP sender ──────────────────────────────────────────────
def send(to_email: str, subject: str, html: str) -> bool:
    """Send HTML email via VentraIP SMTP."""
    if not PASS_FILE.exists():
        print(f"ERROR: Password file not found at {PASS_FILE}")
        return False
    
    password = PASS_FILE.read_text().strip()
    msg = MIMEMultipart("alternative")
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=ctx) as conn:
            conn.login(FROM_ADDR, password)
            conn.send_message(msg)
        print(f"✓ Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"✗ Failed: {e}")
        return False

# ── CLI ──────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LeadDrop Email Engine")
    parser.add_argument("template", choices=["welcome", "lead", "admin-signup", "telegram-setup"])
    parser.add_argument("--email", required=True, help="Recipient email")
    parser.add_argument("--name", default="", help="Customer name")
    parser.add_argument("--business", default="", help="Business name")
    parser.add_argument("--phone", default="", help="Phone number")
    parser.add_argument("--categories", default="", help="Selected categories")
    parser.add_argument("--category", default="", help="Single category name")
    parser.add_argument("--lead", default="", help="Lead text")
    parser.add_argument("--location", default="", help="Lead location")
    parser.add_argument("--permalink", default="#", help="Lead permalink")
    parser.add_argument("--amount", default="39", help="Plan amount")
    parser.add_argument("--time-ago", default="recently", help="When posted")
    parser.add_argument("--lead-count", default="1", help="Leads matched today")
    parser.add_argument("--category-count", default="0", help="Number of categories")
    parser.add_argument("--subscriber-id", default="", help="Subscriber identifier for Telegram linking")
    parser.add_argument("--dry-run", action="store_true", help="Print HTML, don't send")

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if v is not None}
    template_name = kwargs.pop("template")
    dry_run = kwargs.pop("dry_run")
    del kwargs["email"]  # handled separately
    
    subject, html = render(template_name, email=args.email, **kwargs)
    
    if dry_run:
        print(f"SUBJECT: {subject}")
        print(f"HTML: {html[:1000]}...")
    else:
        send(args.email, subject, html)
