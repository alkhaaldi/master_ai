"""Layer 2+4: Signal Hooks + Trading Feature Flags."""
import os, shutil

changes = 0

# ═══ stock_radar.py ═══
print("=== stock_radar.py ===")
with open("stock_radar.py", "r") as f:
    sr = f.read()

# 3A: radar_enabled flag check
old_3a = """            cfg = _get_config()
            if not cfg.get("enabled", True):
                await asyncio.sleep(300)
                continue"""
new_3a = """            # Feature flag check (DB-backed, no restart needed)
            try:
                from feature_flags import FeatureFlags
                _ff = FeatureFlags("data/life.db")
                if not _ff.is_enabled("radar_enabled"):
                    logger.info("Radar disabled by feature flag")
                    await asyncio.sleep(300)
                    continue
            except Exception:
                pass
            cfg = _get_config()
            if not cfg.get("enabled", True):
                await asyncio.sleep(300)
                continue"""
if "radar_enabled" not in sr:
    sr = sr.replace(old_3a, new_3a, 1)
    print("  3A. Added radar_enabled flag check")
    changes += 1
else:
    print("  3A. SKIP exists")

# 3B: daily_refresh flag check
old_3b = """            if not _daily_snapshot_is_fresh():
                try:
                    logger.info("Refreshing daily snapshot (stale or missing)...")"""
new_3b = """            _do_daily = True
            try:
                from feature_flags import FeatureFlags
                _ff2 = FeatureFlags("data/life.db")
                _do_daily = _ff2.is_enabled("daily_refresh")
            except Exception:
                pass
            if _do_daily and not _daily_snapshot_is_fresh():
                try:
                    logger.info("Refreshing daily snapshot (stale or missing)...")"""
if "_do_daily" not in sr:
    sr = sr.replace(old_3b, new_3b, 1)
    print("  3B. Added daily_refresh flag check")
    changes += 1
else:
    print("  3B. SKIP exists")

# 3C: after_signal hook
old_3c = """                        _record_signal(sym, signal, result["candle_time"],
                                       result["price"], result["ema_fast"], result["ema_slow"],
                                       enriched=result)
                        msg = _format_alert(sym, signal, result["price"],"""
new_3c = """                        _record_signal(sym, signal, result["candle_time"],
                                       result["price"], result["ema_fast"], result["ema_slow"],
                                       enriched=result)
                        # Fire after_signal hook (non-blocking)
                        try:
                            from service_health import get_health_hub
                            _hub = get_health_hub()
                            if _hub:
                                _hk = getattr(_hub, '_hooks', None)
                                if _hk:
                                    _hk.fire_sync("after_signal",
                                        symbol=sym, signal_type=signal,
                                        price=result["price"],
                                        score=result.get("score", 0),
                                        timeframe="30m")
                        except Exception:
                            pass
                        msg = _format_alert(sym, signal, result["price"],"""
if "after_signal" not in sr:
    sr = sr.replace(old_3c, new_3c, 1)
    print("  3C. Added after_signal hook")
    changes += 1
else:
    print("  3C. SKIP exists")

# 3D: before_trade_alert hook
old_3d = """                            await send_fn(msg, _sig_meta)
                            logger.info(f"Radar alert sent: {sym} {signal}")"""
new_3d = """                            # before_trade_alert hook — can block the alert
                            _skip_alert = False
                            try:
                                from service_health import get_health_hub
                                _hub2 = get_health_hub()
                                if _hub2:
                                    _hk2 = getattr(_hub2, '_hooks', None)
                                    if _hk2:
                                        _hr = await _hk2.fire("before_trade_alert",
                                            symbol=sym, action=signal,
                                            confidence=result.get("score", 0))
                                        for _r in (_hr or []):
                                            if isinstance(_r, dict) and _r.get("skip"):
                                                _skip_alert = True
                                                logger.info("Hook blocked alert for %s: %s", sym, _r.get("reason", ""))
                                                break
                            except Exception:
                                pass
                            if _skip_alert:
                                continue
                            await send_fn(msg, _sig_meta)
                            logger.info(f"Radar alert sent: {sym} {signal}")"""
if "before_trade_alert" not in sr:
    sr = sr.replace(old_3d, new_3d, 1)
    print("  3D. Added before_trade_alert hook")
    changes += 1
else:
    print("  3D. SKIP exists")

# 3E: after_daily_refresh hook
old_3e = """        return {"ok": ok_count, "errors": err_count}
    finally:
        _daily_refresh_lock = False"""
new_3e = """        # Fire after_daily_refresh hook
        try:
            from service_health import get_health_hub
            _hub = get_health_hub()
            if _hub:
                _hk = getattr(_hub, '_hooks', None)
                if _hk:
                    _hk.fire_sync("after_daily_refresh",
                        ok_count=ok_count, err_count=err_count)
        except Exception:
            pass
        return {"ok": ok_count, "errors": err_count}
    finally:
        _daily_refresh_lock = False"""
if "after_daily_refresh" not in sr:
    sr = sr.replace(old_3e, new_3e, 1)
    print("  3E. Added after_daily_refresh hook")
    changes += 1
else:
    print("  3E. SKIP exists")

with open("/tmp/_patch_sr.py", "w") as f:
    f.write(sr)
os.remove("stock_radar.py")
shutil.move("/tmp/_patch_sr.py", "stock_radar.py")

# ═══ server.py ═══
print("\n=== server.py ===")
with open("server.py", "r") as f:
    sv = f.read()

if "_hook_check_market_hours" not in sv:
    old_hook = '    hook_registry.on("flag_toggled", _hook_log_flag_toggle)'
    new_hook = """    hook_registry.on("flag_toggled", _hook_log_flag_toggle)

    # Trading hook: block alerts outside market hours
    async def _hook_check_market_hours(**kwargs):
        try:
            from datetime import datetime, timezone, timedelta
            _kwt = timezone(timedelta(hours=3))
            now = datetime.now(_kwt)
            if now.weekday() not in {6, 0, 1, 2, 3}:  # Sun-Thu
                return {"skip": True, "reason": "Market closed (weekend)"}
            t = now.hour * 60 + now.minute
            if not (9 * 60 <= t <= 13 * 60 + 30):
                return {"skip": True, "reason": "Market closed (off-hours)"}
        except Exception:
            pass
        return {}
    hook_registry.on("before_trade_alert", _hook_check_market_hours)"""
    sv = sv.replace(old_hook, new_hook, 1)
    print("  Added _hook_check_market_hours handler")
    changes += 1
else:
    print("  SKIP already exists")

with open("/tmp/_patch_sv.py", "w") as f:
    f.write(sv)
os.remove("server.py")
shutil.move("/tmp/_patch_sv.py", "server.py")

print(f"\nDone ({changes} changes).")
