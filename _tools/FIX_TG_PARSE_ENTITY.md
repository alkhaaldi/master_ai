# Fix: Telegram 400 Bad Request — Parse Entity Error
# Date: 2026-04-03
# Priority: HIGH — TG alerts failing silently

## Problem
Telegram sendMessage returns 400 with:
"Bad Request: can't parse entities: Can't find end of the entity starting at byte offset 11"

This means outgoing messages (KAIROS alerts, radar signals, anomaly reports) have
broken HTML/Markdown entities — an unclosed tag or malformed formatting.

## Where to look
1. grep for ALL tg_send calls that use parse_mode
2. Check the message formatting in:
   - KAIROS alerts (kairos.py → tg_send with health status messages)
   - Radar signal alerts (stock_radar.py → tg_send with stock data)
   - Anomaly reports (server.py → anomaly detection messages)
   - Circuit breaker notifications (new integration — may have bad formatting)

## How to fix
Option A (safest): Strip parse_mode entirely — send as plain text:
```python
# Change ALL tg_send calls from:
tg_send(chat_id, message, parse_mode="HTML")
# To:
tg_send(chat_id, message)  # plain text, no parse_mode
```

Option B (better UX): Wrap with try/except and fallback to plain text:
```python
async def tg_send_safe(chat_id, text, parse_mode="HTML"):
    try:
        await tg_send(chat_id, text, parse_mode=parse_mode)
    except Exception:
        # Fallback: strip HTML tags and send plain
        import re
        plain = re.sub(r'<[^>]+>', '', text)
        await tg_send(chat_id, plain)
```

Option C (root cause): Find the specific message with the broken entity at byte offset 11
and fix the formatting. Could be a `<b>` without `</b>`, or `*` without closing `*`.

## Also check
- intent_audit table has 0 rows — verify that tg_intent_router integration is actually
  being called when messages come in. The wiring may need the handler to be registered.
- session_summaries table — check if it exists and is being written to
- auto_memory_extractor — check if record_message is being called

## Test after fix
1. Send a message to the bot: "test"
2. Check server.log for: intent_audit, session_memory, auto_memory
3. Check /api/intent-analytics returns count > 0
4. Check /api/memory-extraction/stats returns today > 0
