"""
sector_map.py — KSE Stock Sector Classification
Phase 3 of Master Plan V10

Maps all 128 tracked KSE stocks to their sectors based on
Boursa Kuwait official classification.
"""

# ═══════════════════════════════════════════════════
# SECTOR MAP — Boursa Kuwait Official Classification
# ═══════════════════════════════════════════════════

SECTOR_MAP = {
    # ── بنوك (Banks) ───────────────────────────────
    "NBK":       "بنوك",
    "KFH":       "بنوك",
    "BOUBYAN":   "بنوك",
    "CBK":       "بنوك",
    "GBK":       "بنوك",
    "ABK":       "بنوك",
    "KIB":       "بنوك",
    "BURG":      "بنوك",

    # ── خدمات مالية (Financial Services) ────────────
    "KAMCO":     "مالي",
    "MARKAZ":    "مالي",
    "NINV":      "مالي",
    "KMEFIC":    "مالي",
    "WETHAQ":    "مالي",
    "INOVEST":   "مالي",
    "KFIC":      "مالي",
    "KINV":      "مالي",
    "ASIYA":     "مالي",
    "IFA":       "مالي",
    "GIH":       "مالي",
    "ABAR":      "مالي",
    "OSOUL":     "مالي",
    "EKTTITAB":  "مالي",
    "SOKOUK":    "مالي",
    "NOOR":      "مالي",
    "UNICAP":    "مالي",
    "WARBACAP":  "مالي",
    "BAYANINV":  "مالي",
    "TAMINV":    "مالي",
    "ARZAN":     "مالي",
    "INJAZZAT":  "مالي",
    "ALIMTIAZ":  "مالي",
    "IPG":       "مالي",
    "TIJARA":    "مالي",

    # ── عقار (Real Estate) ─────────────────────────
    "MABANEE":   "عقار",
    "AAYANRE":   "عقار",
    "NRE":       "عقار",
    "ALDEERA":   "عقار",
    "URC":       "عقار",
    "AAYAN":     "عقار",
    "ALAQARIA":  "عقار",
    "ALTIJARIA": "عقار",
    "SRE":       "عقار",
    "AQAR":      "عقار",
    "KRE":       "عقار",
    "MAZAYA":    "عقار",
    "MANAZEL":   "عقار",
    "BEYOUT":    "عقار",
    "SOOR":      "عقار",
    "MARAKEZ":   "عقار",
    "ARKAN":     "عقار",
    "MUNSHAAT":  "عقار",
    "KUWAITRE":  "عقار",
    "WINSRE":    "عقار",
    "DALQANRE":  "عقار",
    "SANAM":     "عقار",
    "AMAR":      "عقار",
    "KPROJ":     "عقار",

    # ── صناعة (Industrials) ────────────────────────
    "NICBM":     "صناعة",
    "ACICO":     "صناعة",
    "CABLE":     "صناعة",
    "PAPCO":     "صناعة",
    "PCEM":      "صناعة",
    "BPCC":      "صناعة",
    "KCPC":      "صناعة",
    "KCEM":      "صناعة",
    "EQUIPMENT": "صناعة",
    "CGC":       "صناعة",
    "GFC":       "صناعة",
    "NIND":      "صناعة",
    "PAPER":     "صناعة",
    "KPPC":      "صناعة",
    "NCCI":      "صناعة",
    "GINS":      "صناعة",

    # ── اتصالات (Telecom) ─────────────────────────
    "ZAIN":      "اتصالات",
    "STC":       "اتصالات",
    "OOREDOO":   "اتصالات",

    # ── خدمات استهلاكية (Consumer Services) ─────────
    "HUMANSOFT": "استهلاكي",
    "FUTUREKID": "استهلاكي",
    "MEZZAN":    "استهلاكي",
    "AMERICANA": "استهلاكي",
    "CATTL":     "استهلاكي",
    "OSOS":      "استهلاكي",
    "CLEANING":  "استهلاكي",
    "ERESCO":    "استهلاكي",
    "FACIL":     "استهلاكي",
    "MKHZN":     "استهلاكي",
    "TAM":       "استهلاكي",

    # ── طاقة (Energy / Oil & Gas) ──────────────────
    "SENERGY":   "طاقة",
    "OULAFUEL":  "طاقة",
    "KFOUC":     "طاقة",
    "NAPESCO":   "طاقة",
    "KBT":       "طاقة",

    # ── تأمين (Insurance) ─────────────────────────
    "AINS":      "تأمين",
    "KINS":      "تأمين",
    "KCIN":      "تأمين",
    "IFAHR":     "تأمين",
    "KHOT":      "تأمين",

    # ── نقل وخدمات لوجستية (Transport & Logistics) ──
    "SHIP":      "نقل",
    "JAZEERA":   "نقل",
    "ASC":       "نقل",
    "MUBARRAD":  "نقل",

    # ── خدمات (Services / Diversified) ─────────────
    "BOURSA":    "خدمات",
    "TAHSSILAT": "خدمات",
    "DIGITUS":   "خدمات",
    "INTEGRATED":"خدمات",
    "ARABREC":   "خدمات",
    "FTI":       "خدمات",
    "JTC":       "خدمات",
    "ATC":       "خدمات",
    "COAST":     "خدمات",
    "SPEC":      "خدمات",
    "THURAYA":   "خدمات",
    "MENA":      "خدمات",
    "RASIYAT":   "خدمات",
    "MASHAER":   "خدمات",
    "ALMANAR":   "خدمات",
    "AREEC":     "خدمات",
    "ALG":       "خدمات",
    "ALSAFAT":   "خدمات",
    "ALKOUT":    "خدمات",
    "EMIRATESNBD":"خدمات",
    "ALFTAQA":   "خدمات",
    "AZNOULA":   "خدمات",
    "MRC":       "خدمات",
    "MADAR":     "خدمات",
    "NIH":       "خدمات",
    "MUNTAZAHAT":"خدمات",
    "EMIRATES":  "خدمات",
    "ALOLA":     "استهلاكي",
    "ARGAN":     "صناعة",
}


def get_sector(symbol: str) -> str:
    """Get sector for a symbol. Returns 'أخرى' if unknown."""
    return SECTOR_MAP.get(symbol.upper(), "أخرى")


def get_all_sectors() -> dict:
    """Returns {sector: [symbols]} mapping."""
    sectors = {}
    for sym, sec in SECTOR_MAP.items():
        sectors.setdefault(sec, []).append(sym)
    return sectors


def get_sector_summary() -> list:
    """Returns list of {sector, count} sorted by count."""
    sectors = get_all_sectors()
    return sorted(
        [{"sector": s, "count": len(syms), "symbols": syms} for s, syms in sectors.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
