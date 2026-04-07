# -*- coding: utf-8 -*-
"""
Smart Tips Engine — context-aware tips for the user.
Inspired by Claude Code's services/tips/ system.

Each tip has:
- content (Arabic text)
- is_relevant(context) — checks if tip applies NOW
- cooldown_hours — minimum hours between showing same tip
- category — trading / ha / system / general

Tips shown max 1 per Telegram session.
Selection: filter relevant -> remove recently shown -> pick oldest shown.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("tips_engine")


@dataclass
class Tip:
    id: str
    content: str
    category: str = "general"
    cooldown_hours: int = 24
    is_relevant: Callable = field(default_factory=lambda: (lambda ctx: True))
    last_shown: float = 0

    def can_show(self) -> bool:
        if self.cooldown_hours <= 0:
            return True
        elapsed_h = (time.time() - self.last_shown) / 3600
        return elapsed_h >= self.cooldown_hours


def _make_tips() -> list:
    tips = []

    # --- Trading tips ---
    tips.append(Tip(
        id="tip_analyze",
        content="\U0001f4a1 هل تعلم؟ أرسل /تحليل EQUIPMENT وأحلل لك السهم بالتفصيل مع Gemini",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_review",
        content="\U0001f4a1 أرسل /تقييم عشان أعطيك مراجعة إشارات أمس — شنو نجح وشنو فشل",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_momentum",
        content="\U0001f4a1 /موجة يعطيك الأسهم القوية الحين — بغض النظر عن نسبة النجاح",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_brain",
        content="\U0001f4a1 /brain يوريك شنو تعلمت من السوق — أوزان المؤشرات وأفضل الأنماط",
        category="trading",
        cooldown_hours=72,
    ))
    tips.append(Tip(
        id="tip_news",
        content="\U0001f4a1 /أخبار يجيب لك آخر أخبار البورصة + اقتصاد + تقنية من Gemini",
        category="trading",
        cooldown_hours=48,
    ))

    # --- System tips ---
    tips.append(Tip(
        id="tip_kairos",
        content="\U0001f4a1 KAIROS يراقب صحة النظام كل 5 دقائق ويرسل تنبيه لو شي طاح",
        category="system",
        cooldown_hours=168,
    ))
    tips.append(Tip(
        id="tip_dream",
        content="\U0001f4a1 كل ليلة الساعة 3 الفجر، نظام Dream ينظف الذاكرة من الملاحظات المكررة والقديمة",
        category="system",
        cooldown_hours=168,
    ))
    tips.append(Tip(
        id="tip_dashboard",
        content="\U0001f4a1 صفحة النظام بالداشبورد تبيّن: تعلم تلقائي، تحليل الأوامر، صحة السياق",
        category="system",
        cooldown_hours=168,
    ))

    # --- HA tips ---
    tips.append(Tip(
        id="tip_report",
        content="\U0001f4a1 /report يعطيك تقرير الصباح — الشفت + الطقس + حالة البيت",
        category="ha",
        cooldown_hours=48,
    ))

    # --- Context-dependent tips ---
    tips.append(Tip(
        id="tip_memory",
        content="\U0001f4a1 أنا أتعلم من محادثاتنا — كل ما تقول رأيك عن سهم أو جهاز، أسجله تلقائياً",
        category="general",
        cooldown_hours=72,
        is_relevant=lambda ctx: ctx.get("message_count", 0) >= 5,
    ))
    tips.append(Tip(
        id="tip_bridge_offline",
        content="\u26a0\ufe0f البريدج مو متصل — شغّل start_bridge.bat على الكمبيوتر عشان التحليل والرادار يشتغلون",
        category="system",
        cooldown_hours=4,
        is_relevant=lambda ctx: not ctx.get("bridge_online", True),
    ))

    return tips


class TipsEngine:
    def __init__(self):
        self._tips = _make_tips()
        self._shown_this_session = False

    def get_tip(self, context: dict = None) -> Optional[str]:
        """Get a relevant tip for the current context. Returns None if no tip or already shown."""
        if self._shown_this_session:
            return None

        context = context or {}

        # Filter: relevant + can_show (cooldown passed)
        candidates = [t for t in self._tips if t.is_relevant(context) and t.can_show()]
        if not candidates:
            return None

        # Pick: least recently shown (ensures variety)
        candidates.sort(key=lambda t: t.last_shown)
        tip = candidates[0]

        # Mark as shown
        tip.last_shown = time.time()
        self._shown_this_session = True

        logger.info(f"[tips] Showing tip: {tip.id}")
        return tip.content

    def reset_session(self):
        """Call at start of each new Telegram conversation/session."""
        self._shown_this_session = False

    def get_all_tips(self) -> list:
        """For dashboard/API — list all tips with status."""
        return [
            {
                "id": t.id,
                "content": t.content,
                "category": t.category,
                "cooldown_h": t.cooldown_hours,
                "can_show": t.can_show(),
                "last_shown": t.last_shown,
            }
            for t in self._tips
        ]
