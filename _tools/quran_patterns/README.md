# Quran Structural Pattern Search — `_tools/quran_patterns/`

A reproducible, statistically honest search for numerical / structural
patterns in the Quran text.  Every hypothesis is declared before the numbers
are looked at, every test carries an explicit null model, and all p-values are
corrected together for multiple comparisons (Benjamini-Hochberg + Bonferroni).

Findings and their significance: **`QURAN_PATTERNS_REPORT.md`**.

## Run

```bash
pip install pandas numpy scipy          # only deps
cd _tools/quran_patterns
python3 quran_patterns.py               # ~8 min, 20 000 permutations
python3 quran_patterns.py --perms 3000  # ~75 s
```

Outputs go to `results/`:

| file | content |
|---|---|
| `surah_matrix.csv` | per-surah: ayat, words, letters, revelation order, Meccan flag, parity/prime/Fibonacci flags |
| `verse_matrix.csv` | per-ayah word and letter counts |
| `corr_pearson.csv`, `corr_spearman.csv` | correlation matrices (surah no., revelation order, ayat, words, letters, verse length, word length, Meccan, muqatta'at) |
| `battery.csv` | every pre-registered test with raw p, BH q-value and Bonferroni p |
| `prereg_word_pairs.csv` | the 22 pre-registered semantic pairs under three counting rules |
| `word_forms.json` | every surface form matching each pair stem, with counts (audit trail) |
| `word_freq_exact.csv`, `word_freq_stem.csv` | full frequency tables |
| `results.json` | everything above plus the classic-claim replications |

## Data

* Text: Tanzil "simple" edition (standard orthography with diacritics) as
  packaged by `fawazahmed0/quran-api`, Hafs / Kufi numbering, 6236 ayat.
  That edition prefixes the basmala to ayah 1 of every surah; the loader strips
  it (112 times) so it is counted only in Al-Fatihah, where it is ayah 1.
* Metadata (`corpus/surah_meta.json`): surah names and Meccan/Medinan labels from
  `risan/quran-json`.  Revelation order is the standard Egyptian chronology,
  embedded in the script; the Meccan/Medinan labels agree with it for all 114.
* If `corpus/quran-simple.json` is missing the script downloads it.

## Word counting rules (applied uniformly, never per pair)

| rule | meaning |
|---|---|
| `EXACT` | surface token equals the form (after light normalization: hamza/alef variants, ة→ه, ى→ي) |
| `STEM` | clitic-stripped token *starts with* the clitic-stripped stem |
| `CONTAINS` | any token *contains* the stem (most generous) |

Diacritics, Quranic annotation marks and tatweel are removed before counting.
Clitic stripping is deterministic (proclitics و ف ب ك ل س ال and their
combinations; enclitic pronouns) and never shortens a token below 3 letters.

## Hypothesis families (pre-registered)

| family | what is tested | null model |
|---|---|---|
| F1 correlation | Spearman between surah no., revelation order, ayat, verse length, word length | permutation |
| F2 adjacency | do neighbouring surahs resemble each other beyond the global length gradient? | permute detrended residuals; trend-preserving block-6 shuffle |
| F3 parity | the 6236 identity, the 57/57 split, parity independence | permute ayah counts |
| F4 primes | prime ayah counts, prime × prime, prime first-verse lengths, divisibility of totals | ±k jitter null, binomial |
| F5 fibonacci | Fibonacci ayah / word counts, φ, π, e among 550 "iconic" ratios | jitter null, Poisson look-elsewhere |
| F6 word pairs | 22 semantic pairs, exact frequency equality | frequency-band-conditional Poisson-binomial |
| F7 verse position | opening / closing verse length, within-surah trend | shuffle verses within surah, sign test |
| F8 groups | Meccan vs Medinan, muqatta'at vs others, clustering in mushaf order | Mann-Whitney, runs test |
| F9 mirror | surah *i* vs surah 115−*i* (detrended) | permutation |
| F10 regularity | within-surah verse-length CV | uniform random partition |
| F11 word length | word length vs chronology, within Meccan only, partial on verse length | permutation |

Anything not in this table was not tested, and nothing was added after
seeing results.  Adding a family means adding it here first.
