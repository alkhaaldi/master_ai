# Gemini Scanner — Universe Filter Update
# Date: 2026-04-01
# Author: claude.ai → Claude Code executes
# Status: READY FOR EXECUTION

## Overview
Replace the current 128-stock universe with a **92-stock filtered universe**
based on actual monthly trading volume from Boursa Kuwait data (TradingView Screener export).

**Filter criteria:** Monthly volume >= 100,000 shares
**Result:** 92 active stocks (54 Premier + 38 Main), 40 dead stocks excluded

## Why
- 40 stocks have < 100K monthly volume (some as low as 207 shares/month)
- Gemini analysis on dead stocks wastes time and API costs
- Reduces Bridge API 429 rate limit errors
- Prefilter stage becomes more meaningful (92 → 15 instead of 128 → 17)

---

## Step 1: Create scanner_universe.py (NEW FILE)

Location: `/home/pi/master_ai/scanner_universe.py`

```python
"""
scanner_universe.py — Filtered stock universe for Gemini Scanner
Based on Boursa Kuwait monthly volume data (2026-04-01)
Filter: Monthly volume >= 100,000 shares

Premier Market: 54 stocks (السوق الأول)
Main Market: 38 stocks (السوق الرئيسي) 
Total: 92 stocks

Dead stocks excluded: 40 (vol < 100K/month)
"""

PREMIER_MARKET = [
    'KFH', 'AAYAN', 'MKHZN', 'NBK', 'KIB', 'NIND', 'ALFTAQA',
    'WARBABANK', 'IFA', 'ALTIJARIA', 'GBK', 'COAST', 'ZAIN',
    'IFAHR', 'KINV', 'ABK', 'BEYOUT', 'BOUBYAN', 'NINV', 'SRE',
    'KRE', 'KPROJ', 'MRC', 'FUTUREKID', 'THURAYA', 'TROLLEY',
    'OULAFUEL', 'BPCC', 'ALG', 'MABANEE', 'STC', 'BURG', 'FACIL',
    'OSOUL', 'JTC', 'ERESCO', 'INTEGRATED', 'CABLE', 'BAYANINV',
    'KCEM', 'BOURSA', 'SHIP', 'KHOT', 'ARZAN', 'ABAR', 'TAHSSILAT',
    'TIJARA', 'KUWAITRE', 'FTI', 'MUNTAZAHAT', 'WINSRE', 'ALAQARIA',
    'URC', 'TAM',
]

MAIN_MARKET = [
    'CLEANING', 'ARGAN', 'EKTTITAB', 'MANAZEL', 'DALQANRE', 'ALOLA',
    'NCCI', 'MADAR', 'KPPC', 'MARAKEZ', 'NRE', 'ALDEERA', 'KBT',
    'ACICO', 'ALSAFAT', 'EQUIPMENT', 'ALIMTIAZ', 'MAZAYA', 'AZNOULA',
    'ASIYA', 'NIH', 'RASIYAT', 'SANAM', 'ENERGYH', 'DIGITUS',
    'AAYANRE', 'ARKAN', 'SENERGY', 'SECH', 'EMIRATES', 'ARABREC',
    'SOKOUK', 'WETHAQ', 'NOOR', 'MENA', 'SPEC', 'MASHAER', 'UNICAP',
]

# Combined scanner universe (ordered by volume)
SCANNER_UNIVERSE = PREMIER_MARKET + MAIN_MARKET

# Dead stocks excluded from scanning (vol < 100K/month)
EXCLUDED_LOW_VOLUME = [
    'CGC', 'JAZEERA', 'CATTL', 'OOREDOO', 'MUBARRAD', 'KFOUC',
    'IPG', 'AREEC', 'HUMANSOFT', 'ALMANAR', 'MIDAN', 'KCPC',
    'INJAZZAT', 'NICBM', 'PCEM', 'CBK', 'PAPER', 'AMAR', 'KFIC',
    'AQAR', 'AINS', 'NAPESCO', 'OSOS', 'GFC', 'SOOR', 'ALKOUT',
    'KINS', 'MEZZAN', 'UPAC', 'KCIN', 'TAMINV', 'ATC',
    'KMEFIC', 'PAPCO', 'ASC', 'MUNSHAAT', 'GIH', 'KAMCO',
    'MARKAZ', 'WARBACAP',
]

def get_scanner_universe():
    """Return the active scanner universe (92 stocks)."""
    return SCANNER_UNIVERSE.copy()

def get_market(symbol):
    """Return 'premier' or 'main' for a symbol."""
    if symbol in PREMIER_MARKET:
        return 'premier'
    elif symbol in MAIN_MARKET:
        return 'main'
    return 'unknown'

def is_active(symbol):
    """Check if a symbol is in the active universe."""
    return symbol in SCANNER_UNIVERSE
```

---

## Step 2: Update gemini_scanner.py

### Change 1: Import scanner_universe
At the top of gemini_scanner.py, add:
```python
from scanner_universe import get_scanner_universe, get_market
```

### Change 2: Replace universe fetching
In the `_prefilter_universe()` method (or wherever the 128 stocks come from),
replace the current universe source with:
```python
# OLD: symbols = self.get_all_128_symbols()  # or however it's done
# NEW:
symbols = get_scanner_universe()  # 92 active stocks
```

### Change 3: Add market info to results
When saving to `gemini_decisions` table, add the market classification:
```python
# In the fusion/save step:
market = get_market(symbol)  # 'premier' or 'main'
```

---

## Step 3: Add 14 new symbols to sector_map.py

These symbols are in the active universe but NOT in sector_map.py:
```python
# Add to SECTOR_MAP dict:
"MKHZN":       "وسائل النقل",      # Agility
"TROLLEY":     "تجارة التجزئة",     # Trolley
"EKTTITAB":    "مالي",              # Ekttitab Holding
"MANAZEL":     "مالي",              # Manazel Holding
"DALQANRE":    "مالي",              # Dalqan RE
"KPPC":        "خدمات تجارية",      # Takhsees Holding
"EQUIPMENT":   "صناعي",             # Equipment Holding
"AZNOULA":     "طاقة",              # North Zour First Power
"ENERGYH":     "طاقة",              # Energy House Holding
"DIGITUS":     "اتصالات",           # Hayat Communications (Digitus)
"FTI":         "صناعي",             # FTI
"MUNTAZAHAT":  "خدمات مستهلك",      # Muntazahat
"ASIYA":       "مالي",              # Asiya Capital
"EMIRATES":    "مالي",              # Kuwait Emirates Holding
```

---

## Step 4: Update stock_radar.py universe (if separate)

If stock_radar.py has its own hardcoded list of 128 stocks,
update it to use `scanner_universe.py` as well:
```python
from scanner_universe import get_scanner_universe
# Replace hardcoded list with:
symbols = get_scanner_universe()
```

---

## Step 5: Add `market` column to gemini_decisions table

```sql
ALTER TABLE gemini_decisions ADD COLUMN market TEXT DEFAULT 'unknown';
```

---

## Step 6: Testing

1. `python3 -c "from scanner_universe import *; print(len(SCANNER_UNIVERSE))"`
   → Should print 92
2. `quick_check.py` — no import errors
3. `smoke_test.py` — endpoints accessible
4. Trigger manual scan: `POST /api/scanner/scan`
5. Verify scan uses 92 stocks (not 128)
6. Check DB: new entries should have `market` column

---

## Summary

| What | Before | After |
|------|--------|-------|
| Universe size | 128 | 92 (-28%) |
| Prefilter candidates | ~17 | ~12-15 |
| Gemini analyzed | ~17 | ~12-15 |
| Scan time | ~17 min | ~12 min |
| Bridge 429 errors | frequent | reduced |
| Dead stock analysis | yes (waste) | no |

## Files to create/modify
| File | Action | Who |
|------|--------|-----|
| scanner_universe.py | CREATE | Claude Code |
| gemini_scanner.py | MODIFY (import + universe source) | Claude Code |
| sector_map.py | MODIFY (add 14 symbols) | Claude Code |
| stock_radar.py | MODIFY (if has hardcoded list) | Claude Code |
| gemini_decisions table | ALTER (add market column) | Claude Code |
