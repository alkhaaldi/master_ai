---
name: master-ai-dashboard-field
description: The full chain for adding or changing a field shown on a Master AI dashboard page. Use whenever a new value must reach an HTML dashboard page or a Home Assistant sensor - endpoint, JSON, configuration.yaml, sensor, page, verification.
---

## The chain - no step is optional

1. Endpoint change (Python, this agent).
2. Test the raw JSON before touching anything downstream.
3. If `json_attributes` needs the new key: report the exact
   edit needed in `configuration.yaml` and hand it to
   claude.ai. Do NOT edit HA YAML and do NOT restart HA.
4. Confirm the `sensor` state in HA actually carries the value.
   Never assume an entity_id - verify it.
5. HTML page change - NOT this agent. claude.ai owns HTML/CSS/JS.
   Stop here and report which page needs the edit.
6. Visual verification on the page.

Reference: `_tools/ADDING_NEW_DASHBOARD_FIELDS.md`
If that file and this skill ever disagree, the .md file wins and
this skill gets fixed.

## Truth order

API -> DB -> logs -> sensor states. The dashboard is never the
source of truth. If the page shows a value the endpoint cannot
produce, the page is lying.

## Data state rule

Four dashboard pages are on the data contract: swing, decisions,
positions, radar. The other 10 market-data pages carry the shared
`datastate-notice.js` banner saying they do not declare their
data state. If you put fresh data on one of those 10, either wire
it to the contract or leave the banner alone - do not quietly
remove the banner.

Known debt (do not "fix" by guessing): positions.html and
radar.html still run April logic and show P&L without
`pnl_valid` or `price_state`. See `_tools/OPEN_ITEMS.md`.
