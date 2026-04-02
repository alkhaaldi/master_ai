"""
KAIROS — Background health agent.
Monitors service health, sends alerts, auto-recovers where possible.
Gated by ff.is_enabled("kairos").
"""
import gc
import time
import asyncio
import sqlite3
import shutil
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("kairos")

# Kuwait market hours: Sun-Thu 9:00-13:30 (+03:00)
_KWT = timezone(timedelta(hours=3))
_MARKET_DAYS = {6, 0, 1, 2, 3}  # Sun=6, Mon=0, Tue=1, Wed=2, Thu=3


def _is_market_hours() -> bool:
    now = datetime.now(_KWT)
    if now.weekday() not in _MARKET_DAYS:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 <= t <= 13 * 60 + 30


class TelegramQueue:
    """Offline message buffer — stores failed TG messages, flushes on recovery."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS telegram_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                parse_mode TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                sent INTEGER DEFAULT 0,
                sent_at TEXT
            )""")
            c.commit()

    def enqueue(self, chat_id: int, message: str, parse_mode: str = ""):
        with self._conn() as c:
            c.execute(
                "INSERT INTO telegram_queue (chat_id, message, parse_mode) VALUES (?, ?, ?)",
                (chat_id, message, parse_mode or ""),
            )
            c.commit()
        logger.info("TG message queued for chat_id=%s (%d chars)", chat_id, len(message))

    def pending_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM telegram_queue WHERE sent=0").fetchone()[0]

    def get_pending(self, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, chat_id, message, parse_mode FROM telegram_queue WHERE sent=0 ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"id": r[0], "chat_id": r[1], "message": r[2], "parse_mode": r[3]} for r in rows]

    def mark_sent(self, msg_id: int):
        with self._conn() as c:
            c.execute(
                "UPDATE telegram_queue SET sent=1, sent_at=datetime('now') WHERE id=?",
                (msg_id,),
            )
            c.commit()

    def cleanup(self, hours: int = 24):
        """Delete sent messages older than N hours."""
        with self._conn() as c:
            c.execute(
                "DELETE FROM telegram_queue WHERE sent=1 AND sent_at < datetime('now', ?)",
                (f"-{hours} hours",),
            )
            c.commit()


class KairosAgent:
    """Background health agent — checks every 5 min, alerts via Telegram."""

    def __init__(self, health_hub, ff, tg_send_fn, db_path: str = None,
                 cb_ha=None, cb_llm=None, cb_tg=None):
        self._health = health_hub
        self._ff = ff
        self._tg_send = tg_send_fn
        self._db_path = db_path or "data/life.db"
        self._cb_ha = cb_ha
        self._cb_llm = cb_llm
        self._cb_tg = cb_tg
        self._tg_queue = TelegramQueue(self._db_path)
        self._running = False
        self._checks = 0
        self._alerts_sent = 0
        self._auto_fixes = 0
        self._started_at = None
        self._last_check = None
        self._previous_down = set()
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS kairos_alerts (
                alert_key TEXT PRIMARY KEY,
                last_sent TEXT,
                count INTEGER DEFAULT 1,
                resolved INTEGER DEFAULT 0
            )""")
            c.execute("""CREATE TABLE IF NOT EXISTS kairos_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                service TEXT,
                result TEXT,
                detail TEXT
            )""")
            c.commit()

    def _log_action(self, action: str, service: str = None, result: str = None, detail: str = None):
        try:
            with self._conn() as c:
                c.execute(
                    "INSERT INTO kairos_log (action, service, result, detail) VALUES (?, ?, ?, ?)",
                    (action, service, result, detail),
                )
                c.commit()
        except Exception as e:
            logger.error("kairos_log write error: %s", e)

    def _can_alert(self, alert_key: str, cooldown_min: int = 60) -> bool:
        """Dedup: don't re-send same alert within cooldown."""
        try:
            with self._conn() as c:
                row = c.execute(
                    "SELECT last_sent FROM kairos_alerts WHERE alert_key=? AND resolved=0",
                    (alert_key,),
                ).fetchone()
            if not row:
                return True
            last = datetime.fromisoformat(row[0])
            return (datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)).total_seconds() > cooldown_min * 60
        except Exception:
            return True

    def _record_alert(self, alert_key: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                """INSERT INTO kairos_alerts (alert_key, last_sent, count, resolved)
                   VALUES (?, ?, 1, 0)
                   ON CONFLICT(alert_key) DO UPDATE SET last_sent=?, count=count+1, resolved=0""",
                (alert_key, now, now),
            )
            c.commit()

    def _resolve_alert(self, alert_key: str):
        with self._conn() as c:
            c.execute("UPDATE kairos_alerts SET resolved=1 WHERE alert_key=?", (alert_key,))
            c.commit()

    @property
    def tg_queue(self) -> TelegramQueue:
        return self._tg_queue

    # ── Main loop ────────────────────────────────────────
    async def start(self):
        self._running = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        logger.info("KAIROS agent started")
        self._log_action("start", result="ok")
        await asyncio.sleep(60)  # let services initialize
        while self._running:
            try:
                if self._ff.is_enabled("kairos"):
                    await self._check_cycle()
            except Exception as e:
                logger.error("KAIROS cycle error: %s", e)
                self._log_action("error", detail=str(e))
            await asyncio.sleep(300)  # 5 min

    async def stop(self):
        self._running = False
        self._log_action("stop", result="ok")

    async def _check_cycle(self):
        self._checks += 1
        self._last_check = datetime.now(timezone.utc).isoformat()

        # 1. Sync health from circuit breakers
        bridge_st = None
        try:
            from bridge_client import BridgeClient, BRIDGE_BASE_URL
            client = BridgeClient(BRIDGE_BASE_URL)
            bridge_st = client.get_status()
        except Exception:
            pass
        last_b, last_g = None, None
        try:
            from news_engine import last_boursa_refresh, last_gemini_refresh
            last_b, last_g = last_boursa_refresh, last_gemini_refresh
        except Exception:
            pass
        summary = self._health.check_all(
            cb_ha=self._cb_ha, cb_llm=self._cb_llm, cb_tg=self._cb_tg,
            bridge_status=bridge_st,
            last_boursa=last_b, last_gemini=last_g,
        )

        current_down = set(summary["summary"]["down_services"])

        # 2. Detect recovered services
        recovered = self._previous_down - current_down
        for svc in recovered:
            alert_key = f"down_{svc}"
            self._resolve_alert(alert_key)
            msg = f"✅ {svc} رجع يشتغل"
            self._log_action("recovery", service=svc, result="ok")
            await self._send_alert(msg)

        # 3. Alert for down services (3+ consecutive failures)
        for svc_name in current_down:
            svc = summary["services"].get(svc_name, {})
            failures = svc.get("consecutive_failures", 0)
            if failures >= 3:
                alert_key = f"down_{svc_name}"
                if self._can_alert(alert_key):
                    reason = svc.get("reason", "unknown")
                    msg = f"⚠️ {svc_name} غير متاح — {reason}"
                    await self._send_alert(msg)
                    self._record_alert(alert_key)
                    self._log_action("alert", service=svc_name, result="sent", detail=reason)

        self._previous_down = current_down

        # 4. Special: daily_snapshot stale during market hours
        ds = summary["services"].get("daily_snapshot", {})
        if ds.get("status") == "down" and _is_market_hours():
            age_h = ds.get("details", {}).get("age_hours", 0)
            if age_h > 2 and self._can_alert("stale_snapshot", cooldown_min=120):
                self._log_action("auto_refresh", service="daily_snapshot", detail=f"stale {age_h:.1f}h")
                self._record_alert("stale_snapshot")
                self._auto_fixes += 1
                await self._send_alert(f"🔄 Daily snapshot قديم ({age_h:.1f}h) — محتاج refresh")

        # 5. System checks
        await self._check_system_resources()

        # 6. Flush telegram queue if TG is up
        if "telegram" not in current_down and self._ff.is_enabled("telegram_queue"):
            await self._flush_tg_queue()

        # 7. Cleanup old data
        if self._checks % 12 == 0:  # every hour
            self._tg_queue.cleanup(24)
            self._cleanup_old_logs(days=7)

    async def _check_system_resources(self):
        try:
            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            if mem.percent > 80:
                if self._can_alert("high_memory", cooldown_min=60):
                    gc.collect()
                    self._log_action("gc_collect", result="ok", detail=f"mem={mem.percent}%")
                    self._record_alert("high_memory")
                    self._auto_fixes += 1
                    await self._send_alert(f"🧹 Memory {mem.percent}% — gc.collect() تم")
            if disk.percent > 85:
                if self._can_alert("high_disk", cooldown_min=360):
                    self._record_alert("high_disk")
                    await self._send_alert(f"💾 Disk {disk.percent}% — تحتاج تنظيف")
        except ImportError:
            pass  # psutil not installed
        except Exception as e:
            logger.debug("System resource check error: %s", e)

    async def _send_alert(self, msg: str):
        admin_id = None
        try:
            import os
            admin_id = os.getenv("ADMIN_TELEGRAM_ID") or "669769765"
        except Exception:
            admin_id = "669769765"
        try:
            # No parse_mode — alerts contain service names with underscores
            ok = await self._tg_send(int(admin_id), msg)
            if ok:
                self._alerts_sent += 1
            elif self._ff.is_enabled("telegram_queue"):
                self._tg_queue.enqueue(int(admin_id), msg, parse_mode="")
        except Exception as e:
            logger.error("KAIROS alert send error: %s", e)
            if self._ff.is_enabled("telegram_queue"):
                self._tg_queue.enqueue(int(admin_id or 669769765), msg, parse_mode="")

    async def _flush_tg_queue(self):
        pending = self._tg_queue.get_pending(limit=20)
        if not pending:
            return
        self._log_action("queue_flush", detail=f"{len(pending)} messages")
        flushed = 0
        for msg in pending:
            try:
                _pm = msg["parse_mode"] if msg["parse_mode"] else None
                ok = await self._tg_send(msg["chat_id"], msg["message"], parse_mode=_pm)
                if ok:
                    self._tg_queue.mark_sent(msg["id"])
                    flushed += 1
                else:
                    break  # TG still down
            except Exception:
                break
            await asyncio.sleep(1)  # rate limit
        if flushed:
            self._log_action("queue_flushed", result="ok", detail=f"{flushed}/{len(pending)}")

    def _cleanup_old_logs(self, days: int = 7):
        try:
            with self._conn() as c:
                c.execute(
                    "DELETE FROM kairos_log WHERE timestamp < datetime('now', ?)",
                    (f"-{days} days",),
                )
                c.commit()
        except Exception:
            pass

    # ── Status / TG command ──────────────────────────────
    def get_status(self) -> dict:
        return {
            "enabled": self._ff.is_enabled("kairos"),
            "running": self._running,
            "started_at": self._started_at,
            "last_check": self._last_check,
            "total_checks": self._checks,
            "alerts_sent": self._alerts_sent,
            "auto_fixes": self._auto_fixes,
            "tg_queue_pending": self._tg_queue.pending_count(),
            "current_down": list(self._previous_down),
        }

    def get_log(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT timestamp, action, service, result, detail FROM kairos_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"timestamp": r[0], "action": r[1], "service": r[2], "result": r[3], "detail": r[4]}
            for r in rows
        ]

    def format_tg_status(self) -> str:
        """Plain text — no Markdown (service names contain underscores)."""
        s = self.get_status()
        if not s["enabled"]:
            return "🤖 KAIROS: معطّل\nشغّله من الداشبورد أو API"
        lines = [
            "🤖 KAIROS Agent",
            f"📊 Checks: {s['total_checks']}",
            f"🔔 Alerts: {s['alerts_sent']}",
            f"🔧 Auto-fixes: {s['auto_fixes']}",
            f"📬 Queue: {s['tg_queue_pending']} pending",
        ]
        if s["current_down"]:
            down = ", ".join(d.replace("_", " ") for d in s["current_down"])
            lines.append(f"🔴 Down: {down}")
        else:
            lines.append("🟢 All services OK")
        if s["last_check"]:
            lines.append(f"⏰ Last: {s['last_check'][:19]}")
        return "\n".join(lines)
