# FIX: Bridge IP Changed — 192.168.111.158 → 192.168.111.159
# Date: 2026-04-07
# Author: claude.ai (plan) → Claude Code (execute)
# Priority: URGENT — Dashboard analysis stale because Bridge unreachable

## المشكلة
PC IP تغيّر من `192.168.111.158` إلى `192.168.111.159`.
كل ملفات Python اللي تتصل بالـ Bridge تستخدم الـ IP القديم.

## الحل الأفضل (طويل المدى)
بدال hardcode الـ IP، استخدم متغير بيئة أو config file:
1. أضف `BRIDGE_HOST=192.168.111.159` في `/home/pi/master_ai/.env`
2. كل ملف يقرأ: `BRIDGE_BASE = os.getenv("BRIDGE_HOST", "http://192.168.111.158:8059")`

## الحل السريع (الحين)
غيّر `192.168.111.158` → `192.168.111.159` في كل الملفات:

### الملفات المتأثرة (10 مواقع في 8 ملفات):
```
brain_backfill.py:20       BRIDGE_URL
bridge_client_new.py:14    BRIDGE_BASE_URL
bridge_client.py:14        BRIDGE_BASE_URL
dashboard_api.py:734       hardcoded URL
dashboard_api.py:2738      hardcoded URL
journal_engine.py:293      hardcoded URL
kse_data_collector.py:23   BRIDGE_URL
stock_analyzer.py:11       BRIDGE_BASE
stock_radar.py:687         hardcoded URL
stock_radar.py:1161        BRIDGE
```

### التنفيذ:
```bash
cd /home/pi/master_ai

# الحل السريع — find and replace
sed -i 's/192\.168\.111\.158/192.168.111.159/g' \
  brain_backfill.py bridge_client_new.py bridge_client.py \
  dashboard_api.py journal_engine.py kse_data_collector.py \
  stock_analyzer.py stock_radar.py

# تحقق
grep -rn '192.168.111.158' *.py  # يجب يرجع فاضي
grep -rn '192.168.111.159' *.py  # يجب يبيّن 10 نتائج

# اختبر
python3 -c "from stock_analyzer import _bridge_available; print('Bridge:', _bridge_available())"

# commit + restart
git add -A && git commit -m "fix: update Bridge IP 158→159"
bash _tools/restart_master_ai.sh

# شغّل التحليل
curl -s -X POST -H "X-API-Key: $(cat ~/.master_ai_key)" http://localhost:9000/api/refresh-analysis | head -3
```

### الحل الطويل المدى (اختياري — بعد الإصلاح السريع):
أضف في `.env`:
```
BRIDGE_URL=http://192.168.111.159:8059
```
وكل ملف يقرأ:
```python
BRIDGE_BASE = os.getenv("BRIDGE_URL", "http://192.168.111.159:8059")
```
هذا يخلي تغيير الـ IP مستقبلاً = تعديل `.env` فقط بدون لمس 8 ملفات.

### بعد الحل:
ثبّت IP الكمبيوتر في الراوتر (DHCP Reservation) على عنوان ثابت.
