#!/usr/bin/env python3
"""
LeadDrop Telegram Bot
=====================
Handles /start commands to link subscribers' Telegram accounts.
Polls Telegram API for updates, processes leaddrop_<id> deep links.

Run via systemd or cron: python3 telegram_bot.py
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

TOKEN_FILE = Path.home() / ".config/leaddrop/telegram-bot-token.txt"
SUBSCRIBERS_FILE = Path.home() / "kramer-data/state/leaddrop-subscribers.json"
STATE_FILE = Path.home() / "kramer-data/state/leaddrop-bot-state.json"

def telegram(method: str, data: dict = None) -> dict:
    token = TOKEN_FILE.read_text().strip()
    url = f"https://api.telegram.org/bot{token}/{method}"
    if data:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_update_id": 0, "linked": {}}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")

def load_subscribers():
    if SUBSCRIBERS_FILE.exists():
        return json.loads(SUBSCRIBERS_FILE.read_text())
    return []

def save_subscribers(subs):
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps(subs, indent=2) + "\n")

def handle_start(chat_id: int, text: str, state: dict):
    """Handle /start leaddrop_<subscriber_id>"""
    if not text.startswith("leaddrop_"):
        telegram("sendMessage", {
            "chat_id": chat_id,
            "text": "👋 G'day! This is the LeadDrop bot.\n\n"
                    "To link your account, use the setup link from your welcome email.\n"
                    "It looks like: /start leaddrop_yourcode"
        })
        return

    sub_id = text.replace("leaddrop_", "").strip()
    subs = load_subscribers()
    found = None
    
    for s in subs:
        # Match by subscriber_id (email hash or stored ID)
        if s.get("telegram_id") == sub_id or s.get("stripe_session_id", "").endswith(sub_id):
            found = s
            break
    
    if not found:
        telegram("sendMessage", {
            "chat_id": chat_id,
            "text": "❌ Couldn't find your account. Check your setup email and try again, "
                    "or reply to the welcome email for help."
        })
        return

    # Link Telegram
    found["telegram_chat_id"] = chat_id
    found["telegram_linked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_subscribers(subs)

    state["linked"][str(chat_id)] = sub_id
    save_state(state)

    # Send confirmation
    name = found.get("name", "there")
    cats = found.get("categories", "your categories")
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": f"✅ You're all set, {name}!\n\n"
                f"LeadDrop is now monitoring {cats} for you across the Northern Rivers.\n"
                f"When someone posts a service request matching your categories, "
                f"you'll get an alert right here — usually within the hour.\n\n"
                f"Reply to this chat anytime if you need help.\n\n"
                f"⚡ Your first leads will arrive soon.",
        "parse_mode": "HTML"
    })

def poll():
    state = load_state()
    
    updates = telegram("getUpdates", {
        "offset": state["last_update_id"] + 1,
        "timeout": 30
    })

    for update in updates.get("result", []):
        update_id = update["update_id"]
        state["last_update_id"] = max(state["last_update_id"], update_id)

        message = update.get("message", {})
        if not message:
            continue

        text = message.get("text", "")
        chat_id = message["chat"]["id"]

        if text.startswith("/start"):
            # Extract payload after /start
            # Telegram sends "/start leaddrop_xxx" or just "/start"
            payload = text[7:].strip() if len(text) > 6 else ""
            handle_start(chat_id, payload, state)

    save_state(state)

if __name__ == "__main__":
    print("LeadDrop Telegram Bot running...")
    try:
        while True:
            try:
                poll()
            except Exception as e:
                print(f"Poll error: {e}")
                time.sleep(5)
    except KeyboardInterrupt:
        print("Stopped.")
