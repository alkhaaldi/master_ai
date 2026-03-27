# Journal Best/Worst Fix — Claude Code Task
# Date: 2026-03-27
# Priority: LOW

## PROBLEM
When there's only 1 trade (CLEANING), the journal shows it as BOTH "أفضل صفقة" AND "أسوأ صفقة".
This looks wrong to the user.

## FIX
In journal.html (the rendering code), add this logic:

1. If best_trade and worst_trade are the SAME trade (same id or symbol):
   - Show only "أفضل صفقة" (or only one card)
   - Hide the duplicate
   
2. If there are fewer than 2 closed trades:
   - Show "لا توجد بيانات كافية للمقارنة" instead of best/worst cards
   - OR show only the one trade without the best/worst label

3. The best/worst should ideally come from CLOSED trades only (not open ones)
   - If the API returns open trades as best/worst, the HTML should filter or label them as "(مفتوحة)"

## FILE TO EDIT
- /home/pi/master_ai/www/trading/journal.html
- This is an HTML-only fix (no backend change needed)

## ALSO CHECK
- Does /dashboard/journal return best_trade/worst_trade from open or closed trades?
- If from open trades, that's OK but label it properly
