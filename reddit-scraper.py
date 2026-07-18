#!/usr/bin/env python3
"""Reddit scraper for LeadDrop — polls subreddits for trade/service lead posts.

Uses RSS feeds (public, no auth). Outputs reddit-leads.json compatible with pipeline.

Usage:
    python3 reddit-scraper.py              # scrape once, output to reddit-leads.json
    python3 reddit-scraper.py --merge      # scrape + merge into main leads.json
"""

import json, urllib.request, urllib.error, time, re, sys, os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────
SUBREDDITS = [
    "AusRenovation",
    "AusFinance",
    "australia",
    "sydney",
]

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Keywords that indicate someone looking for a service
LEAD_PATTERNS = [
    r"recommend\s+(?:a|an|me\s+a)\s+(\w+(?:\s+\w+){0,3})",
    r"looking\s+for\s+(?:a|an)\s+(\w+(?:\s+\w+){0,3})",
    r"can\s+any(?:one|body)\s+recommend\s+(?:a|an)\s+(\w+(?:\s+\w+){0,3})",
    r"need\s+(?:a|an)\s+(\w+(?:\s+\w+){0,3})\s+(?:in|near|around)",
    r"any(?:one|body)\s+know\s+(?:a|of\s+a)\s+(?:good\s+)?(\w+(?:\s+\w+){0,3})",
]

TRADE_CATEGORIES = {
    "plumber": "Plumbing & Gas",
    "plumbing": "Plumbing & Gas",
    "electrician": "Electrical",
    "electrical": "Electrical",
    "sparky": "Electrical",
    "builder": "Building",
    "carpenter": "Carpentry",
    "carpentry": "Carpentry",
    "painter": "Painting",
    "painting": "Painting",
    "roofer": "Roofing",
    "roofing": "Roofing",
    "tiler": "Tiling",
    "tiling": "Tiling",
    "concreter": "Concreting",
    "concreting": "Concreting",
    "landscaper": "Landscaping",
    "landscaping": "Landscaping",
    "gardener": "Gardening",
    "gardening": "Gardening",
    "cleaner": "Cleaning",
    "cleaning": "Cleaning",
    "pest control": "Pest Control",
    "solar": "HVAC & Solar",
    "air conditioning": "HVAC & Solar",
    "hvac": "HVAC & Solar",
    "mechanic": "Automotive",
    "auto": "Automotive",
    "locksmith": "Locksmiths",
    "fencing": "Fencing",
    "welder": "Welding",
    "welding": "Welding",
    "glazier": "Glazing",
    "glazing": "Glazing",
    "cabinet": "Cabinetmaking",
    "flooring": "Flooring",
    "waterproofing": "Waterproofing",
    "tech support": "Tech Support",
    "it support": "Tech Support",
    "rubbish": "Rubbish Removal",
    "skip bin": "Rubbish Removal",
    "plasterer": "Plastering",
    "plastering": "Plastering",
    "earthmoving": "Earthmoving",
    "excavator": "Earthmoving",
    "earth mover": "Earthmoving",
    "welder": "Welding",
    "bookkeeper": "Bookkeeping",
    "bookkeeping": "Bookkeeping",
    "accountant": "Bookkeeping",
    "beauty": "Beauty",
    "hairdresser": "Beauty",
    "barber": "Beauty",
}

# NSW location keywords
LOCATIONS = [
    "grafton", "yamba", "maclean", "coffs harbour", "coffs", "ballina",
    "lismore", "byron", "casino", "evans head", "iluka", "woolgoolga",
    "northern rivers", "clarence valley", "mid north coast", "nsw",
    "sydney", "newcastle", "port macquarie", "taree", "armidale",
    "tamworth", "dubbo", "wagga", "albury", "central coast", "wollongong",
]

ATOM_NS = "http://www.w3.org/2005/Atom"
OUTPUT_DIR = Path(os.environ.get("LEADDROP_STATE", str(Path.home() / "kramer-data/state/leaddrop")))


def fetch_rss(subreddit, limit=50, retries=3):
    """Fetch subreddit RSS feed with retry on rate limit."""
    url = f"https://www.reddit.com/r/{subreddit}/new/.rss?limit={limit}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = (attempt + 1) * 10
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise


def parse_rss(xml_text):
    """Parse Reddit Atom feed into entries."""
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        content_el = entry.find(f"{{{ATOM_NS}}}content")
        link_el = entry.find(f"{{{ATOM_NS}}}link")
        id_el = entry.find(f"{{{ATOM_NS}}}id")
        updated_el = entry.find(f"{{{ATOM_NS}}}updated")
        category_els = entry.findall(f"{{{ATOM_NS}}}category")

        title = title_el.text if title_el is not None else ""
        content = content_el.text if content_el is not None else ""
        link = link_el.get("href") if link_el is not None else ""
        post_id = id_el.text.split("/")[-1] if id_el is not None and id_el.text else ""
        updated = updated_el.text if updated_el is not None else ""
        categories = [c.get("term", "") for c in category_els]

        entries.append({
            "title": title,
            "content": content,
            "link": link,
            "id": post_id,
            "updated": updated,
            "categories": categories,
        })
    return entries


def strip_html(text):
    """Remove HTML tags and entities from text."""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', ' ', text)
    # Decode common HTML entities
    clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    clean = clean.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
    return clean


def classify_trade(text):
    """Map extracted keywords to LeadDrop categories."""
    text_lower = text.lower()
    for keyword, category in TRADE_CATEGORIES.items():
        if keyword in text_lower:
            return category
    return "other"


def extract_location(text):
    """Find location mentions in text."""
    text_lower = text.lower()
    for loc in LOCATIONS:
        if loc in text_lower:
            return loc.title()
    return "unknown"


def scrape_subreddit(subreddit, limit=50):
    """Scrape a subreddit RSS feed for potential leads."""
    leads = []

    try:
        xml_text = fetch_rss(subreddit, limit=limit)
        entries = parse_rss(xml_text)
    except Exception as e:
        print(f"  Error fetching r/{subreddit}: {e}")
        return leads

    for entry in entries:
        title = entry["title"]
        content = entry["content"]
        full_text = f"{title} {content}"
        # Strip HTML before matching/classifying — RSS content has HTML
        clean_text = strip_html(full_text)

        # Check if it matches a lead pattern
        matched = False
        for pattern in LEAD_PATTERNS:
            if re.search(pattern, clean_text, re.IGNORECASE):
                matched = True
                break

        if not matched:
            continue

        category = classify_trade(clean_text)
        if category == "other":
            continue

        location = extract_location(clean_text)

        leads.append({
            "id": f"reddit_{entry['id']}",
            "text": title[:200],
            "full_text": clean_text[:500],
            "category": category,
            "location": location,
            "source": f"r/{subreddit}",
            "url": entry["link"],
            "date": entry["updated"],
            "fingerprint": f"reddit_{entry['id']}",
        })

    return leads


def main():
    merge = "--merge" in sys.argv
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_leads = []

    for sub in SUBREDDITS:
        print(f"Scanning r/{sub}...")
        leads = scrape_subreddit(sub, limit=50)
        print(f"  {len(leads)} leads found")
        all_leads.extend(leads)
        time.sleep(45)  # Reddit rate limit — 45s between subs

    # Save to reddit-leads.json
    out_file = OUTPUT_DIR / "reddit-leads.json"
    with open(out_file, "w") as f:
        json.dump(all_leads, f, indent=2)

    print(f"\nSaved {len(all_leads)} leads to {out_file}")

    # Print summary
    for lead in all_leads[:10]:
        print(f"  [{lead['category']}] {lead['text'][:80]} — {lead['location']}")
    if len(all_leads) > 10:
        print(f"  ... and {len(all_leads) - 10} more")

    # Merge into main leads.json
    if merge:
        main_file = OUTPUT_DIR / "leads.json"
        existing = []
        if main_file.exists():
            existing = json.loads(main_file.read_text())

        existing_fps = {l.get("fingerprint", "") for l in existing}
        new = [l for l in all_leads if l["fingerprint"] not in existing_fps]
        existing.extend(new)

        with open(main_file, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"Merged {len(new)} new leads into {main_file} ({len(existing)} total)")


if __name__ == "__main__":
    main()
