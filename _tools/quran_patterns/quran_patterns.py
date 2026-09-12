#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quran_patterns.py — Structural / numerical pattern search over the Quran text
with honest statistical significance testing.

Design principles (anti-overfitting):
  1. Every hypothesis family is declared BEFORE looking at the numbers
     (see HYPOTHESIS_FAMILIES below and the pre-registered word pairs).
  2. Every test has an explicit null model (permutation / jitter / binomial).
  3. All p-values from the discovery battery are corrected together
     (Benjamini-Hochberg FDR + Bonferroni) — the "look-elsewhere" effect
     is measured, not ignored.
  4. Counting rules for words are fixed ex ante and applied uniformly to
     every pair; sensitivity to the rule is reported instead of hidden.
  5. Famous claims (6236 parity identity, 24/24, 32/13 sea/land, 365 يوم)
     are REPLICATED, not assumed, and their chance probability is computed.

Data: Tanzil "simple" edition (standard orthography + diacritics) via
      fawazahmed0/quran-api, Hafs/Kufi numbering, 6236 ayat.  The edition
      prefixes the basmala to ayah 1 of every surah; it is stripped so the
      basmala is counted only in Al-Fatihah (where it IS ayah 1).
      Surah metadata (names, Meccan/Medinan) from risan/quran-json.

Usage:
  python3 quran_patterns.py                 # full run, writes results/
  python3 quran_patterns.py --perms 5000    # faster
  python3 quran_patterns.py --data path/to/quran.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_URL = "https://raw.githubusercontent.com/fawazahmed0/quran-api/1/editions/ara-quransimple.json"
DEFAULT_DATA = os.path.join(HERE, "corpus", "quran-simple.json")
META_PATH = os.path.join(HERE, "corpus", "surah_meta.json")
RESULTS_DIR = os.path.join(HERE, "results")

# --------------------------------------------------------------------------
# Reference metadata (standard Egyptian chronology of revelation).
# Index = revelation rank (1..114), value = surah number.
# --------------------------------------------------------------------------
REVELATION_ORDER = [
    96, 68, 73, 74, 1, 111, 81, 87, 92, 89, 93, 94, 103, 100, 108, 102, 107, 109,
    105, 113, 114, 112, 53, 80, 97, 91, 85, 95, 106, 101, 75, 104, 77, 50, 90, 86,
    54, 38, 7, 72, 36, 25, 35, 19, 20, 56, 26, 27, 28, 17, 10, 11, 12, 15, 6, 37,
    31, 34, 39, 40, 41, 42, 43, 44, 45, 46, 51, 88, 18, 16, 71, 14, 21, 23, 32, 52,
    67, 69, 70, 78, 79, 82, 84, 30, 29, 83, 2, 8, 3, 33, 60, 4, 99, 57, 47, 13, 55,
    76, 65, 98, 59, 24, 22, 63, 58, 49, 66, 64, 61, 62, 48, 5, 9, 110,
]
assert sorted(REVELATION_ORDER) == list(range(1, 115)), "revelation order must be a permutation"

# Surahs opening with disjoined letters (الحروف المقطعة)
MUQATTAAT = {2, 3, 7, 10, 11, 12, 13, 14, 15, 19, 20, 26, 27, 28, 29, 30, 31, 32,
             36, 38, 40, 41, 42, 43, 44, 45, 46, 50, 68}

FIB = {1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377}
PHI = (1 + 5 ** 0.5) / 2

# --------------------------------------------------------------------------
# Pre-registered semantic word pairs (declared BEFORE counting).
# Each entry: (label, stem_A, stem_B, famous_claim_or_None)
# Stems are matched after diacritic stripping + clitic stripping (rule STEM)
# and also as exact surface tokens (rule EXACT).  Both are reported.
# --------------------------------------------------------------------------
PREREG_PAIRS = [
    ("الدنيا / الآخرة",     "الدنيا",  "الآخرة",  "115 / 115"),
    ("الملائكة / الشياطين", "ملائك",   "شيطان",   "88 / 88 (الشيطان)"),
    ("الملائكة / الشياطين (جمع)", "ملائك", "شياطين", None),
    ("الحياة / الموت",      "حياة",    "موت",     "145 / 145"),
    ("الرجل / المرأة",      "رجل",     "امرأ",    "24 / 24"),
    ("البحر / البر",        "البحر",   "البر",    "32 / 13  (71.1% / 28.9%)"),
    ("الجنة / النار",       "الجنة",   "النار",   "77 / 77 (claimed by some)"),
    ("الصيف / الشتاء",      "الصيف",   "الشتاء",  "1 / 1"),
    ("الحر / البرد",        "الحر",    "البرد",   "4 / 4"),
    ("النفع / الفساد",      "نفع",     "فساد",    "50 / 50"),
    ("الصبر / الشدة",       "صبر",     "شدة",     "102 / 102"),
    ("الزكاة / البركة",     "زكاة",    "بركة",    "32 / 32"),
    ("الجهر / العلانية",    "جهر",     "علان",    "16 / 16"),
    ("إبليس / الاستعاذة",   "إبليس",   "استعذ",   "11 / 11"),
    ("الشمس / القمر",       "الشمس",   "القمر",   None),
    ("الليل / النهار",      "الليل",   "النهار",  None),
    ("السماء / الأرض",      "السماء",  "الأرض",   None),
    ("الإيمان / الكفر",     "إيمان",   "كفر",     None),
    ("الخير / الشر",        "الخير",   "الشر",    None),
    ("الذكر / الأنثى",      "الذكر",   "الأنثى",  None),
    ("الرحمة / العذاب",     "رحمة",    "عذاب",    None),
    ("يوم (365?) / شهر (12?)", "يوم",  "شهر",     "365 / 12"),
]

# --------------------------------------------------------------------------
# Text normalization
# --------------------------------------------------------------------------
_STRIP_RANGES = [
    (0x0610, 0x061A), (0x064B, 0x065F), (0x0670, 0x0670), (0x06D6, 0x06ED),
    (0x08D3, 0x08FF), (0x0640, 0x0640),  # tatweel
]
_STRIP_SET = {chr(c) for lo, hi in _STRIP_RANGES for c in range(lo, hi + 1)}
_MAP = {"ٱ": "ا"}  # ٱ -> ا


def strip_diacritics(s: str) -> str:
    out = []
    for ch in s:
        if ch in _STRIP_SET:
            continue
        if unicodedata.category(ch) == "Mn":
            continue
        out.append(_MAP.get(ch, ch))
    return "".join(out)


def light_normalize(tok: str) -> str:
    """Looser orthographic normalization (hamza/alef maqsura/ta marbuta)."""
    tok = re.sub("[أإآٱ]", "ا", tok)
    tok = tok.replace("ى", "ي").replace("ة", "ه").replace("ء", "")
    return tok


PROCLITICS = ["وبال", "فبال", "وكال", "فكال", "ولل", "فلل", "بال", "كال", "وال", "فال",
              "لل", "ال", "وب", "فب", "ول", "فل", "وك", "فك", "وس", "فس",
              "و", "ف", "ب", "ك", "ل", "س"]
ENCLITICS = ["كموها", "كموهم", "هما", "همو", "كما", "كمو", "هم", "هن", "كم", "كن",
             "نا", "ها", "ه", "ك", "ي"]


def strip_clitics(tok: str) -> str:
    """Rough, deterministic clitic stripping. Never shortens below 3 letters."""
    t = tok
    for p in PROCLITICS:
        if t.startswith(p) and len(t) - len(p) >= 3:
            t = t[len(p):]
            break
    for e in ENCLITICS:
        if t.endswith(e) and len(t) - len(e) >= 3:
            t = t[: -len(e)]
            break
    return t


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
BASMALA_TOKENS = ["بسم", "الله", "الرحمن", "الرحيم"]


def load_quran(path: str) -> list[dict]:
    """Return list of 114 dicts: id, name, type, verses=[{id,text}]."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"[data] downloading {DATA_URL} -> {path}")
        urllib.request.urlretrieve(DATA_URL, path)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)["quran"]
    with open(META_PATH, encoding="utf-8") as f:
        meta = {m["surah"]: m for m in json.load(f)}
    by_surah = defaultdict(list)
    for v in raw:
        by_surah[v["chapter"]].append(v)
    out = []
    stripped = 0
    for n in range(1, 115):
        verses = []
        for v in sorted(by_surah[n], key=lambda x: x["verse"]):
            text = v["text"]
            if v["verse"] == 1 and n != 1:
                raw_toks = text.split()
                if [strip_diacritics(t) for t in raw_toks[:4]] == BASMALA_TOKENS and len(raw_toks) > 4:
                    text, stripped = " ".join(raw_toks[4:]), stripped + 1
            verses.append({"id": v["verse"], "text": text})
        assert len(verses) == meta[n]["n_ayat"], (n, len(verses), meta[n]["n_ayat"])
        out.append({"id": n, "name": meta[n]["name"], "type": meta[n]["type"], "verses": verses})
    assert len(out) == 114
    assert stripped == 112, f"expected 112 basmala prefixes stripped, got {stripped}"
    return out


def build_frames(q):
    """Return (surah_df, verse_df, tokens_by_surah)."""
    rev_rank = {s: i + 1 for i, s in enumerate(REVELATION_ORDER)}
    srows, vrows, toks_by_surah = [], [], {}
    for s in q:
        n = s["id"]
        verses = s["verses"]
        toks_all = []
        for v in verses:
            raw = v["text"]
            clean = strip_diacritics(raw)
            toks = [t for t in clean.split() if t]
            toks_all.extend(toks)
            vrows.append({
                "surah": n, "ayah": v["id"], "n_words": len(toks),
                "n_letters": sum(len(t) for t in toks),
            })
        toks_by_surah[n] = toks_all
        srows.append({
            "surah": n, "name": s["name"], "type": s["type"],
            "meccan": int(s["type"] == "meccan"),
            "rev_order": rev_rank[n],
            "n_ayat": len(verses),
            "n_words": len(toks_all),
            "n_letters": sum(len(t) for t in toks_all),
            "muqattaat": int(n in MUQATTAAT),
        })
    sdf = pd.DataFrame(srows).set_index("surah")
    sdf["words_per_ayah"] = sdf.n_words / sdf.n_ayat
    sdf["letters_per_word"] = sdf.n_letters / sdf.n_words
    sdf["sum_no_ayat"] = sdf.index + sdf.n_ayat
    sdf["sum_even"] = (sdf.sum_no_ayat % 2 == 0).astype(int)
    sdf["prime_no"] = [int(is_prime(i)) for i in sdf.index]
    sdf["prime_ayat"] = sdf.n_ayat.map(lambda x: int(is_prime(x)))
    sdf["fib_ayat"] = sdf.n_ayat.isin(FIB).astype(int)
    vdf = pd.DataFrame(vrows)
    return sdf, vdf, toks_by_surah


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    r = int(n ** 0.5)
    for d in range(3, r + 1, 2):
        if n % d == 0:
            return False
    return True


def perm_pvalue(observed: float, null: np.ndarray, two_sided=True) -> float:
    null = np.asarray(null)
    if two_sided:
        c = np.mean(np.abs(null) >= abs(observed))
    else:
        c = np.mean(null >= observed)
    # add-one correction so p is never exactly 0
    return (c * len(null) + 1) / (len(null) + 1)


def bh_fdr(pvals: list[float]) -> list[float]:
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1.0)
    return out.tolist()


class Battery:
    """Collects every pre-registered test so they can be corrected together."""

    def __init__(self):
        self.rows = []

    def add(self, family, test, statistic, p, null_model, effect="", note=""):
        self.rows.append(dict(family=family, test=test, statistic=statistic,
                              p_raw=p, null_model=null_model, effect=effect, note=note))

    def finalize(self) -> pd.DataFrame:
        df = pd.DataFrame(self.rows)
        df["q_BH"] = bh_fdr(df.p_raw.tolist())
        df["p_bonferroni"] = np.minimum(df.p_raw * len(df), 1.0)
        return df.sort_values("p_raw").reset_index(drop=True)


# --------------------------------------------------------------------------
# 1. Correlation matrix
# --------------------------------------------------------------------------
def correlation_matrix(sdf: pd.DataFrame, rng, nperm, bat: Battery):
    cols = ["rev_order", "n_ayat", "n_words", "n_letters", "words_per_ayah",
            "letters_per_word", "meccan", "muqattaat"]
    m = sdf[cols].copy()
    m.insert(0, "surah_no", sdf.index.values)
    pear = m.corr(method="pearson")
    spear = m.corr(method="spearman")
    pear.to_csv(os.path.join(RESULTS_DIR, "corr_pearson.csv"), float_format="%.3f")
    spear.to_csv(os.path.join(RESULTS_DIR, "corr_spearman.csv"), float_format="%.3f")

    # permutation p-values for the correlations we pre-registered as interesting
    pairs = [("surah_no", "n_ayat"), ("surah_no", "words_per_ayah"),
             ("rev_order", "words_per_ayah"), ("rev_order", "n_ayat"),
             ("surah_no", "rev_order"), ("n_ayat", "words_per_ayah"),
             ("surah_no", "letters_per_word"), ("rev_order", "letters_per_word")]
    x_all = m.to_dict("series")
    for a, b in pairs:
        x, y = x_all[a].values.astype(float), x_all[b].values.astype(float)
        obs = stats.spearmanr(x, y).correlation
        null = np.array([stats.spearmanr(x, rng.permutation(y)).correlation for _ in range(nperm)])
        p = perm_pvalue(obs, null)
        bat.add("F1 correlation", f"spearman({a},{b})", round(obs, 3), p,
                "permute y across surahs", effect=f"rho={obs:.3f}")
    return pear, spear


# --------------------------------------------------------------------------
# 2. Famous parity identity (6236) — replicate + chance probability
# --------------------------------------------------------------------------
def parity_identity(sdf: pd.DataFrame, rng, nperm, bat: Battery):
    n = sdf.index.values
    a = sdf.n_ayat.values
    s = n + a
    even = s % 2 == 0
    res = {
        "n_even_group": int(even.sum()), "n_odd_group": int((~even).sum()),
        "sum_(no+ayat)_even_group": int(s[even].sum()),
        "sum_(no+ayat)_odd_group": int(s[~even].sum()),
        "sum_surah_no_even_group": int(n[even].sum()),
        "sum_ayat_even_group": int(a[even].sum()),
        "total_ayat": int(a.sum()), "total_surah_no": int(n.sum()),
    }
    # Chance model: permute ayah counts among surahs (multiset fixed).
    # Event of interest: even-group sum of (no+ayat) == total ayat (6236).
    # Also record the broader event "even-group sum equals ANY of the
    # 'iconic' totals" to expose the look-elsewhere effect.
    iconic = {int(a.sum()), int(n.sum()), 114, 6236 + 6555}
    hits_exact, hits_any, sums = 0, 0, []
    for _ in range(nperm):
        ap = rng.permutation(a)
        sp = n + ap
        ev = sp % 2 == 0
        val = int(sp[ev].sum())
        sums.append(val)
        hits_exact += (val == a.sum())
        hits_any += (val in iconic) or (int(n[ev].sum()) in iconic) or (int(ap[ev].sum()) in iconic)
    sums = np.array(sums)
    p_exact = (hits_exact + 1) / (nperm + 1)
    p_any = (hits_any + 1) / (nperm + 1)
    res.update({
        "null_mean_even_group_sum": float(sums.mean()),
        "null_sd_even_group_sum": float(sums.std()),
        "p_exact_hit_6236": p_exact,
        "p_any_iconic_hit": p_any,
        "analytic_p_point_mass": float(stats.norm.pdf(a.sum(), sums.mean(), sums.std())),
    })
    bat.add("F3 parity", "even-group sum(no+ayat) == total ayat (6236)", res["sum_(no+ayat)_even_group"],
            p_exact, "permute ayah counts", note=f"broader 'any iconic total' p={p_any:.4f}")
    # 57/57 split
    obs57 = abs(even.sum() - 57)
    null57 = np.array([abs(((n + rng.permutation(a)) % 2 == 0).sum() - 57) for _ in range(nperm)])
    bat.add("F3 parity", "even/odd split exactly 57/57", int(even.sum()),
            (np.sum(null57 <= obs57) + 1) / (nperm + 1), "permute ayah counts")
    # parity association chi-square (surah_no parity x ayat parity)
    tbl = pd.crosstab(n % 2, a % 2)
    chi2, p_chi, _, _ = stats.chi2_contingency(tbl)
    bat.add("F3 parity", "surah_no parity x ayat parity independence", round(chi2, 3), p_chi,
            "chi-square", note=str(tbl.values.tolist()))
    return res


# --------------------------------------------------------------------------
# 3. Primes
# --------------------------------------------------------------------------
def jitter_null(values: np.ndarray, rng, nperm, pred, width=3):
    """Local-density null: shift each value by U{-width..width}, keep >=1."""
    out = np.empty(nperm)
    for i in range(nperm):
        v = values + rng.integers(-width, width + 1, size=len(values))
        v = np.maximum(v, 1)
        out[i] = np.sum([pred(int(x)) for x in v])
    return out


def prime_analysis(sdf, vdf, rng, nperm, bat: Battery):
    n = sdf.index.values
    a = sdf.n_ayat.values
    res = {}
    # (i) how many ayah counts are prime vs local-density null
    obs = int(sdf.prime_ayat.sum())
    null = jitter_null(a, rng, nperm, is_prime)
    res["prime_ayat_count"] = obs
    res["prime_ayat_null_mean"] = float(null.mean())
    p = perm_pvalue(obs - null.mean(), null - null.mean())
    bat.add("F4 primes", "# surahs with prime ayah count", obs, p, "jitter ±3 null",
            effect=f"null mean {null.mean():.1f}")
    # (ii) prime surah number x prime ayah count association (permutation)
    both = int(((sdf.prime_no == 1) & (sdf.prime_ayat == 1)).sum())
    nullb = np.array([int(np.sum(sdf.prime_no.values * rng.permutation(sdf.prime_ayat.values)))
                      for _ in range(nperm)])
    res["prime_no_and_prime_ayat"] = both
    res["prime_no_and_prime_ayat_null_mean"] = float(nullb.mean())
    bat.add("F4 primes", "prime surah_no AND prime ayah count", both,
            perm_pvalue(both - nullb.mean(), nullb - nullb.mean()), "permute ayah counts")
    # (iii) prime word counts in first verses
    first = vdf[vdf.ayah == 1].n_words.values
    obs_f = int(sum(is_prime(int(x)) for x in first))
    nullf = jitter_null(first, rng, nperm, is_prime, width=2)
    res["prime_first_verse_wordcount"] = obs_f
    res["prime_first_verse_null_mean"] = float(nullf.mean())
    bat.add("F4 primes", "# first verses with prime word count", obs_f,
            perm_pvalue(obs_f - nullf.mean(), nullf - nullf.mean()), "jitter ±2 null")
    # (iv) Divisibility battery: how many of the global totals are divisible by k?
    totals = {"n_surahs": 114, "total_ayat": int(a.sum()), "total_words": int(sdf.n_words.sum()),
              "total_letters": int(sdf.n_letters.sum()), "sum_surah_no": int(n.sum()),
              "sum_no_plus_ayat": int((n + a).sum())}
    div = {k: [name for name, v in totals.items() if v % k == 0] for k in range(2, 31)}
    res["totals"] = totals
    res["divisibility_hits_by_k"] = {k: v for k, v in div.items() if v}
    # expected hits for a k: 6/k (each total independent uniform mod k); observed for 19:
    hits19 = len(div[19])
    p19 = 1 - stats.binom.cdf(hits19 - 1, 6, 1 / 19) if hits19 else 1.0
    bat.add("F4 primes", "totals divisible by 19 (out of 6 totals)", hits19, p19,
            "binomial(6, 1/19)", note="tested k=2..30 — see divisibility table")
    return res


# --------------------------------------------------------------------------
# 4. Fibonacci / golden ratio
# --------------------------------------------------------------------------
def fibonacci_analysis(sdf, rng, nperm, bat: Battery):
    res = {}
    a = sdf.n_ayat.values
    w = sdf.n_words.values
    obs = int(sdf.fib_ayat.sum())
    null = jitter_null(a, rng, nperm, lambda x: x in FIB)
    res["fib_ayat_count"] = obs
    res["fib_ayat_surahs"] = sdf.index[sdf.fib_ayat == 1].tolist()
    res["fib_ayat_null_mean"] = float(null.mean())
    bat.add("F5 fibonacci", "# surahs with Fibonacci ayah count", obs,
            perm_pvalue(obs - null.mean(), null - null.mean()), "jitter ±3 null")
    obs_w = int(np.sum([x in FIB for x in w]))
    nullw = jitter_null(w, rng, nperm, lambda x: x in FIB, width=10)
    res["fib_word_count"] = obs_w
    res["fib_word_null_mean"] = float(nullw.mean())
    bat.add("F5 fibonacci", "# surahs with Fibonacci word count", obs_w,
            perm_pvalue(obs_w - nullw.mean(), nullw - nullw.mean()), "jitter ±10 null")
    # Golden-ratio look-elsewhere demo: all ratios between "iconic" totals
    totals = {"114": 114, "ayat": int(a.sum()), "words": int(w.sum()),
              "letters": int(sdf.n_letters.sum()), "sum_no": 6555, "meccan": int(sdf.meccan.sum()),
              "medinan": int((1 - sdf.meccan).sum()), "muqattaat": int(sdf.muqattaat.sum()),
              "57": 57, "max_ayat": int(a.max()), "min_ayat": int(a.min())}
    hits = []
    n_ratios = 0
    for (ka, va), (kb, vb) in combinations(totals.items(), 2):
        for num, den, la, lb in ((va, vb, ka, kb), (vb, va, kb, ka)):
            n_ratios += 1
            r = num / den
            for name, target in (("phi", PHI), ("phi^2", PHI ** 2), ("1/phi", 1 / PHI), ("pi", math.pi), ("e", math.e)):
                if abs(r / target - 1) < 0.01:
                    hits.append((f"{la}/{lb}", round(r, 4), name))
    res["golden_ratio_hits_within_1pct"] = hits
    res["golden_ratio_ratios_tested"] = n_ratios * 5
    # expected hits ≈ ratios * P(|r/target -1|<1%) — for ratios spread over ~[0.01,100] in log space,
    # P ≈ 0.02/ln(1e4) per target ≈ 0.0022
    exp_hits = n_ratios * 5 * 0.02 / math.log(1e4)
    res["golden_ratio_expected_hits"] = round(exp_hits, 2)
    p = 1 - stats.poisson.cdf(len(hits) - 1, exp_hits) if hits else 1.0
    bat.add("F5 fibonacci", "iconic ratios within 1% of phi/pi/e", len(hits), p,
            "Poisson look-elsewhere", note=f"{n_ratios*5} ratios tested, expected {exp_hits:.2f}")
    return res


# --------------------------------------------------------------------------
# 5. Word frequencies & semantic pairs
# --------------------------------------------------------------------------
def word_tables(toks_by_surah):
    exact = Counter()
    stem = Counter()
    loose = Counter()
    for toks in toks_by_surah.values():
        for t in toks:
            exact[t] += 1
            stem[strip_clitics(t)] += 1
            loose[light_normalize(strip_clitics(t))] += 1
    return exact, stem, loose


def count_stem(counter: Counter, stem: str, mode: str) -> int:
    if mode == "EXACT":
        return counter.get(stem, 0)
    # STEM: token (after clitic strip) starts with stem
    return sum(c for w, c in counter.items() if w.startswith(stem))


def word_pair_analysis(toks_by_surah, rng, bat: Battery):
    exact, stem, loose = word_tables(toks_by_surah)
    vocab = pd.Series(exact).sort_values(ascending=False)
    vocab.to_csv(os.path.join(RESULTS_DIR, "word_freq_exact.csv"), header=["count"])
    pd.Series(stem).sort_values(ascending=False).to_csv(
        os.path.join(RESULTS_DIR, "word_freq_stem.csv"), header=["count"])
    res = {"n_tokens": int(vocab.sum()), "n_types_exact": int(len(vocab)),
           "n_types_stem": int(len(stem)), "hapax_fraction_exact": float((vocab == 1).mean())}

    # Zipf fit (log-log slope on top 2000 ranks)
    ranks = np.arange(1, min(2000, len(vocab)) + 1)
    slope, intercept, r, _, _ = stats.linregress(np.log(ranks), np.log(vocab.values[: len(ranks)]))
    res["zipf_exponent"] = round(-slope, 3)
    res["zipf_r2"] = round(r ** 2, 3)

    # How easy is it to find equal-frequency pairs?  For each frequency f,
    # C(n_f, 2) distinct word pairs share it.
    freq_of_freq = Counter(exact.values())
    equal_pairs_total = sum(math.comb(k, 2) for k in freq_of_freq.values())
    equal_pairs_ge5 = sum(math.comb(k, 2) for f, k in freq_of_freq.items() if f >= 5)
    equal_pairs_ge20 = sum(math.comb(k, 2) for f, k in freq_of_freq.items() if f >= 20)
    res["equal_frequency_word_pairs_total"] = equal_pairs_total
    res["equal_frequency_word_pairs_freq>=5"] = equal_pairs_ge5
    res["equal_frequency_word_pairs_freq>=20"] = equal_pairs_ge20

    # Empirical P(two random words with freq in band share the same freq)
    def p_equal_in_band(counter, lo, hi):
        vals = np.array([c for c in counter.values() if lo <= c <= hi])
        if len(vals) < 2:
            return float("nan")
        cnt = Counter(vals.tolist())
        same = sum(math.comb(k, 2) for k in cnt.values())
        return same / math.comb(len(vals), 2)

    bands = [(1, 1), (2, 5), (6, 20), (21, 60), (61, 200), (201, 10 ** 6)]
    res["p_equal_by_band_exact"] = {f"{lo}-{hi}": round(p_equal_in_band(exact, lo, hi), 4) for lo, hi in bands}
    res["p_equal_by_band_stem"] = {f"{lo}-{hi}": round(p_equal_in_band(stem, lo, hi), 4) for lo, hi in bands}

    # Pre-registered pairs
    exact_loose = Counter()
    for w, c in exact.items():
        exact_loose[light_normalize(w)] += c
    rows = []
    for label, sa, sb, claim in PREREG_PAIRS:
        na, nb = light_normalize(sa), light_normalize(sb)
        # EXACT: surface token == stem (after light normalization)
        ea, eb = exact_loose.get(na, 0), exact_loose.get(nb, 0)
        # STEM: clitic-stripped token starts with clitic-stripped stem
        ka, kb = strip_clitics(na), strip_clitics(nb)
        ta, tb = count_stem(loose, ka, "STEM"), count_stem(loose, kb, "STEM")
        # CONTAINS: any surface token containing the (clitic-stripped) stem — most generous
        ca = sum(c for w, c in exact_loose.items() if ka in w)
        cb = sum(c for w, c in exact_loose.items() if kb in w)
        rows.append(dict(pair=label, claim=claim or "", exact_A=ea, exact_B=eb, exact_match=int(ea == eb and ea > 0),
                         stem_A=ta, stem_B=tb, stem_match=int(ta == tb and ta > 0),
                         contains_A=ca, contains_B=cb, contains_match=int(ca == cb and ca > 0)))
    pdf = pd.DataFrame(rows)
    pdf.to_csv(os.path.join(RESULTS_DIR, "prereg_word_pairs.csv"), index=False)

    # Significance: for each rule, expected # of matches given the frequency band
    # of word A (band-conditional chance of equality), then Poisson-binomial ≈ binomial.
    def band_p(counter, f):
        for lo, hi in bands:
            if lo <= f <= hi:
                return p_equal_in_band(counter, lo, hi)
        return 0.0

    for rule, col_a, col_b, ctr in (("EXACT", "exact_A", "exact_B", exact), ("STEM", "stem_A", "stem_B", loose),
                                    ("CONTAINS", "contains_A", "contains_B", loose)):
        matches = int(pdf[f"{rule.lower()}_match"].sum())
        probs = [band_p(ctr, f) for f in pdf[col_a] if f > 0]
        # exact tail via Poisson-binomial DP
        dist = np.zeros(len(probs) + 1)
        dist[0] = 1.0
        for pr in probs:
            dist[1:] = dist[1:] * (1 - pr) + dist[:-1] * pr
            dist[0] *= (1 - pr)
        p_tail = float(dist[matches:].sum())
        bat.add("F6 word pairs", f"pre-registered pairs exact-equal frequency ({rule} rule)", matches, p_tail,
                "band-conditional Poisson-binomial", effect=f"expected {sum(probs):.2f} of {len(probs)}")
        res[f"prereg_matches_{rule}"] = matches
        res[f"prereg_expected_matches_{rule}"] = round(float(sum(probs)), 2)

    # Transparency: every surface form (exact token) that contains each stem,
    # so any counting rule can be audited.
    forms = {}
    for label, sa, sb, claim in PREREG_PAIRS:
        for st in (sa, sb):
            f = {w: c for w, c in exact.items() if strip_clitics(light_normalize(st)) in light_normalize(w)}
            forms[st] = dict(sorted(f.items(), key=lambda kv: -kv[1])[:60])
    with open(os.path.join(RESULTS_DIR, "word_forms.json"), "w", encoding="utf-8") as fh:
        json.dump(forms, fh, ensure_ascii=False, indent=1)

    # Data-driven counterpart: ALL pairs among the top-300 stem forms that
    # have exactly equal frequency ≥ 20 — to show how many "miracles" exist
    top = pd.Series(stem).sort_values(ascending=False)
    top = top[top >= 20]
    by_f = defaultdict(list)
    for w, c in top.items():
        by_f[int(c)].append(w)
    equal_sets = {f: ws for f, ws in by_f.items() if len(ws) >= 2}
    res["equal_freq_groups_stem_ge20"] = {str(f): ws[:8] for f, ws in sorted(equal_sets.items(), reverse=True)[:40]}
    res["n_equal_pairs_stem_ge20"] = int(sum(math.comb(len(ws), 2) for ws in equal_sets.values()))
    return res, pdf, vocab


# --------------------------------------------------------------------------
# 6. Discovery battery — structural hypotheses beyond the classic claims
# --------------------------------------------------------------------------
def discovery_battery(sdf, vdf, rng, nperm, bat: Battery):
    res = {}
    # ---- F2: local (adjacent-surah) similarity after removing global trend
    for order_col, label in (("surah_no", "mushaf order"), ("rev_order", "revelation order")):
        if order_col == "surah_no":
            idx = np.argsort(sdf.index.values)
        else:
            idx = np.argsort(sdf.rev_order.values)
        for var in ("n_words", "words_per_ayah"):
            y = np.log(sdf[var].values[idx])
            x = np.arange(len(y))
            # detrend with LOWESS-like cubic fit
            coef = np.polyfit(x, y, 3)
            resid = y - np.polyval(coef, x)
            obs = np.corrcoef(resid[:-1], resid[1:])[0, 1]
            null = np.array([np.corrcoef(r[:-1], r[1:])[0, 1] for r in (rng.permutation(resid) for _ in range(nperm))])
            p = perm_pvalue(obs, null)
            bat.add("F2 adjacency", f"lag-1 autocorr of detrended log {var} ({label})", round(obs, 3), p,
                    "permute detrended residuals", effect=f"r1={obs:.3f}")
            res[f"lag1_{var}_{order_col}"] = round(float(obs), 3)

    # ---- F2b: trend-preserving null — shuffle within consecutive blocks of 6
    # surahs.  The coarse length gradient survives, adjacency is destroyed.
    def block_shuffle(v, B):
        v = v.copy()
        for s in range(0, len(v), B):
            v[s:s + B] = rng.permutation(v[s:s + B])
        return v

    for var in ("words_per_ayah", "n_ayat", "letters_per_word"):
        y = np.log(sdf[var].values)  # mushaf order
        obs = np.corrcoef(y[:-1], y[1:])[0, 1]
        null = np.array([np.corrcoef(b[:-1], b[1:])[0, 1] for b in (block_shuffle(y, 6) for _ in range(nperm))])
        bat.add("F2 adjacency", f"lag-1 autocorr of log {var} vs block-6 shuffle (mushaf order)",
                round(obs, 3), perm_pvalue(obs - null.mean(), null - null.mean()),
                "shuffle within blocks of 6 (trend-preserving)", effect=f"r1={obs:.3f}, null {null.mean():.3f}")
        res[f"lag1_block_null_{var}"] = {"obs": round(float(obs), 3), "null_mean": round(float(null.mean()), 3)}

    # ---- F7: within-surah position effects of verse length
    # Is the FIRST verse / LAST verse systematically longer or shorter than the surah's other verses?
    def pos_stat(vd, which, exclude=frozenset()):
        zs = []
        for s, g in vd.groupby("surah"):
            if len(g) < 5 or s in exclude:
                continue
            L = g.n_words.values.astype(float)
            mu, sd = L.mean(), L.std(ddof=1)
            if sd == 0:
                continue
            v = L[0] if which == "first" else L[-1]
            zs.append((v - mu) / sd)
        return float(np.mean(zs)), len(zs)

    excl = MUQATTAAT | {1}
    for which in ("first", "last"):
        for exclude, tag in ((frozenset(), "all"), (frozenset(excl), "excl. muqatta'at+Fatiha")):
            obs, k = pos_stat(vdf, which, exclude)
            null = []
            for _ in range(nperm // 5):  # shuffle verse order within each surah
                shuffled = vdf.copy()
                shuffled["n_words"] = shuffled.groupby("surah")["n_words"].transform(lambda c: rng.permutation(c.values))
                null.append(pos_stat(shuffled, which, exclude)[0])
            p = perm_pvalue(obs, np.array(null))
            bat.add("F7 verse position", f"{which} verse length z-score ({tag}, {k} surahs)", round(obs, 3), p,
                    "shuffle verses within surah", effect=f"mean z={obs:.2f}")
            res[f"{which}_verse_mean_z_{tag}"] = round(obs, 3)
    # first-verse vs last-verse direct comparison (excl.): sign test across surahs
    fl = []
    for s, g in vdf.groupby("surah"):
        if len(g) >= 5 and s not in excl:
            fl.append(g.n_words.values[-1] - g.n_words.values[0])
    fl = np.array(fl)
    npos, nneg = int((fl > 0).sum()), int((fl < 0).sum())
    p_sign = stats.binomtest(npos, npos + nneg, 0.5).pvalue
    bat.add("F7 verse position", "last verse longer than first verse (sign test, excl. muqatta'at+Fatiha)",
            npos, p_sign, "binomial sign test", effect=f"{npos} longer / {nneg} shorter / {int((fl==0).sum())} equal")
    res["last_minus_first_words_median"] = float(np.median(fl))

    # within-surah verse-length trend: do verses get longer/shorter toward the end?
    rhos = []
    for s, g in vdf.groupby("surah"):
        if len(g) >= 10:
            rhos.append(stats.spearmanr(np.arange(len(g)), g.n_words.values).correlation)
    obs = float(np.mean(rhos))
    null = []
    for _ in range(nperm // 5):
        rr = []
        for s, g in vdf.groupby("surah"):
            if len(g) >= 10:
                rr.append(stats.spearmanr(np.arange(len(g)), rng.permutation(g.n_words.values)).correlation)
        null.append(np.mean(rr))
    bat.add("F7 verse position", f"mean within-surah spearman(verse index, length) over {len(rhos)} surahs",
            round(obs, 3), perm_pvalue(obs, np.array(null)), "shuffle verses within surah")
    res["within_surah_length_trend_mean_rho"] = round(obs, 3)
    res["within_surah_length_trend_n_positive"] = int(np.sum(np.array(rhos) > 0))

    # ---- F11: word-length chronology — is mean word length tied to revelation
    # order beyond the Meccan/Medinan split and beyond verse length?
    mec = sdf[sdf.meccan == 1]
    obs = stats.spearmanr(mec.rev_order, mec.letters_per_word).correlation
    null = np.array([stats.spearmanr(mec.rev_order, rng.permutation(mec.letters_per_word.values)).correlation
                     for _ in range(nperm)])
    bat.add("F11 word length", "spearman(rev_order, letters_per_word) within Meccan surahs only",
            round(obs, 3), perm_pvalue(obs, null), "permute within Meccan", effect=f"rho={obs:.3f} (n={len(mec)})")
    res["rev_order_vs_letters_per_word_meccan_only"] = round(float(obs), 3)
    med = sdf[sdf.meccan == 0]
    obs2 = stats.spearmanr(med.rev_order, med.letters_per_word).correlation
    res["rev_order_vs_letters_per_word_medinan_only"] = round(float(obs2), 3)

    def partial_spearman(x, y, z):
        rx = stats.rankdata(x); ry = stats.rankdata(y); rz = stats.rankdata(z)
        ex = rx - np.polyval(np.polyfit(rz, rx, 1), rz)
        ey = ry - np.polyval(np.polyfit(rz, ry, 1), rz)
        return np.corrcoef(ex, ey)[0, 1]

    x, y, z = sdf.rev_order.values, sdf.letters_per_word.values, sdf.words_per_ayah.values
    obs = partial_spearman(x, y, z)
    null = np.array([partial_spearman(x, rng.permutation(y), z) for _ in range(nperm)])
    bat.add("F11 word length", "partial spearman(rev_order, letters_per_word | words_per_ayah)",
            round(obs, 3), perm_pvalue(obs, null), "permute letters_per_word", effect=f"rho_partial={obs:.3f}")
    res["partial_rev_order_letters_per_word_given_verse_len"] = round(float(obs), 3)
    # tercile summary for the report
    terc = pd.qcut(sdf.rev_order, 3, labels=["early", "middle", "late"])
    res["letters_per_word_by_revelation_tercile"] = sdf.groupby(terc, observed=True).letters_per_word.mean().round(3).to_dict()

    # ---- F8: Meccan/Medinan & muqattaat contrasts
    for var in ("words_per_ayah", "n_ayat", "letters_per_word"):
        a = sdf[sdf.meccan == 1][var].values
        b = sdf[sdf.meccan == 0][var].values
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        eff = (np.median(b) - np.median(a))
        bat.add("F8 groups", f"Meccan vs Medinan: {var} (Mann-Whitney)", round(u, 1), p, "rank test",
                effect=f"median Mecc={np.median(a):.2f} Med={np.median(b):.2f}")
    for var in ("words_per_ayah", "n_ayat"):
        a = sdf[sdf.muqattaat == 1][var].values
        b = sdf[sdf.muqattaat == 0][var].values
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        bat.add("F8 groups", f"Muqatta'at vs others: {var} (Mann-Whitney)", round(u, 1), p, "rank test",
                effect=f"median Muq={np.median(a):.2f} other={np.median(b):.2f}")
    # muqattaat clustering in mushaf order: runs test on the 0/1 sequence
    seq = sdf.muqattaat.values
    runs = 1 + int(np.sum(seq[1:] != seq[:-1]))
    null = np.array([1 + int(np.sum(s[1:] != s[:-1])) for s in (rng.permutation(seq) for _ in range(nperm))])
    bat.add("F8 groups", "Muqatta'at surahs clustering (runs test, mushaf order)", runs,
            perm_pvalue(runs - null.mean(), null - null.mean()), "permute labels",
            effect=f"runs={runs}, null mean {null.mean():.1f}")
    res["muqattaat_runs"] = runs
    res["muqattaat_runs_null_mean"] = round(float(null.mean()), 2)
    # Meccan/Medinan clustering in mushaf order
    seq = sdf.meccan.values
    runs = 1 + int(np.sum(seq[1:] != seq[:-1]))
    null = np.array([1 + int(np.sum(s[1:] != s[:-1])) for s in (rng.permutation(seq) for _ in range(nperm))])
    bat.add("F8 groups", "Meccan/Medinan clustering (runs test, mushaf order)", runs,
            perm_pvalue(runs - null.mean(), null - null.mean()), "permute labels",
            effect=f"runs={runs}, null mean {null.mean():.1f}")

    # ---- F9: mirror symmetry surah i vs 115-i (on detrended residuals, else the
    # global length gradient alone produces a spurious negative correlation)
    y = np.log(sdf.n_words.values)
    x = np.arange(len(y))
    resid = y - np.polyval(np.polyfit(x, y, 3), x)
    obs = stats.spearmanr(resid[:57], resid[::-1][:57]).correlation
    null = np.array([stats.spearmanr(resid[:57], rng.permutation(resid)[:57]).correlation for _ in range(nperm)])
    bat.add("F9 mirror", "spearman(resid log words[i], resid log words[115-i])", round(obs, 3),
            perm_pvalue(obs, null), "permute detrended residuals")
    res["mirror_detrended_rho"] = round(float(obs), 3)

    # ---- F10: verse-length regularity — is the within-surah CV of verse length
    # lower than expected for a random partition of the surah's words into its ayat?
    # Null: multinomial split of n_words into n_ayat verses (uniform).  This is the
    # rhythmic/"saj'" regularity test.
    def cv_stat(vd):
        out = []
        for s, g in vd.groupby("surah"):
            if len(g) >= 5:
                L = g.n_words.values.astype(float)
                out.append(L.std(ddof=1) / L.mean())
        return float(np.median(out))

    obs = cv_stat(vdf)
    null = []
    for _ in range(nperm // 10):
        rows = []
        for s in sdf.index:
            k, W = int(sdf.at[s, "n_ayat"]), int(sdf.at[s, "n_words"])
            if k >= 5:
                cuts = np.sort(rng.choice(np.arange(1, W), size=k - 1, replace=False))
                parts = np.diff(np.concatenate([[0], cuts, [W]]))
                rows.append(pd.DataFrame({"surah": s, "n_words": parts}))
        null.append(cv_stat(pd.concat(rows)))
    null = np.array(null)
    bat.add("F10 regularity", "median within-surah CV of verse length", round(obs, 3),
            perm_pvalue(obs - null.mean(), null - null.mean()), "uniform random partition of words",
            effect=f"obs {obs:.3f} vs null {null.mean():.3f}")
    res["verse_length_cv_median"] = round(obs, 3)
    res["verse_length_cv_null_mean"] = round(float(null.mean()), 3)
    return res


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--perms", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20260912)
    args = ap.parse_args()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    rng = np.random.default_rng(args.seed)
    bat = Battery()

    q = load_quran(args.data)
    sdf, vdf, toks = build_frames(q)
    sdf.to_csv(os.path.join(RESULTS_DIR, "surah_matrix.csv"))
    vdf.to_csv(os.path.join(RESULTS_DIR, "verse_matrix.csv"), index=False)
    summary = {
        "n_surahs": 114, "total_ayat": int(sdf.n_ayat.sum()), "total_words": int(sdf.n_words.sum()),
        "total_letters": int(sdf.n_letters.sum()), "meccan": int(sdf.meccan.sum()),
        "medinan": int((1 - sdf.meccan).sum()),
    }
    mismatch = sdf[(sdf.rev_order <= 86) != (sdf.meccan == 1)].index.tolist()
    summary["meccan_label_vs_revorder_mismatch"] = mismatch
    print("[summary]", summary)

    out = {"summary": summary}
    pear, spear = correlation_matrix(sdf, rng, args.perms, bat)
    out["parity_identity"] = parity_identity(sdf, rng, args.perms, bat)
    out["primes"] = prime_analysis(sdf, vdf, rng, args.perms, bat)
    out["fibonacci"] = fibonacci_analysis(sdf, rng, args.perms, bat)
    wp, pdf, vocab = word_pair_analysis(toks, rng, bat)
    out["words"] = wp
    out["discovery"] = discovery_battery(sdf, vdf, rng, args.perms, bat)
    battery = bat.finalize()
    battery.to_csv(os.path.join(RESULTS_DIR, "battery.csv"), index=False)
    out["battery"] = battery.to_dict("records")
    with open(os.path.join(RESULTS_DIR, "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print("\n=== Spearman correlation matrix ===")
    print(spear.round(2))
    print("\n=== Parity identity (6236) ===")
    for k, v in out["parity_identity"].items():
        print(f"  {k}: {v}")
    print("\n=== Primes ===")
    for k, v in out["primes"].items():
        print(f"  {k}: {v}")
    print("\n=== Fibonacci / ratios ===")
    for k, v in out["fibonacci"].items():
        print(f"  {k}: {v}")
    print("\n=== Words ===")
    for k, v in wp.items():
        if k != "equal_freq_groups_stem_ge20":
            print(f"  {k}: {v}")
    print("\n=== Pre-registered pairs ===")
    print(pdf.to_string(index=False))
    print("\n=== Discovery ===")
    for k, v in out["discovery"].items():
        print(f"  {k}: {v}")
    print("\n=== BATTERY (all tests, BH-corrected) ===")
    print(battery[["family", "test", "statistic", "effect", "p_raw", "q_BH", "p_bonferroni"]].to_string(index=False))
    print(f"\nTests: {len(battery)} | q<0.05: {(battery.q_BH < 0.05).sum()} | Bonferroni<0.05: {(battery.p_bonferroni < 0.05).sum()}")


if __name__ == "__main__":
    main()
