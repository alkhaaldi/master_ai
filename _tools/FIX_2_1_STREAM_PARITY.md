# Fix 2.1 — Stream Handler Feature Parity Refactor
# Priority: Medium | Type: Refactor | Risk: Low (backward compatible)

## PROBLEM
`handle_chat_v7_stream()` is missing several features that `handle_chat_v7()` has:
- No world state snapshot injection
- No structured memory context injection
- No corrections learning loop context
- No memory search / auto-enrichment of user text
- No model selection via `choose_model()` (model stays None if not passed)
- No self-check / retry with Opus
- No corrections detection after response
- No session summary saving
- No trace logging

This means users get materially different (worse) answers depending on which handler is used.

## SOLUTION
Extract shared request preparation into a helper function `_prepare_chat_context()` used by BOTH handlers.
Then refactor both handlers to call this shared helper.

## EXECUTION PLAN

### Step 1: Create the shared helper function `_prepare_chat_context()`
**File:** `chat_v7.py`
**Where:** Insert BEFORE `handle_chat_v7()` function definition
**What:** New async function that does ALL prompt preparation:

```python
async def _prepare_chat_context(user_text, system_prompt, user_id):
    """Shared context preparation for both chat handlers.
    Returns (enriched_system_prompt, enriched_user_text, selected_model)."""

    # 1. Inject dynamic TODAY date + Islamic dates
    from datetime import datetime as _dt
    _today_str = _dt.now().strftime("TODAY: %A %d %B %Y, %H:%M Kuwait time")
    try:
        from brain_core import get_islamic_dates_context
        _islamic = get_islamic_dates_context()
    except Exception:
        _islamic = ""
    _dates_block = _today_str + chr(10) + _islamic
    _v7 = V8_SYSTEM_OVERRIDE.replace("{islamic_dates}", _dates_block)
    system_prompt = system_prompt + _v7

    # 2. World state snapshot
    try:
        from world_state import get_snapshot_text
        try:
            from world_state_delta import get_delta_text
            _delta = get_delta_text()
            _ws = _delta if _delta else get_snapshot_text()
        except ImportError:
            _ws = get_snapshot_text()
        if _ws:
            system_prompt = system_prompt + chr(10)*2 + _ws
    except Exception:
        pass

    # 3. Structured Memory context
    if _SMEM:
        try:
            _mem_ctx = smem.get_context_for_llm(user_text)
            if _mem_ctx:
                system_prompt = system_prompt + chr(10)*2 + _mem_ctx
        except Exception:
            pass

    # 4. Corrections Learning Loop context
    if _CORRECTIONS:
        try:
            _corr_ctx = _get_correction_context()
            if _corr_ctx:
                system_prompt = system_prompt + chr(10)*2 + _corr_ctx
                logger.info("Corrections context injected")
        except Exception:
            pass

    # 5. Model selection
    _tier = choose_model(user_text)
    model = MODEL_MAP.get(_tier, MODEL_MAP["sonnet"])
    logger.info(f"Model: {_tier} for: {user_text[:40]}")

    # 6. Apply stored corrections to user text
    enriched_text = user_text
    if _CORRECTIONS:
        try:
            _corrected_text, _applied = _apply_corrections(user_text)
            if _applied:
                logger.info(f"Applied {len(_applied)} corrections")
                enriched_text = _corrected_text
        except Exception:
            pass

    # 7. Auto-inject relevant memories
    try:
        from memory_db import search_memory_smart
        _mems = await search_memory_smart(enriched_text, limit=5)
        if _mems:
            _ml = [m["content"] for m in _mems if m.get("content")]
            if _ml:
                enriched_text = enriched_text + chr(10) + "[Memory: " + " | ".join(_ml[:5]) + "]"
                logger.info(f"Memory injected: {len(_ml)} items")
    except Exception:
        pass

    return system_prompt, enriched_text, model
```

### Step 2: Refactor `handle_chat_v7()` to use the helper
**File:** `chat_v7.py`
**What:** Replace the duplicated preparation code at the start of `handle_chat_v7()` with a single call:

Replace everything from:
```python
    # V7 override: force natural Arabic response, no JSON
    # Inject dynamic TODAY date + Islamic dates
    from datetime import datetime as _dt
    ...
```
Up to (but NOT including):
```python
    history.append({"role": "user", "content": _enriched})
```

With:
```python
    # Shared context preparation
    if model is None:
        system_prompt, _enriched, model = await _prepare_chat_context(user_text, system_prompt, user_id)
    else:
        system_prompt, _enriched, _ = await _prepare_chat_context(user_text, system_prompt, user_id)
```

### Step 3: Refactor `handle_chat_v7_stream()` to use the helper
**File:** `chat_v7.py`
**What:** Replace the minimal preparation at the start of `handle_chat_v7_stream()`:

Replace everything from:
```python
    # Inject dynamic TODAY date + Islamic dates
    from datetime import datetime as _dt
    ...
    system_prompt = system_prompt + _v7
```

With:
```python
    # Shared context preparation (same as non-stream handler)
    if model is None:
        system_prompt, user_text, model = await _prepare_chat_context(user_text, system_prompt, user_id)
    else:
        system_prompt, user_text, _ = await _prepare_chat_context(user_text, system_prompt, user_id)
```

### Step 4: Add post-response features to stream handler
**File:** `chat_v7.py`
**Area:** `handle_chat_v7_stream()` → after `end_turn` branch, after `history.append`
**What:** Add session save + corrections detection + trace logging (copy from non-stream handler):

After `history.append({"role": "assistant", "content": final})` in the stream handler, add:
```python
            # Auto-save session context if complex interaction (3+ tools)
            if len(tools_used) >= 3:
                try:
                    from memory_db import save_memory_with_facts
                    _summary = f"Session {time.strftime('%Y-%m-%d %H:%M')}: User asked '{user_text[:60]}', used tools: {', '.join(set(tools_used))}"
                    await save_memory_with_facts("session_log", _summary, user_id)
                except Exception:
                    pass

            # Corrections detection
            if _CORRECTIONS:
                try:
                    _prev_ai = history[-2]['content'] if len(history) >= 2 else ''
                    _corr = _process_correction(user_text, _prev_ai)
                    if _corr:
                        logger.info(f"Correction detected (stream): {_corr.get('wrong','')} -> {_corr.get('right','')}")
                except Exception:
                    pass

            # Trace logging
            if _PLANNER:
                try:
                    _intent = classify_intent(user_text)
                    save_trace({"msg_id": str(int(time.time()*1000)), "user_text": user_text,
                                "intent_type": _intent["type"], "compound": _intent["compound"],
                                "model": model or "", "tools_used": list(set(tools_used)),
                                "tools_count": len(tools_used), "self_check_ok": True,
                                "final_status": "ok", "response_len": len(final),
                                "elapsed_ms": round((time.time()-t0)*1000, 1), "user_id": user_id})
                except Exception:
                    pass
```

## VALIDATION AFTER EACH STEP
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
```

## FINAL VALIDATION
```bash
python3 _tools/quick_check.py
python3 _tools/smoke_test.py
python3 _tools/db_sanity.py
git add -A && git commit -m "refactor: extract _prepare_chat_context() — stream handler parity (Fix 2.1)"
bash _tools/restart_master_ai.sh
```

## RULES
- ALL edits via `_tools/patchers/apply_text_patch.py`
- Do NOT rewrite the entire file — use targeted patches
- Preserve all existing behavior in `handle_chat_v7()` — only extract, don't change logic
- The helper must be backward compatible — if any import fails, it should gracefully skip
- Test after EACH step before moving to next
