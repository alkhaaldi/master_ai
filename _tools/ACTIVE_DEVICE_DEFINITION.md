# ACTIVE DEVICE — what `active_devices_count` counts, in words

- Written 2026-08-18, when the field was first shipped on `/dashboard`.
  Before that both `home.html` and `home-control.html` read it with `|| 0`
  and no endpoint shipped it, so both pages had always said "0 جهاز نشط".
- **Every state vocabulary below is MEASURED against the live HA instance on
  2026-08-18 07:30 Kuwait**, not read from a docs page. Where a rule cannot
  answer, that is written down rather than resolved by a plausible guess.
- Rule this file exists to enforce: *a count is a claim about the world, and
  a reader who cannot say which things were counted cannot check it.* The
  same shape as `_tools/SCALES.md` — an unlabelled number is the defect.

---

## The rule as shipped

`dashboard_api.py`, inside `/dashboard`, computed from the `/api/states`
fetch that endpoint already performs. No extra HTTP call.

```
active = (entities in light · switch · fan · climate · media_player
          whose state ∈ {on, playing, open, heat, cool, auto, heat_cool, fan_only}
          and whose entity_id does not contain "backlight")
       + (cover entities whose id contains "_inverted" and whose state == "closed")
```

`-1` when HA could not be read — never `0`. Both pages render `-1` as `--`.
Proved on the wire 2026-08-18: token removed → `-1` on all four home fields,
token restored → real counts return. A zero would have said "the house is
asleep" when it meant "we could not ask".

---

## Type by type, and the awkward cases spelled out

### light — counted when `on`
157 entities: `on` 11 · `off` 134 · `unavailable` 12.

`unavailable` is NOT counted. It means the light did not answer, which is not
the same as off, but a count cannot express "unknown" — so it is excluded and
this line is the record of that choice.

**Backlights are excluded by name.** Any `entity_id` containing `backlight` is
skipped: they are decorative strips that follow other devices, and counting
them made the number track the TV rather than the house. 11 lights are `on`,
8 are counted, so 3 are backlights.

**Brightness is not consulted.** A light at 1% is counted the same as one at
100%. `on` is `on`.

### switch — counted when `on`
297 entities: `on` 20 · `off` 159 · `unavailable` 114 · `unknown` 4.

**This is the largest single contributor and the least trustworthy.** Switches
in this house include appliance sockets a person turns on and infrastructure
that is on permanently — a router socket and a bedroom lamp are the same
`switch.x` with the same `on`. 114 `unavailable` is also the largest unknown
block of any domain.

Nothing distinguishes them today. If the number ever needs to mean "things the
household is using", switches need a whitelist or an area filter, and that is
a decision, not a fix.

### fan — counted when `on`
15 entities: `on` 1 · `off` 14. No speed threshold; `on` at any speed counts.

### climate (AC) — counted when `heat`, `cool`, `auto`, `heat_cool` or `fan_only`
8 entities, **all 8 currently report `unknown`, and `hvac_action` is `None` on
every one of them.**

So the answer to "does an AC on standby count?" is not the interesting one:
**the climate rule has never fired and cannot fire in this house's current
state.** `home_ac_on` is 0 for the same reason, and it is 0 because nothing is
measurable, not because nothing is running.

Had the states been readable the intent is: `off` does not count, and an AC
idling inside a mode (`hvac_action: idle` while `state: cool` — thermostat
satisfied, compressor resting) DOES count, because the household has asked
for cooling and the machine is committed to it. That intent is untested here.

**This is the honest gap in the count.** Worth its own item: either the
climate integration is broken or these are stale entities that should be
removed.

### media_player — counted only when `playing`
26 entities: `idle` 10 · `off` 7 · `unavailable` 5 · `playing` 4.

**`idle` does NOT count.** A TV showing a home screen and an Alexa waiting for
a wake word are both `idle`; counting them would make the number report
"devices with power" rather than "devices in use". `paused` does not appear in
this house today; by the same reasoning it would not count.

**Virtual entities are counted if they play.** `media_player.everywhere`,
`this_device`, `none`, `ground_floor` are groups and targets, not hardware.
`ground_floor` is `playing` right now and is being counted, so a single speaker
playing through a group can add two to the total. Not fixed here; recorded.

### cover (shutters) — counted from the `_inverted` entities only
28 entities, and they are **two views of ~14 physical shutters**:

```
cover.living_room_left_shutter_curtain    state=closed  pos=0     <- raw device
cover.living_room_left_shutter_inverted   state=open    pos=100   <- corrected
```

`covers_inverted.yaml` builds each `_inverted` entity as
`position = 100 - state_attr(raw, 'current_position')`. It exists because the
hardware reports backwards, and its header records that the automations and
scenes use the `_inverted` ids.

**Counting the cover domain plainly would double-count**, and would be right
only while the two views happen to mirror each other. So the count takes one
entity per shutter, matching the rule `home_covers_open` uses four lines above.

Two things this rule does not handle, both stated rather than fixed:

1. **The pairing is not 1:1.** `cover.curtain_switch_wifi_ble_8_curtain` has no
   `_inverted` twin and is therefore invisible to this count for ever;
   `cover.room_1_shutter_inverted` and `cover.room_5_shutter_inverted` have no
   raw twin; `cover.men_window_shutter_curtain_2` is a second raw entity for
   one window. 14 and 14 is a coincidence of totals, not a pairing.
2. **A half-open shutter counts as fully open.** Position is read as a state,
   not a percentage: `open` at position 30 and `open` at position 100 are the
   same to this count. `opening` and `closing` do not appear in the sampled
   states and would not be counted.

### Never counted, in any domain
`unavailable` · `unknown` · `off` · `idle` · `standby` · `closed` (a cover that
is shut) · anything whose entity_id contains `backlight` · every domain outside
the six above (`sensor`, `binary_sensor`, `automation`, `script`, `person`,
`device_tracker`, …). A motion sensor detecting motion is not an active device.

---

## OPEN — the direction of the shutter count

`dashboard_api.py:285-286` counts `_inverted == "closed"` and names the result
`home_covers_open`. But `covers_inverted.yaml` defines `_inverted` as the
CORRECTED view, so `_inverted == "open"` should be the shutter that is open.

Measured 2026-08-18 07:30: the `_inverted` entities report **6 open, 8 closed**,
while `/dashboard` reports `home_covers_open: 8`.

If the template is the corrected view — which is what the file says it is for —
then `home_covers_open` has been reporting the count of CLOSED shutters, on
both `home.html` and `home-control.html`, and `active_devices_count` inherited
the same direction on the day it was shipped.

This is a claim about the physical house and one glance out of a window settles
it. It is left as measured, not flipped on a deduction, because a wrong flip
inverts a number on two pages instead of one.

---

## Two definitions for one fact — NOT resolved

`quick_query._active_devices_count()` (the Telegram path, reached by
"شنو شغال بالبيت") uses the same domains and the same on-states, but counts
covers **plainly** — every `cover.*` in state `open`, both views, no `_inverted`
handling. It also returns a formatted Arabic string, not a number.

So the page and the bot answer the same question with two rules. They agree
today only when the two cover views happen to mirror each other. Tracked in
`OPEN_ITEMS`; until they are unified, a disagreement between the page and the
bot is expected and is not evidence of a bug in either.
