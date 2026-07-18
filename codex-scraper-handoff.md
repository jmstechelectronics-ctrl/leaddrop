# Codex Handoff — Scraper Expansion

## What's done
- Baseline expanded from 55 to 147 groups (77 new Northern Rivers/Clarence Valley groups added)
- File: `/home/josh/kramer-data/state/all-groups-baseline.json`
- Groups extracted from Fred's Facebook membership (252 total, filtered to 83 service-request groups, 77 net new)

## What Codex needs to build

### Multi-scraper architecture
- Split `all-groups-baseline.json` into two files: `all-groups-1.json` (~73 groups) and `all-groups-2.json` (~74 groups)
- Two CDP Chrome instances: Fred on 9223, second profile on 9225
- Both run `clawbot-group-scraper.py` hourly at :00, each reading their own baseline
- Output: two JSON files → merge script extracts leads from both → single `group-leads.json`
- Merge runs at :40 each hour
- Target: each instance finishes in ~35 min (well within the hour window)

### Second Chrome profile
- Need a second Facebook account logged in
- CDP on port 9225 (Xvfb or similar headless setup)

### Key notes
- 25 of the 77 new groups are still pending Fred's join approval — scraper will skip them (few seconds each)
- Baseline file uses format: `[{"name": "...", "group_id": "...", "status": "active"}, ...]`
- Some groups are buy/swap/sell-heavy but all have community/noticeboard overlap worth scraping
