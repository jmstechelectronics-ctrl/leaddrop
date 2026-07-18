#!/usr/bin/env python3
"""
LeadDrop — Permalink Extractor (Save Post Method)
=================================================
Backup method for extracting Facebook post permalinks when DOM
extraction fails. Uses the reliable Save Post → /saved/ workflow.

Run after the scraper: python3 extract_permalinks.py
Reads trade-leads-accumulated.json, fills in missing permalinks
"""
import json
import subprocess
import sys
import time
from pathlib import Path

KIMI = "http://127.0.0.1:10086/command"
LEADS_FILE = Path.home() / "kramer-data/state/trade-leads-accumulated.json"
SESSION = "leaddrop-links"

def api(action, args=None):
    body = {"action": action, "args": args or {}, "session": SESSION}
    r = subprocess.run(
        ["curl", "-s", "--max-time", "15", "-X", "POST", KIMI,
         "-H", "Content-Type: application/json", "-d", json.dumps(body)],
        capture_output=True, text=True, timeout=20
    )
    return json.loads(r.stdout)

def navigate(url):
    return api("navigate", {"url": url, "newTab": True})

def snapshot():
    r = api("snapshot")
    if r.get("ok"):
        return r["data"].get("tree", [])
    return []

def click(ref):
    api("click", {"selector": ref})

def extract_links_for_leads(leads_without_links, group_url):
    """Save all leads, go to /saved/, extract links."""
    print(f"  Saving {len(leads_without_links)} posts...")
    
    # Navigate to group
    r = api("navigate", {"url": group_url, "newTab": True})
    if not r.get("ok"):
        print(f"  ✗ Failed to navigate to group")
        return {}
    
    time.sleep(4)
    
    link_map = {}
    
    for lead in leads_without_links:
        fingerprint = lead.get("fingerprint", "")[:60]
        if not fingerprint:
            continue
        
        # Find the post by text and click 3-dot menu
        js_find = f'''
(function() {{
    var texts = document.querySelectorAll("div[dir=auto]");
    var target = null;
    for (var i = 0; i < texts.length; i++) {{
        if (texts[i].textContent.indexOf({json.dumps(fingerprint)}) >= 0) {{
            target = texts[i];
            break;
        }}
    }}
    if (!target) return JSON.stringify({{error: "not found"}});
    
    // Walk up to article
    var article = target;
    while (article && article.getAttribute("role") !== "article") {{
        article = article.parentElement;
    }}
    if (!article) return JSON.stringify({{error: "no article"}});
    
    // Find 3-dot menu
    var menus = article.querySelectorAll('[aria-label*="Actions" i], [aria-label*="action" i]');
    for (var j = 0; j < menus.length; j++) {{
        menus[j].click();
        return JSON.stringify({{ok: true}});
    }}
    return JSON.stringify({{error: "no menu"}});
}})()
'''
        
        try:
            r = api("evaluate", {"code": js_find})
            if not r.get("ok"):
                continue
            
            time.sleep(1)
            
            # Click "Save Post"
            r = api("snapshot")
            tree = json.dumps(r.get("data", {}).get("tree", []))
            import re
            refs = re.findall(r'"@e(\d+)".*?"Save Post.*Add this to your saved items"', tree)
            if refs:
                click(f"@e{refs[0]}")
                time.sleep(1)
                
                # Click "Done"
                r = api("snapshot")
                tree2 = json.dumps(r.get("data", {}).get("tree", []))
                done_refs = re.findall(r'"@e(\d+)".*?"Done"', tree2)
                if done_refs:
                    click(f"@e{done_refs[0]}")
                    time.sleep(0.5)
        except Exception as e:
            print(f"    ⚠️ Save failed for {fingerprint[:40]}: {e}")
    
    # Navigate to saved items
    print("  Extracting from Saved Items...")
    api("navigate", {"url": "https://www.facebook.com/saved/", "newTab": False})
    time.sleep(4)
    
    for lead in leads_without_links:
        fingerprint = lead.get("fingerprint", "")[:60]
        if not fingerprint:
            continue
        
        # Find saved post by text
        js_find_saved = f'''
(function() {{
    var items = document.querySelectorAll("a[role=link]");
    for (var i = 0; i < items.length; i++) {{
        var text = items[i].textContent || "";
        if (text.indexOf({json.dumps(fingerprint[:40])}) >= 0) {{
            items[i].click();
            return JSON.stringify({{ok: true, url: window.location.href}});
        }}
    }}
    return JSON.stringify({{error: "not found in saved"}});
}})()
'''
        try:
            r = api("evaluate", {"code": js_find_saved})
            if r.get("ok"):
                data = json.loads(r["data"].get("value", "{}"))
                if "url" in data:
                    link_map[fingerprint] = data["url"]
                    time.sleep(2)
                    api("navigate", {"url": "https://www.facebook.com/saved/", "newTab": False})
                    time.sleep(3)
        except Exception as e:
            print(f"    ⚠️ Extract failed for {fingerprint[:40]}: {e}")
    
    return link_map

def main():
    if not LEADS_FILE.exists():
        print("No leads file found.")
        return
    
    leads = json.loads(LEADS_FILE.read_text())
    leads_list = leads.get("leads", {})
    
    # Find leads without proper permalinks
    needs_links = {}
    for key, lead in leads_list.items():
        link = lead.get("link", lead.get("permalink", ""))
        if not link or "/groups/" in link and "/permalink/" not in link:
            gid = lead.get("group_id", "")
            if gid:
                needs_links.setdefault(gid, []).append(lead)
    
    print(f"Leads without permalinks: {sum(len(v) for v in needs_links.values())}")
    
    for gid, group_leads in needs_links.items():
        group_url = f"https://www.facebook.com/groups/{gid}"
        print(f"\nGroup {gid}: {len(group_leads)} leads")
        
        link_map = extract_links_for_leads(group_leads, group_url)
        
        # Update leads
        updated = 0
        for lead in group_leads:
            fp = lead.get("fingerprint", "")[:60]
            if fp in link_map:
                lead["link"] = link_map[fp]
                lead["permalink"] = link_map[fp]
                updated += 1
        
        print(f"  ✓ Updated {updated}/{len(group_leads)}")
    
    # Save
    LEADS_FILE.write_text(json.dumps(leads, indent=2) + "\n")
    print(f"\nSaved to {LEADS_FILE}")

if __name__ == "__main__":
    main()
