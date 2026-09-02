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
DIRECT_FACEBOOK_POST_URL = re.compile(
    r'https://(?:www\.)?facebook\.com/(?:groups/[^/]+/posts/\d+/?(?:\?[^\s"\']*)?|permalink\.php\?[^\s"\']*story_fbid=\d+)',
    re.IGNORECASE,
)

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


def read_cards(path_value: str, *, label: str, require_direct_links: bool) -> str:
    """Read manually curated report cards and validate direct links where required."""
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        raise ValueError(f"{label} file was not found: {path}")
    cards = path.read_text().strip()
    if not cards:
        return ""
    facebook_links = re.findall(r'''href=["'](https?://[^"']*facebook\.com[^"']*)["']''', cards, flags=re.IGNORECASE)
    if require_direct_links and (not facebook_links or any(not DIRECT_FACEBOOK_POST_URL.fullmatch(link) for link in facebook_links)):
        raise ValueError(f"{label} cards must use exact Facebook post permalinks; group-search links are not allowed")
    return cards


def report_section(title: str, cards: str) -> str:
    if not cards:
        return ""
    return (
        '<section style="margin:0 0 28px;">'
        f'<h2 style="color:#f0f0ec;font-size:20px;margin:0 0 14px;">{title}</h2>'
        f'{cards}'
        '</section>'
    )

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
    parser.add_argument("template", choices=["welcome", "lead", "admin-signup", "telegram-setup", "weekly-report"])
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
    parser.add_argument("--report-date", default="", help="Date displayed on a weekly report")
    parser.add_argument("--fresh-permalink-cards-file", default="", help="HTML cards for new leads with exact Facebook post links")
    parser.add_argument("--fresh-other-cards-file", default="", help="HTML cards for new leads without a direct permalink")
    parser.add_argument("--missed-lead-cards-file", default="", help="HTML cards for older local leads worth revisiting")
    parser.add_argument("--upgrade-url", default="https://leaddrop.com.au/light/#profile-builder", help="LeadDrop Premium upgrade URL")
    parser.add_argument("--dry-run", action="store_true", help="Print HTML, don't send")

    args = parser.parse_args()
    kwargs = {k: v for k, v in vars(args).items() if v is not None}
    template_name = kwargs.pop("template")
    dry_run = kwargs.pop("dry_run")
    del kwargs["email"]  # handled separately

    if template_name == "weekly-report":
        try:
            fresh_permalink = read_cards(kwargs.pop("fresh_permalink_cards_file", ""), label="Fresh permalink", require_direct_links=True)
            fresh_other = read_cards(kwargs.pop("fresh_other_cards_file", ""), label="Fresh other", require_direct_links=False)
            missed = read_cards(kwargs.pop("missed_lead_cards_file", ""), label="Missed lead", require_direct_links=True)
        except ValueError as exc:
            parser.error(str(exc))
        if not (fresh_permalink or fresh_other or missed):
            parser.error("weekly-report requires at least one fresh or missed lead card")
        sections: list[str] = []
        if fresh_permalink:
            sections.append(report_section("New local leads", fresh_permalink))
        if fresh_other:
            sections.append(report_section("More local leads", fresh_other))
        if missed:
            sections.append(report_section("Leads you may have missed!", missed))
        kwargs["report_sections"] = "".join(sections)
    
    subject, html = render(template_name, email=args.email, **kwargs)
    
    if dry_run:
        print(f"SUBJECT: {subject}")
        print(f"HTML: {html[:1000]}...")
    else:
        send(args.email, subject, html)
