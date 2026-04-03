---
name: stock_comparison
description: Compare two or more stocks side by side
requires_bridge: true
requires_llm: true
timeout: 120
input: tickers
output_format: telegram_card
---

Compare these stocks: {tickers}

For each stock show:
- Current price + daily change %
- RSI + MACD signal
- EMA 9/21 trend
- Volume ratio
- Brain observations (if any)
- Personality summary

Then give overall verdict: which is stronger and why.
Arabic output with table format using monospace alignment.
