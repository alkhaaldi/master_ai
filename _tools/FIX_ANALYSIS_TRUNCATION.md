# Fix: Gemini Analysis Text Truncated at 4000 chars
# Date: 2026-04-02
# Priority: HIGH

## Problem
Gemini analysis text is being truncated to exactly 4000 characters in the DB.
Both ALG and CLEANING show `analysis_length: 4000` — the text cuts off mid-sentence.

Example: ALG analysis ends with: `"entry": "الإغلاق فوق 1105", "stop_lo`
Example: CLEANING ends with: `خطة التداول المقترحة`

This means Gemini's full analysis (usually 5000-8000 chars) is being cut.

## Root Cause
Check `gemini_scanner.py` for any of these:
1. `gemini_analysis TEXT` column — is there a VARCHAR(4000) or similar limit?
2. When saving to DB, is the text being sliced: `analysis[:4000]`?
3. The Gemini API response parsing — is it cutting the response?
4. The `/api/analyze` endpoint — does it limit response text?

## Fix
1. Find the 4000 char limit and remove it (or increase to 50000)
2. The DB column should be `TEXT` (unlimited) not `VARCHAR(4000)`
3. Make sure the full Gemini response is saved

## Verification
After fix, trigger a manual scan and check:
```sql
SELECT symbol, LENGTH(gemini_analysis) FROM gemini_decisions ORDER BY id DESC LIMIT 5;
```
Should show lengths > 4000 for detailed analyses.

## Additional: Clean up JSON in analysis display
Some Gemini responses end with a JSON summary block like:
```json
{"signal": "شراء", "confidence": 75, ...}
```
The frontend already handles markdown formatting (###, **, *).
But raw JSON blocks look ugly. Frontend fix: strip trailing JSON blocks.
This is already handled by fmtAnalysis() on the frontend.
