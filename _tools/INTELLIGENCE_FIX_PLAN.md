# Master AI Intelligence Fixes — Plan for Claude Code
# Generated from ChatGPT GPT-4o code audit patches (Batch 1 + Batch 2)
# Date: 2026-03-25

## CONTEXT
- ChatGPT reviewed 11 intelligence/decision-making files and found 47 issues
- These patches fix CRITICAL + HIGH issues only (27 fixes)
- All fixes must use patch system: `_tools/patchers/apply_text_patch.py`
- After each file: `python3 _tools/quick_check.py`
- After all: `python3 _tools/smoke_test.py` + `python3 _tools/db_sanity.py` + git commit + restart

## IMPORTANT NOTES FOR CLAUDE CODE
- ChatGPT's patches are APPROXIMATE — the search strings may not be exact.
- You MUST read the actual file first, find the matching code area, then apply a correct patch.
- If a search string doesn't match exactly, find the closest matching code and adapt.
- Some patches are too broad (e.g. "replace all hit_count with use_count") — apply surgically.
- DO NOT blindly search-and-replace across entire files.

---

## BATCH 1: tg_intent_router.py, confidence_engine.py, corrections_loop.py, self_check.py, mini_planner.py

### Fix 1 — CRITICAL: tg_intent_router.py — ACTION_VERBS duplicate keys
**Problem:** Python dict duplicate keys — "حط" and "خل" appear twice, later entry overwrites earlier.
Brightness intent routing breaks because these keys become set_temp only.
**Fix:** Restructure ACTION_VERBS so each verb maps to a BASE action (on/off/set_value/increase/decrease).
Then resolve the actual HA service by combining action + domain context (light→brightness, climate→temperature).
DO NOT just rename keys — redesign the mapping to avoid duplicates.

### Fix 2 — CRITICAL: tg_intent_router.py — alias fast path returns tuple as text
**Problem:** `_ha_call()` returns `(success, detail)` tuple, but alias path puts raw tuple into `"text"` field.
**Fix:** Unpack the tuple:
```python
_ok, _detail = await _ha_call(_alias_eid, _act)
if _ok:
    return {"text": f"✅ {_detail}", "entities": [_alias_eid], "action": _act, "source": "alias"}
else:
    return {"text": f"❌ {_detail}", "entities": [_alias_eid], "action": _act, "source": "alias", "error": True}
```

### Fix 3 — CRITICAL: confidence_engine.py — overconfident scoring + climate hard block
**Problem:** Climate >23 only gets -0.1 penalty. Should be hard block per house rules.
Also general scoring too generous (0.8 for incomplete calls).
**Fix:** For climate with temp > 23:
```python
if d == "climate" and t is not None and t > 23:
    return {"score": 0.05, "level": "low", "notes": ["temp_above_23_hard_block"]}
```

### Fix 4 — CRITICAL: corrections_loop.py — blind substring replacement
**Problem:** `apply_corrections()` does `re.sub(re.escape(wrong), right, ...)` on full user text — can break words.
**Fix:** Add word boundary matching:
```python
corrected = re.sub(r'\b' + re.escape(wrong) + r'\b', right, corrected, flags=re.IGNORECASE)
```
Also: only apply corrections with confidence >= 0.7.

### Fix 5 — CRITICAL: corrections_loop.py — times_applied inflated
**Problem:** `times_applied` incremented on every save, not on actual application.
**Fix:** Remove the increment from the save/update path. Only increment in `apply_corrections()` when a correction is actually used.

### Fix 6 — CRITICAL: corrections_loop.py — _extract_wrong returns garbage
**Problem:** Always returns "unknown" or "previous_response" placeholder.
**Fix:** If wrong value cannot be extracted, return None and abort the correction save:
```python
def _extract_wrong_from_context(text, context):
    # ... existing logic ...
    wrong = ...
    if wrong in ("unknown", "previous_response", ""):
        return None  # Cannot determine what was wrong — don't save garbage
    return wrong
```
Then in the caller, check for None before saving.

### Fix 7 — HIGH: tg_intent_router.py — _ha_call() no HTTP status check
**Problem:** Never validates HTTP response status. Reports success even when HA rejects the call.
**Fix:** After `await c.post(...)`:
```python
r = await c.post(url, headers=headers, json=data)
if r.status_code not in (200, 201):
    return False, f"HA error {r.status_code}"
```

### Fix 8 — HIGH: tg_intent_router.py — unsupported actions classified but not executable
**Problem:** Actions like brightness/dim/increase/decrease are classified but _ha_call() doesn't handle them.
**Fix:** Either add support in _ha_call() for brightness (light.turn_on with brightness_pct) and increase/decrease,
OR remove these from ACTION_VERBS so they fall through to LLM.
Recommended: Add basic brightness support:
```python
if action == "set_brightness" and domain == "light":
    svc = "turn_on"
    data["brightness_pct"] = value  # extracted from user text
```

### Fix 9 — HIGH: self_check.py — string-scan tool success detection
**Problem:** Uses `'"error"' not in str(r)[:100]` to detect success.
**Fix:** Use structured check:
```python
has_success = any(
    r and (
        (isinstance(r, dict) and not r.get("error")) or
        (isinstance(r, str) and '"error"' not in r[:200])
    )
    for r in tool_results
)
```

### Fix 10 — HIGH: self_check.py — only saves failures
**Problem:** `save_tool_outcomes()` only records failures, not successes. AI can't learn what works.
**Fix:** Add success recording:
```python
if success:
    # Save success pattern
    try:
        from structured_memory import save_lesson
        save_lesson(f"Tool {tool_name} succeeded for '{user_text[:50]}'", category="tool_success")
    except Exception:
        pass
```

### Fix 11 — HIGH: mini_planner.py — decompose splits on " و " 
**Problem:** Arabic conjunction "و" appears in normal phrases, causing over-decomposition.
**Fix:** Remove " و " from split separators, keep only explicit sequence words:
```python
for sep in [" ثم ", " وبعدين ", " بعدها "]:  # removed " و "
```

### Fix 12 — HIGH: mini_planner.py — classify_intent keyword overlap
**Problem:** Same keywords appear in multiple intent categories. Simple count-based scoring picks wrong intent.
**Fix:** Use word-level matching instead of substring, and add precedence rules:
- If imperative verb present → action first
- If "ليش/لماذا/كيف" → reasoning
- Status/query words → retrieval only if no action verb

---

## BATCH 2: brain_core.py, quick_query.py, smart_router.py, smart_tools.py, exec_policy.py, memory_db.py

### Fix 13 — HIGH: brain_core.py — reload() swallows errors
**Problem:** `except Exception: pass` hides init failures.
**Fix:** Replace with:
```python
except Exception as e:
    logger.error(f"Brain reload failed: {e}")
```

### Fix 14 — HIGH: brain_core.py — naive substring alias matching
**Problem:** Short aliases match inside unrelated words.
**Fix:** Use word boundary regex:
```python
if content and re.search(r'\b' + re.escape(content.lower()) + r'\b', text.lower()):
```

### Fix 15 — HIGH: brain_core.py — hit_count vs use_count schema mismatch
**Problem:** Code uses `hit_count` and `hits` but DB schema has `use_count`.
**Fix:** Replace `hit_count` and `hits` with `use_count` in get_relevant_memories() and related functions.
Be surgical — only change the column references, not variable names.

### Fix 16 — HIGH: brain_core.py — dual DB paths
**Problem:** `AUDIT_DB` and `_AUDIT_DB` may point to different paths.
**Fix:** Remove `_AUDIT_DB` and use `AUDIT_DB` everywhere. Or vice versa — pick one canonical path.

### Fix 17 — HIGH: brain_core.py — auto_learn() is placebo
**Problem:** Only logs one summary row, doesn't actually learn patterns.
**Fix:** Add deprecation marker and TODO. Don't remove (backward compatible) but add comment:
```python
def auto_learn(query, response, actions=None):
    """DEPRECATED: Placeholder only. Real learning happens via corrections_loop and structured_memory."""
    # TODO: Implement actual pattern extraction or remove
    ...
```

### Fix 18 — HIGH: quick_query.py — shift tuple unpacking crash
**Problem:** `s, emoji, _ = _get_shift(d)` but function returns 4 values.
**Fix:** `s, emoji, times, pos = _get_shift(d)` or `s, emoji, *_ = _get_shift(d)`

### Fix 19 — HIGH: quick_query.py — _H_MO possibly undefined
**Problem:** Referenced but may not be defined/imported.
**Fix:** Ensure `_H_MO` is defined at module level or imported. If it's a Hijri month mapping, add:
```python
_H_MO = {1: "محرم", 2: "صفر", 3: "ربيع الأول", ...}
```
Or import from the module that defines it.

### Fix 20 — HIGH: quick_query.py — greeting interpolates tuple
**Problem:** `f"شفتك اليوم {_s}"` where `_s` is a tuple.
**Fix:** `f"شفتك اليوم {_s[0]}"` or unpack properly.

### Fix 21 — HIGH: quick_query.py — Bluesound uses HA media_player
**Problem:** Uses `media_player.*` HA services for Bluesound. Should use Music Assistant only.
**Fix:** For Bluesound entities (office_1_2, office_2_2, room_3_2, ground_floor):
- Volume: OK via HA media_player.volume_set
- Playback/queue/media: Must use music_assistant.play_media on LEADER only
Add a check before media commands:
```python
_BLUESOUND_IDS = {"media_player.office_1_2", "media_player.office_2_2", "media_player.room_3_2", "media_player.ground_floor"}
_BLUESOUND_LEADER = "media_player.office_1_2"
if entity_id in _BLUESOUND_IDS and action not in ("volume_set", "volume_up", "volume_down"):
    entity_id = _BLUESOUND_LEADER
    domain = "music_assistant"
```

### Fix 22 — HIGH: smart_router.py — action classification too broad
**Problem:** Device nouns like "درجة", "حرارة", "مكيف" alone trigger action classification.
**Fix:** Require imperative verb + target, not just device noun:
```python
if kw in t and len(t.split()) > 1 and any(v in t for v in _IMPERATIVE_VERBS):
    return "action"
```

### Fix 23 — HIGH: smart_tools.py — _find_room() only handles dict
**Problem:** entity_map rooms can be list of strings, not just dicts.
**Fix:**
```python
if isinstance(room_data, (dict, list)):
    if isinstance(room_data, list):
        # Handle list of "entity=name" strings
        entities = []
        for item in room_data:
            if "=" in item:
                eid, name = item.split("=", 1)
                entities.append({"entity_id": eid.strip(), "name": name.strip()})
        room_data = {"entities": entities}
    # ... continue with dict handling
```

### Fix 24 — HIGH: exec_policy.py — shared mutable state no locking
**Problem:** `_outcomes` and `_session_tools` modified concurrently without protection.
**Fix:** Add threading.Lock:
```python
import threading
_outcomes_lock = threading.Lock()

def record_outcome(tool_name, result):
    with _outcomes_lock:
        # ... existing logic
```

### Fix 25 — MEDIUM: memory_db.py — positional args fragile
**Problem:** `add_memory()` called with positional args that could break if signature changes.
**Fix:** Use named parameters:
```python
await add_memory(category=category, type_="user_stated", content=content, source=source)
```

### Fix 26 — MEDIUM: memory_db.py — extract_facts() too narrow
**Problem:** Only catches one birth date pattern with `(\w+)` which is fragile for Arabic.
**Fix:** Add more patterns:
```python
_FACT_PATTERNS = [
    (r'([\u0600-\u06FF]+)\s+(?:مواليد|انولد|ولد)\s+(\d{4}[-/]\d{2}[-/]\d{2})', 'birth_date'),
    (r'(?:ميلاد|عيد ميلاد)\s+([\u0600-\u06FF]+)\s+(\d{1,2}[-/]\d{1,2})', 'birthday'),
    (r'([\u0600-\u06FF]+)\s+(?:زوجتي|زوجي|ابني|بنتي|أمي|أبوي)', 'family_relation'),
]
```

---

## EXECUTION ORDER
```
1. Read dev context: fetch https://ai.salem-home.com/dev/context
2. Read _tools/OPERATIONAL_ACCESS_MATRIX.md

Phase 1 — CRITICAL (Fixes 1-6):
3. Fix 1: tg_intent_router.py — ACTION_VERBS restructure
4. Fix 2: tg_intent_router.py — alias tuple unpack
5. Fix 3: confidence_engine.py — climate hard block
6. Fix 4: corrections_loop.py — word boundary
7. Fix 5: corrections_loop.py — times_applied
8. Fix 6: corrections_loop.py — extract_wrong None
9. Run: quick_check + smoke_test

Phase 2 — HIGH (Fixes 7-24):
10. Fix 7: tg_intent_router.py — HTTP status check
11. Fix 8: tg_intent_router.py — brightness support OR remove
12. Fix 9-10: self_check.py — structured check + success saving
13. Fix 11-12: mini_planner.py — decompose + classify
14. Fix 13-17: brain_core.py — all 5 fixes
15. Fix 18-21: quick_query.py — all 4 fixes
16. Fix 22: smart_router.py — action classification
17. Fix 23: smart_tools.py — room format
18. Fix 24: exec_policy.py — locking
19. Run: quick_check + smoke_test

Phase 3 — MEDIUM (Fixes 25-26):
20. Fix 25-26: memory_db.py
21. Run: quick_check + smoke_test + db_sanity

Final:
22. Git commit: "fix: intelligence audit — 26 fixes across 11 files"
23. Restart: bash _tools/restart_master_ai.sh
```

## RULES
- ALL Python edits via `_tools/patchers/apply_text_patch.py`
- Read each file FIRST before patching — ChatGPT's search strings are approximate
- Find the actual matching code, then apply the fix
- NO direct file overwrites, NO append
- Each fix = one patch, then verify syntax
- Backward compatible — no breaking changes
- If any fix fails validation, stop and report
