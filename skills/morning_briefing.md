---
name: morning_briefing
description: Daily morning briefing for the user
requires_bridge: false
requires_llm: true
timeout: 30
input: shift_type
output_format: telegram_card
---

Generate a morning briefing for shift type {shift_type}:
1. Today's shift schedule and timing
2. Weather summary for Kuwait
3. Top 3 overnight news items (KSE related)
4. Any pending HA alerts or anomalies
5. Quick market outlook if trading day

Keep it concise, Arabic, friendly tone.
Use emoji for sections: 🕐 schedule, 🌤 weather, 📰 news, 🏠 home, 📊 market.
