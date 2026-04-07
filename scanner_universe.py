"""
scanner_universe.py — Filtered stock universe for Gemini Scanner
Based on Boursa Kuwait monthly volume data (2026-04-01)
Filter: Monthly volume >= 100,000 shares

Premier Market: 54 stocks
Main Market: 38 stocks
Total: 92 stocks
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

SCANNER_UNIVERSE = PREMIER_MARKET + MAIN_MARKET

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
    if symbol in MAIN_MARKET:
        return 'main'
    return 'unknown'


def is_active(symbol):
    """Check if a symbol is in the active universe."""
    return symbol in SCANNER_UNIVERSE
