---
name: technical_analysis
description: Full technical analysis for a KSE stock
requires_bridge: true
requires_llm: true
timeout: 90
input: ticker
output_format: telegram_card
---

Analyze {ticker} on Kuwait Stock Exchange using:
1. RSI (14) — overbought (>70) or oversold (<30)
2. MACD (12/26/9) — signal line crossover direction
3. EMA 9/21 — trend (bullish cross / bearish cross / neutral)
4. Volume — above or below 20-day average
5. Support/Resistance — nearest levels from daily chart
6. ADX — trend strength (>25 = trending)

Output as Arabic Telegram card with emoji indicators.
Use 📈 for bullish, 📉 for bearish, ➡️ for neutral.
Include: current price, verdict (شراء/بيع/انتظار), confidence %.
