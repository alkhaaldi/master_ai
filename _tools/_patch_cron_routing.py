"""Patch server.py to add cron handler routing with orphan cleanup (Tier2 #13)."""
import sys

FILE = "/home/pi/master_ai/server.py"
with open(FILE) as f:
    content = f.read()

# Find a good insertion point — before the telegram_polling_loop
marker = "async def _send_progress_after_delay("
idx = content.find(marker)
if idx < 0:
    print("Could not find _send_progress_after_delay")
    sys.exit(1)

cron_code = '''
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRON HANDLER ROUTING + ORPHAN CLEANUP (Tier2 #13)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCHEDULED_HANDLERS = {}
_cron_breakers = {}


def register_scheduled_handler(task_name: str, handler):
    """Register a handler for a scheduled task name."""
    _SCHEDULED_HANDLERS[task_name] = handler
    logger.info("Registered scheduled handler: %s", task_name)


async def fire_scheduled_task(task_name: str, **kwargs):
    """Route a scheduled task fire to its handler.
    If handler missing or fails 3 times consecutively, skip."""
    handler = _SCHEDULED_HANDLERS.get(task_name)
    if handler is None:
        logger.warning("Orphaned scheduled task: %s — no handler registered", task_name)
        return

    from circuit_breaker import CircuitBreaker
    if task_name not in _cron_breakers:
        _cron_breakers[task_name] = CircuitBreaker(
            name=f"cron_{task_name}", failure_threshold=3, cooldown_seconds=300
        )
    breaker = _cron_breakers[task_name]

    if not breaker.allow_request():
        logger.warning("Cron %s circuit open — skipping", task_name)
        return

    try:
        if asyncio.iscoroutinefunction(handler):
            await handler(**kwargs)
        else:
            handler(**kwargs)
        breaker.record_success()
    except Exception as e:
        breaker.record_failure()
        logger.error("Cron %s failed: %s", task_name, e)


'''

content = content[:idx] + cron_code + content[idx:]

with open(FILE, "w") as f:
    f.write(content)

print("PATCHED server.py with cron routing OK")
