# تنبيه موجة صعود — Momentum Alert للأسهم اللي تصعد بقوة
# التاريخ: 2026-03-31
# المنفذ: Claude Code

## المشكلة
THURAYA صعد +7.3% بحجم 3x والرادار يشوفه (score=100, verdict=فرصة قوية)
لكن golden_engine ما يرشحه لأن أنماطه التاريخية win_rate < 55%.
المستخدم يبي يعرف عن هالأسهم حتى لو ما عندها pattern ناجح تاريخياً.

## الحل: Momentum Alert داخل market_hours_scanner

### 1. أضف دالة `_check_momentum_alerts()` في kse_data_collector.py

```python
def _check_momentum_alerts() -> list:
    """Find stocks with strong momentum even without qualifying patterns."""
    import requests as _req
    
    alerts = []
    try:
        with _conn() as c:
            # Stocks with: change > 4% OR (volume_ratio > 2.5 AND change > 2%) OR score >= 90
            rows = c.execute("""
                SELECT symbol, price, change_pct, vol_ratio, score, verdict, rsi,
                       trend, ema_fast, ema_slow
                FROM stock_radar_daily
                WHERE (change_pct >= 4.0)
                   OR (vol_ratio >= 2.5 AND change_pct >= 2.0)
                   OR (score >= 90 AND change_pct >= 1.5)
                ORDER BY change_pct DESC
            """).fetchall()
            
            for r in rows:
                sym = r[0]
                # Check if already alerted today
                today = date.today().isoformat()
                existing = c.execute(
                    "SELECT id FROM signal_reviews WHERE symbol=? AND review_date=? AND smart_decision='MOMENTUM'",
                    (sym, today)
                ).fetchone()
                if existing:
                    continue
                    
                alerts.append({
                    "symbol": sym,
                    "price": r[1],
                    "change_pct": r[2],
                    "vol_ratio": r[3],
                    "score": r[4],
                    "verdict": r[5],
                    "rsi": r[6],
                    "trend": r[7],
                })
    except Exception as e:
        logging.getLogger("momentum").warning("Momentum check failed: %s", e)
    
    return alerts


def _send_momentum_alert(alerts: list) -> bool:
    """Send Telegram alert for momentum stocks."""
    import requests as _req
    
    if not alerts:
        return False
    
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or _read_file("~/.telegram_bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("ADMIN_TELEGRAM_ID") or _read_file("~/.telegram_chat_id")
    if not bot_token or not chat_id:
        return False
    
    lines = [f"🚀 <b>موجة صعود — {len(alerts)} سهم</b>\n"]
    
    for a in alerts[:8]:  # max 8
        rsi_warn = " ⚠️RSI" if a.get("rsi", 0) > 75 else ""
        vol_str = f"{a['vol_ratio']:.1f}x" if a.get("vol_ratio") else "--"
        lines.append(
            f"<b>{a['symbol']}</b> {a['price']} "
            f"<b>+{a['change_pct']:.1f}%</b> "
            f"📊{vol_str} "
            f"{'🔥' if a.get('score',0) >= 90 else '📈'}{a.get('score',0)}"
            f"{rsi_warn}"
        )
    
    lines.append(f"\n⚠️ <i>تنبيه حركة — ليس ترشيح دخول</i>")
    
    text = "\n".join(lines)
    try:
        resp = _req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False
```

### 2. استدعاؤها من market_hours_scanner

بعد scan_opportunities في market_hours_scanner، أضف:

```python
            # Momentum alerts — stocks moving strongly without pattern match
            try:
                from kse_data_collector import _check_momentum_alerts, _send_momentum_alert
                momentum = _check_momentum_alerts()
                if momentum:
                    _send_momentum_alert(momentum)
                    _log.info("Momentum: %d alerts", len(momentum))
            except Exception as _e:
                _log.warning("Momentum check failed: %s", _e)
```

### 3. أمر `/موجة` بالتيليقرام

أضف في server.py بعد `/تقييم`:

```python
    if cmd == "/موجة" or cmd == "/momentum":
        try:
            from kse_data_collector import _check_momentum_alerts
            alerts = _check_momentum_alerts()
            if not alerts:
                return "⚪ لا توجد موجات صعود حالياً"
            lines = [f"🚀 <b>{len(alerts)} سهم بموجة صعود</b>\n"]
            for a in alerts[:10]:
                rsi_warn = " ⚠️RSI عالي" if a.get("rsi", 0) > 75 else ""
                lines.append(
                    f"<b>{a['symbol']}</b> — {a['price']} | "
                    f"+{a['change_pct']:.1f}% | "
                    f"حجم {a.get('vol_ratio',0):.1f}x | "
                    f"سكور {a.get('score',0)}"
                    f"{rsi_warn}"
                )
            lines.append(f"\n⚠️ <i>تنبيه حركة — ليس ترشيح دخول رسمي</i>")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ خطأ: {e}"
```

### 4. الشروط:

السهم يدخل "موجة صعود" إذا تحقق أي من:
- **change >= 4%** (صعود قوي بأي حجم)
- **volume >= 2.5x AND change >= 2%** (حجم غير عادي مع صعود)
- **score >= 90 AND change >= 1.5%** (سكور عالي مع صعود)

### 5. الفرق عن الترشيحات:

الرسالة تقول بوضوح: "⚠️ تنبيه حركة — ليس ترشيح دخول"
يعني: "هالسهم قاعد يتحرك بقوة — شوف بنفسك إذا تبي تدخل"
مو مثل الترشيحات اللي تقول "ادخل بستوب وهدف"

## بعد التنفيذ:
```bash
python3 _tools/quick_check.py
sudo systemctl restart master-ai

# اختبار:
# أرسل /موجة بالتيليقرام
```
