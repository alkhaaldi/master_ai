"""
tv_data.py - TradingView Data Engine for Master AI
Fetches real-time KSE stock prices via tvDatafeed WebSocket.
"""
import json
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("tv_data")

SYMBOL_ALIASES = {
    # === Banks ===
    "\u0628\u064a\u062a\u0643": "KFH", "\u0628\u064a\u062a \u0627\u0644\u062a\u0645\u0648\u064a\u0644": "KFH", "kfh": "KFH", "\u0627\u0644\u062a\u0645\u0648\u064a\u0644": "KFH",
    "\u0627\u0644\u0648\u0637\u0646\u064a": "NBK", "nbk": "NBK",
    "\u0628\u0648\u0628\u064a\u0627\u0646": "BOUBYAN", "boubyan": "BOUBYAN",
    "\u0628\u0631\u0642\u0627\u0646": "BURG", "burg": "BURG",
    "\u0627\u0644\u0623\u0647\u0644\u064a": "ABK", "\u0627\u0644\u0627\u0647\u0644\u064a": "ABK", "abk": "ABK",
    "\u0627\u0644\u062a\u062c\u0627\u0631\u064a": "CBK", "cbk": "CBK",
    "\u0648\u0631\u0628\u0629": "WARBABANK", "\u0648\u0631\u0628\u0647": "WARBABANK", "warba": "WARBABANK", "warbabank": "WARBABANK",
    "\u0627\u0644\u062f\u0648\u0644\u064a": "KIB", "kib": "KIB",
    "\u0627\u0644\u062e\u0644\u064a\u062c": "GBK", "gbk": "GBK", "\u062e\u0644\u064a\u062c": "GBK",
    # === Telecom ===
    "\u0632\u064a\u0646": "ZAIN", "zain": "ZAIN",
    "\u0627\u0648\u0631\u064a\u062f\u0648": "OOREDOO", "ooredoo": "OOREDOO", "\u0627\u0644\u0648\u0637\u0646\u064a\u0629": "OOREDOO",
    "stc": "STC", "\u0627\u0633 \u062a\u064a \u0633\u064a": "STC", "\u0627\u0644\u0627\u062a\u0635\u0627\u0644\u0627\u062a": "STC",
    # === Real Estate & Development ===
    "\u0627\u0644\u0645\u0628\u0627\u0646\u064a": "MABANEE", "mabanee": "MABANEE", "\u0645\u0628\u0627\u0646\u064a": "MABANEE",
    "\u0645\u0631\u0627\u0643\u0632": "MARAKEZ", "marakez": "MARAKEZ",
    "\u0627\u0644\u0645\u0632\u0627\u064a\u0627": "MAZAYA", "\u0645\u0632\u0627\u064a\u0627": "MAZAYA", "mazaya": "MAZAYA",
    "\u0627\u0644\u062a\u062c\u0627\u0631\u064a\u0629 \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629": "ALTIJARIA", "\u0627\u0644\u062a\u062c\u0627\u0631\u064a\u0647": "ALTIJARIA", "altijaria": "ALTIJARIA",
    "\u0639\u0642\u0627\u0631\u0627\u062a \u0627\u0644\u0643\u0648\u064a\u062a": "KRE", "kre": "KRE",
    "\u0627\u0644\u0635\u0627\u0644\u062d\u064a\u0629": "SRE", "sre": "SRE", "\u0635\u0627\u0644\u062d\u064a\u0629": "SRE",
    "\u0627\u0644\u0627\u0646\u0645\u0627\u0621": "ERESCO", "eresco": "ERESCO",
    "\u0627\u0644\u0627\u0631\u062c\u0627\u0646": "ARGAN", "\u0623\u0631\u062c\u0627\u0646": "ARGAN", "argan": "ARGAN",
    "\u0645\u0646\u0634\u0622\u062a": "MUNSHAAT", "\u0645\u0646\u0634\u0627\u062a": "MUNSHAAT", "munshaat": "MUNSHAAT",
    "\u0645\u0646\u0627\u0632\u0644": "MANAZEL", "manazel": "MANAZEL",
    "\u0633\u0646\u0627\u0645": "SANAM", "sanam": "SANAM",
    "\u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629 \u0627\u0644\u0643\u0648\u064a\u062a\u064a\u0629": "ALAQARIA", "alaqaria": "ALAQARIA",
    "\u0627\u0644\u062a\u0645\u062f\u064a\u0646": "TAM", "\u062a\u0645\u062f\u064a\u0646": "TAM", "tam": "TAM",
    "\u0627\u0644\u062b\u0631\u064a\u0627": "THURAYA", "\u062b\u0631\u064a\u0627": "THURAYA", "thuraya": "THURAYA",
    "\u0627\u0631\u0643\u0627\u0646": "ARKAN", "arkan": "ARKAN",
    "\u0645\u064a\u0646\u0627": "MENA", "mena": "MENA",
    "\u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629 \u0627\u0644\u0645\u062a\u062d\u062f\u0629": "URC", "urc": "URC",
    "\u062f\u0644\u0642\u0627\u0646": "DALQANRE", "dalqanre": "DALQANRE",
    "\u0623\u0639\u064a\u0627\u0646 \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629": "AAYANRE", "aayanre": "AAYANRE",
    "\u0627\u0644\u0648\u0637\u0646\u064a\u0629 \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629": "NRE", "nre": "NRE",
    "\u0627\u0646\u062c\u0627\u0632\u0627\u062a": "INJAZZAT", "injazzat": "INJAZZAT",
    # === Aviation & Transport ===
    "\u0627\u0644\u062c\u0632\u064a\u0631\u0629": "JAZEERA", "\u062c\u0632\u064a\u0631\u0629": "JAZEERA", "jazeera": "JAZEERA",
    "\u0627\u0644\u0645\u0634\u0627\u0631\u064a\u0639 \u0627\u0644\u0645\u062a\u062d\u062f\u0629": "UPAC", "upac": "UPAC",
    "\u062c\u0627\u0633\u0645 \u0644\u0644\u0646\u0642\u0644\u064a\u0627\u062a": "JTC", "jtc": "JTC",
    # === Investment & Financial ===
    "\u0628\u0648\u0631\u0635\u0629": "BOURSA", "\u0628\u0648\u0631\u0635\u0647": "BOURSA", "boursa": "BOURSA",
    "\u0643\u0627\u0645\u0643\u0648": "KAMCO", "kamco": "KAMCO",
    "\u0627\u0644\u0627\u0645\u062a\u064a\u0627\u0632": "ALIMTIAZ", "\u0627\u0645\u062a\u064a\u0627\u0632": "ALIMTIAZ", "alimtiaz": "ALIMTIAZ",
    "\u0627\u0644\u0645\u0631\u0643\u0632": "MARKAZ", "\u0645\u0631\u0643\u0632": "MARKAZ", "markaz": "MARKAZ",
    "\u0627\u0644\u0627\u0633\u062a\u062b\u0645\u0627\u0631\u0627\u062a \u0627\u0644\u0648\u0637\u0646\u064a\u0629": "NINV", "ninv": "NINV",
    "\u0623\u0635\u0648\u0644": "OSOUL", "osoul": "OSOUL",
    "\u0628\u064a\u0627\u0646": "BAYANINV", "bayaninv": "BAYANINV",
    "\u0627\u0644\u0643\u0648\u064a\u062a\u064a\u0629 \u0644\u0644\u0627\u0633\u062a\u062b\u0645\u0627\u0631": "KINV", "kinv": "KINV",
    "\u0643\u0641\u064a\u0643": "KFIC", "kfic": "KFIC",
    "\u0622\u0633\u064a\u0627": "ASIYA", "\u0627\u0633\u064a\u0627": "ASIYA", "asiya": "ASIYA",
    "\u0627\u0631\u0632\u0627\u0646": "ARZAN", "\u0623\u0631\u0632\u0627\u0646": "ARZAN", "arzan": "ARZAN",
    "\u0627\u064a\u0641\u0627": "IFA", "ifa": "IFA",
    "\u0627\u0644\u0645\u062f\u0627\u0631": "MADAR", "madar": "MADAR",
    "\u0627\u0644\u0623\u0648\u0644\u0649 \u0644\u0644\u0627\u0633\u062a\u062b\u0645\u0627\u0631": "ALOLA", "alola": "ALOLA",
    "\u0635\u0643\u0648\u0643": "SOKOUK", "sokouk": "SOKOUK",
    "\u0627\u0644\u0645\u0646\u0627\u0631": "ALMANAR", "almanar": "ALMANAR",
    "\u064a\u0648\u0646\u064a\u0643\u0627\u0628": "UNICAP", "unicap": "UNICAP",
    "\u0648\u0631\u0628\u0629 \u0643\u0627\u0628\u064a\u062a\u0627\u0644": "WARBACAP", "warbacap": "WARBACAP",
    "\u0627\u0644\u062a\u0645\u062f\u064a\u0646 \u0627\u0644\u0627\u0633\u062a\u062b\u0645\u0627\u0631\u064a\u0629": "TAMINV", "taminv": "TAMINV",
    "\u0628\u064a\u062a \u0627\u0644\u0627\u0633\u062a\u062b\u0645\u0627\u0631": "GIH", "gih": "GIH",
    "\u0628\u064a\u062a \u0627\u0644\u0627\u0648\u0631\u0627\u0642": "SECH", "sech": "SECH",
    "\u0628\u064a\u062a \u0627\u0644\u0637\u0627\u0642\u0629": "ENERGYH", "energyh": "ENERGYH",
    "\u0627\u0644\u0627\u0645\u062a\u064a\u0627\u0632\u0627\u062a \u0627\u0644\u062e\u0644\u064a\u062c\u064a\u0629": "GFC", "gfc": "GFC",
    "\u0627\u0644\u0643\u0645\u064a\u0641\u0643": "KMEFIC", "kmefic": "KMEFIC",
    "\u0646\u0648\u0631": "NOOR", "noor": "NOOR",
    "\u0627\u0644\u062a\u062c\u0627\u0631\u0629 \u0648\u0627\u0644\u0627\u0633\u062a\u062b\u0645\u0627\u0631": "TIJARA", "tijara": "TIJARA",
    # === Industry & Services ===
    "\u0647\u064a\u0648\u0645\u0646 \u0633\u0648\u0641\u062a": "HUMANSOFT", "humansoft": "HUMANSOFT", "\u0647\u064a\u0648\u0645\u0646\u0633\u0648\u0641\u062a": "HUMANSOFT",
    "\u0627\u0644\u063a\u0627\u0646\u0645": "ALG", "alg": "ALG", "\u063a\u0627\u0646\u0645": "ALG",
    "\u0645\u0639\u062f\u0627\u062a": "EQUIPMENT", "\u0627\u0644\u0645\u0639\u062f\u0627\u062a": "EQUIPMENT", "equipment": "EQUIPMENT",
    "\u0627\u0643\u062a\u062a\u0627\u0628": "EKTTITAB", "ekttitab": "EKTTITAB",
    "\u0643\u0644\u064a\u0646\u064a\u0646\u0642": "CLEANING", "\u0643\u0644\u064a\u0646\u0646\u0642": "CLEANING", "\u0627\u0644\u062a\u0646\u0638\u064a\u0641": "CLEANING", "\u062a\u0646\u0638\u064a\u0641": "CLEANING", "cleaning": "CLEANING",
    "\u0633\u0646\u0631\u062c\u064a": "SENERGY", "senergy": "SENERGY",
    "\u0627\u064a\u0646\u0648\u0641\u0633\u062a": "INOVEST", "inovest": "INOVEST",
    "\u0627\u0644\u0635\u0646\u0627\u0639\u0627\u062a \u0627\u0644\u0648\u0637\u0646\u064a\u0629": "NICBM", "\u0635\u0646\u0627\u0639\u0627\u062a": "NICBM", "nicbm": "NICBM",
    "\u0627\u0633\u0645\u0646\u062a": "PCEM", "\u0628\u0648\u0631\u062a\u0644\u0627\u0646\u062f": "PCEM", "pcem": "PCEM",
    "\u0627\u0633\u0645\u0646\u062a \u0627\u0644\u0643\u0648\u064a\u062a": "KCEM", "kcem": "KCEM",
    "\u0628\u0648\u0628\u064a\u0627\u0646 \u0628\u062a\u0631\u0648": "BPCC", "\u0628\u062a\u0631\u0648\u0643\u064a\u0645\u0627\u0648\u064a\u0627\u062a": "BPCC", "bpcc": "BPCC",
    "\u0643\u0627\u0628\u0644\u0627\u062a": "CABLE", "\u0627\u0644\u0643\u0627\u0628\u0644\u0627\u062a": "CABLE", "cable": "CABLE",
    "\u0627\u0644\u0643\u0648\u062a": "ALKOUT", "alkout": "ALKOUT",
    "\u0627\u0633\u064a\u0643\u0648": "ACICO", "acico": "ACICO",
    "\u0627\u0644\u0645\u0639\u0627\u062f\u0646": "MRC", "mrc": "MRC",
    "\u0627\u0644\u0633\u0641\u0646": "SHIP", "\u0628\u0646\u0627\u0621 \u0627\u0644\u0633\u0641\u0646": "SHIP", "ship": "SHIP",
    "\u0627\u0644\u0645\u0642\u0627\u0648\u0644\u0627\u062a \u0627\u0644\u0645\u0634\u062a\u0631\u0643\u0629": "CGC", "cgc": "CGC",
    "\u0628\u0646\u0627\u0621 \u0627\u0644\u0645\u0639\u0627\u0645\u0644": "KCPC", "kcpc": "KCPC",
    "\u0627\u0644\u0646\u062e\u064a\u0644": "PAPCO", "papco": "PAPCO",
    "\u0627\u062c\u064a\u0644\u064a\u062a\u064a": "MKHZN", "\u0627\u0644\u0645\u062e\u0627\u0632\u0646": "MKHZN", "mkhzn": "MKHZN", "agility": "MKHZN",
    "\u0645\u064a\u0632\u0627\u0646": "MEZZAN", "\u0645\u064a\u0632\u0646": "MEZZAN", "mezzan": "MEZZAN",
    "\u0627\u0644\u0648\u0642\u0648\u062f": "OULAFUEL", "oulafuel": "OULAFUEL",
    "\u0627\u0644\u0627\u0646\u0638\u0645\u0629 \u0627\u0644\u0622\u0644\u064a\u0629": "ASC", "asc": "ASC",
    "\u0627\u0644\u062a\u0642\u062f\u0645": "ATC", "atc": "ATC",
    "\u0646\u0627\u0628\u0633\u0643\u0648": "NAPESCO", "napesco": "NAPESCO",
    "\u0627\u0644\u0634\u0639\u064a\u0628\u0629": "PAPER", "paper": "PAPER",
    "\u0628\u0631\u0642\u0627\u0646 \u0644\u062d\u0641\u0631 \u0627\u0644\u0622\u0628\u0627\u0631": "ABAR", "abar": "ABAR",
    "\u0645\u0628\u0631\u062f": "MUBARRAD", "mubarrad": "MUBARRAD",
    "\u0627\u0644\u0633\u0643\u0628": "KFOUC", "kfouc": "KFOUC",
    "\u062d\u064a\u0627\u0629 \u0644\u0644\u0627\u062a\u0635\u0627\u0644\u0627\u062a": "DIGITUS", "digitus": "DIGITUS",
    "\u0627\u0644\u0633\u0648\u0631": "SOOR", "soor": "SOOR",
    "\u062a\u0635\u0646\u064a\u0641": "TAHSSILAT", "tahssilat": "TAHSSILAT",
    "\u0627\u0644\u0628\u062a\u0631\u0648\u0644\u064a\u0629": "IPG", "ipg": "IPG",
    "\u0637\u0627\u0642\u0629": "ALFTAQA", "alftaqa": "ALFTAQA",
    # === Insurance ===
    "\u0627\u0644\u0643\u0648\u064a\u062a \u0644\u0644\u062a\u0623\u0645\u064a\u0646": "KINS", "kins": "KINS",
    "\u0627\u0644\u0623\u0647\u0644\u064a\u0629 \u0644\u0644\u062a\u0623\u0645\u064a\u0646": "AINS", "ains": "AINS",
    "\u0627\u0644\u062a\u0643\u0627\u0641\u0644\u064a": "FTI", "fti": "FTI",
    "\u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u062a\u0623\u0645\u064a\u0646": "KUWAITRE", "kuwaitre": "KUWAITRE",
    "\u0648\u0631\u0628\u0629 \u0644\u0644\u062a\u0623\u0645\u064a\u0646": "WINSRE", "winsre": "WINSRE",
    "\u0627\u0644\u062e\u0644\u064a\u062c \u0644\u0644\u062a\u0623\u0645\u064a\u0646": "GINS", "gins": "GINS",
    "\u0648\u062b\u0627\u0642": "WETHAQ", "wethaq": "WETHAQ",
    # === Holdings & Diversified ===
    "\u0627\u0644\u062f\u064a\u0631\u0629": "ALDEERA", "aldeera": "ALDEERA",
    "\u0627\u0644\u0645\u062a\u0643\u0627\u0645\u0644\u0629": "INTEGRATED", "integrated": "INTEGRATED",
    "\u0631\u0627\u0633\u064a\u0627\u062a": "RASIYAT", "rasiyat": "RASIYAT",
    "\u0623\u0639\u064a\u0627\u0646": "AAYAN", "aayan": "AAYAN",
    "\u0627\u0644\u0635\u0646\u0627\u0639\u0627\u062a \u0627\u0644\u0648\u0637\u0646\u064a\u0629 \u0627\u0644\u0642\u0627\u0628\u0636\u0629": "NIND", "nind": "NIND",
    "\u0627\u0644\u062a\u0633\u0647\u064a\u0644\u0627\u062a": "FACIL", "facil": "FACIL",
    "\u0634\u0645\u0627\u0644 \u0627\u0644\u0632\u0648\u0631": "AZNOULA", "\u0627\u0644\u0632\u0648\u0631": "AZNOULA", "aznoula": "AZNOULA",
    "\u0627\u0644\u062a\u062e\u0635\u064a\u0635": "KPPC", "kppc": "KPPC",
    "\u0645\u0634\u0627\u0631\u064a\u0639 \u0627\u0644\u0643\u0648\u064a\u062a": "KPROJ", "kproj": "KPROJ",
    "\u0645\u0634\u0627\u0639\u0631": "MASHAER", "mashaer": "MASHAER",
    "\u0639\u0642\u0627\u0631": "AQAR", "aqar": "AQAR",
    "\u0627\u0644\u0627\u0645\u0627\u0631\u0627\u062a\u064a\u0629": "EMIRATES", "emirates": "EMIRATES",
    "\u0627\u0644\u0635\u0641\u0627\u0629": "ALSAFAT", "\u0635\u0641\u0627\u0629": "ALSAFAT", "alsafat": "ALSAFAT",
    "\u0627\u0644\u062e\u0635\u0648\u0635\u064a\u0629": "SPEC", "spec": "SPEC",
    # === Leisure & Consumer ===
    "\u0627\u064a\u0641\u0627 \u0644\u0644\u0641\u0646\u0627\u062f\u0642": "IFAHR", "ifahr": "IFAHR",
    "\u0627\u0644\u0633\u064a\u0646\u0645\u0627": "KCIN", "kcin": "KCIN",
    "\u0627\u0644\u0641\u0646\u0627\u062f\u0642 \u0627\u0644\u0643\u0648\u064a\u062a\u064a\u0629": "KHOT", "khot": "KHOT",
    "\u0637\u0641\u0644 \u0627\u0644\u0645\u0633\u062a\u0642\u0628\u0644": "FUTUREKID", "futurekid": "FUTUREKID",
    "\u0627\u0644\u0627\u0633\u062a\u0647\u0644\u0627\u0643\u064a\u0629": "NCCI", "ncci": "NCCI",
    "\u0627\u0644\u0645\u0648\u0627\u0634\u064a": "CATTL", "cattl": "CATTL",
    "\u0627\u0644\u0633\u0627\u062d\u0644": "COAST", "coast": "COAST",
    "\u0627\u0644\u0645\u0646\u062a\u0632\u0647\u0627\u062a": "MUNTAZAHAT", "muntazahat": "MUNTAZAHAT",
    "\u0627\u062c\u064a\u0627\u0644": "AREEC", "areec": "AREEC",
    "\u0627\u0644\u0639\u0631\u0628\u064a\u0629 \u0627\u0644\u0639\u0642\u0627\u0631\u064a\u0629": "ARABREC", "arabrec": "ARABREC",
    "\u0623\u0633\u0633": "OSOS", "osos": "OSOS",
    "\u0627\u0644\u0628\u064a\u0648\u062a": "BEYOUT", "beyout": "BEYOUT",
    "\u0639\u0645\u0627\u0631": "AMAR", "amar": "AMAR",
    "\u0645\u062f\u064a\u0646\u0629 \u0627\u0644\u0623\u0639\u0645\u0627\u0644": "KBT", "kbt": "KBT",
}

KSE_STOCKS = {}

def _load_kse_stocks(csv_path=None):
    global KSE_STOCKS
    p = csv_path or str(Path(__file__).parent / "data" / "kse_stocks.csv")
    if Path(p).exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    ticker = parts[0].strip()
                    name_ar = parts[1].strip()
                    KSE_STOCKS[ticker] = name_ar
                    SYMBOL_ALIASES[name_ar] = ticker
                    SYMBOL_ALIASES[ticker.lower()] = ticker
            logger.info(f"Loaded {len(KSE_STOCKS)} KSE stocks")
        except Exception as e:
            logger.warning(f"CSV load failed: {e}")

_price_cache = {}
_cache_lock = threading.Lock()

def _is_market_open():
    now = datetime.utcnow() + timedelta(hours=3)
    if now.weekday() in (4, 5):
        return False
    return now.replace(hour=9,minute=0,second=0) <= now <= now.replace(hour=13,minute=0,second=0)

def _cache_ttl():
    return 60 if _is_market_open() else 900

_tv_instance = None
_tv_lock = threading.Lock()

def _get_tv():
    global _tv_instance
    with _tv_lock:
        if _tv_instance is None:
            from tvDatafeed import TvDatafeed
            cp = Path(__file__).parent / "data" / "tv_credentials.json"
            if cp.exists():
                c = json.loads(cp.read_text())
                if c.get("username","") not in ("","CHANGE_ME"):
                    _tv_instance = TvDatafeed(c["username"], c["password"])
                    logger.info("TvDatafeed: logged in")
                    return _tv_instance
            _tv_instance = TvDatafeed()
            logger.info("TvDatafeed: no login")
        return _tv_instance

def resolve_symbol(query):
    q = query.strip().lower()
    if q in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[q]
    upper = query.strip().upper()
    if upper in KSE_STOCKS:
        return upper
    for alias, ticker in SYMBOL_ALIASES.items():
        if q in alias.lower():
            return ticker
    return upper


def _normalize_price_to_fils(price, symbol=None):
    """Normalize price to fils. TradingView sometimes returns KWD for KSE stocks.
    If price < 10, it's likely KWD → multiply by 1000.
    If price >= 10, it's likely already fils."""
    if price is None:
        return None
    price = float(price)
    if price < 10:
        return round(price * 1000, 1)
    return round(price, 1)


def get_price(symbol, n_bars=30):
    ticker = resolve_symbol(symbol)
    ck = f"{ticker}_{n_bars}"
    with _cache_lock:
        if ck in _price_cache:
            e = _price_cache[ck]
            if time.time() - e["ts"] < _cache_ttl():
                return e["data"]
    try:
        from tvDatafeed import Interval
        df = _get_tv().get_hist(ticker, "KSE", Interval.in_daily, n_bars=n_bars)
        if df is None or df.empty:
            return {"error": f"No data for {ticker}", "ticker": ticker}
        cur = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else cur
        price = float(cur["close"])
        pc = float(prev["close"])
        ch = price - pc
        result = {
            "ticker": ticker, "name_ar": KSE_STOCKS.get(ticker, ticker),
            "exchange": "KSE", "price": price,
            "open": float(cur["open"]), "high": float(cur["high"]),
            "low": float(cur["low"]), "close": price,
            "volume": int(cur["volume"]), "prev_close": pc,
            "change": round(ch, 3), "change_pct": round(ch/pc*100 if pc else 0, 2),
            "timestamp": str(df.index[-1]), "market_open": _is_market_open(),
            "history": {
                "close": df["close"].tolist(), "high": df["high"].tolist(),
                "low": df["low"].tolist(), "open": df["open"].tolist(),
                "volume": df["volume"].tolist(),
                "dates": [str(d) for d in df.index],
            },
        }
        with _cache_lock:
            _price_cache[ck] = {"ts": time.time(), "data": result}
        return result
    except Exception as e:
        logger.error(f"get_price({ticker}): {e}")
        return {"error": str(e), "ticker": ticker}

def get_multiple_prices(symbols):
    results = []
    for s in symbols:
        results.append(get_price(s))
        time.sleep(0.5)
    return results

def search_symbol(query):
    q = query.strip().lower()
    return [{"ticker": t, "name_ar": n} for t, n in KSE_STOCKS.items()
            if q in t.lower() or q in n][:10]


def get_top_volume(top_n=10):
    """Fetch top N stocks by volume. Uses cached data when available."""
    from tvDatafeed import Interval
    tv = _get_tv()
    results = []
    for ticker in KSE_STOCKS:
        ck = f"{ticker}_5"
        with _cache_lock:
            if ck in _price_cache:
                e = _price_cache[ck]
                if time.time() - e["ts"] < 900:
                    d = e["data"]
                    if "error" not in d:
                        results.append({"ticker": ticker, "name_ar": KSE_STOCKS[ticker],
                            "price": d["price"], "volume": d["volume"],
                            "change_pct": d["change_pct"]})
                    continue
        try:
            df = tv.get_hist(ticker, "KSE", Interval.in_daily, n_bars=5)
            if df is not None and not df.empty:
                cur = df.iloc[-1]
                prev = df.iloc[-2] if len(df) > 1 else cur
                p = float(cur["close"])
                pc = float(prev["close"])
                v = int(cur["volume"])
                ch = round((p - pc) / pc * 100 if pc else 0, 2)
                results.append({"ticker": ticker, "name_ar": KSE_STOCKS[ticker],
                    "price": p, "volume": v, "change_pct": ch})
                with _cache_lock:
                    _price_cache[ck] = {"ts": time.time(), "data": {
                        "ticker": ticker, "price": p, "volume": v,
                        "change_pct": ch, "name_ar": KSE_STOCKS[ticker]}}
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"top_volume skip {ticker}: {e}")
            continue
    results.sort(key=lambda x: x["volume"], reverse=True)
    return results[:top_n]


def format_top_volume_arabic(stocks):
    """Format top volume list as Arabic text."""
    if not stocks:
        return "\u274c \u0645\u0627 \u0642\u062f\u0631\u062a \u0623\u0633\u062d\u0628 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u062a\u062f\u0627\u0648\u0644"
    lines = ["\U0001f4ca \u0623\u0639\u0644\u0649 " + str(len(stocks)) + " \u0623\u0633\u0647\u0645 \u062a\u062f\u0627\u0648\u0644 \u0627\u0644\u064a\u0648\u0645:", ""]
    for i, s in enumerate(stocks, 1):
        arrow = "\u2b06\ufe0f" if s["change_pct"] >= 0 else "\u2b07\ufe0f"
        lines.append(f"{i}. {s['name_ar']} ({s['ticker']})")
        lines.append(f"   {arrow} {s['price']} fils | {s['change_pct']:+.2f}% | Vol: {s['volume']:,}")
    return chr(10).join(lines)

_load_kse_stocks()
