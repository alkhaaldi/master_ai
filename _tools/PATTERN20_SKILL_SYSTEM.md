# Pattern #20: Skill/Plugin System
# Date: 2026-04-03
# For: Claude Code execution
# Last remaining pattern from Claude Code Source Analysis (21/21)

---

## What
Reusable analysis templates defined as .md files with YAML frontmatter.
Each "skill" = prompt template + configuration (requires_bridge, timeout, etc.)

## New Directory: skills/

## New File: skill_loader.py

```python
"""
Skill/Plugin loader for Master AI.
Loads .md skill files from skills/ directory.
Each skill has YAML frontmatter (metadata) + body (prompt template).

Usage:
    loader = SkillLoader("skills/")
    skill = loader.get("technical_analysis")
    prompt = skill.render(ticker="CLEANING")
"""

import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    name: str
    description: str = ""
    template: str = ""
    requires_bridge: bool = False
    requires_llm: bool = True
    timeout: int = 60
    input_vars: list = field(default_factory=list)
    output_format: str = "text"  # text, telegram_card, json
    source_path: str = ""

    def render(self, **kwargs) -> str:
        """Replace {var} placeholders with provided values."""
        prompt = self.template
        for key, val in kwargs.items():
            prompt = prompt.replace(f"{{{key}}}", str(val))
        return prompt

    def validate_inputs(self, **kwargs) -> tuple:
        """Check all required inputs are provided."""
        missing = [v for v in self.input_vars if v not in kwargs]
        if missing:
            return False, f"Missing inputs: {', '.join(missing)}"
        return True, ""


class SkillLoader:
    """Load and manage skill files from a directory."""

    def __init__(self, skills_dir: str = "skills/"):
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    def load_all(self) -> int:
        """Load all .md skill files. Returns count loaded."""
        if not os.path.isdir(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)
            logger.info(f"[skills] Created directory: {self.skills_dir}")
            return 0

        count = 0
        for f in os.listdir(self.skills_dir):
            if not f.endswith('.md'):
                continue
            try:
                skill = self._parse_file(os.path.join(self.skills_dir, f))
                if skill:
                    self._skills[skill.name] = skill
                    count += 1
            except Exception as e:
                logger.warning(f"[skills] Failed to load {f}: {e}")

        self._loaded = True
        logger.info(f"[skills] Loaded {count} skills from {self.skills_dir}")
        return count

    def _parse_file(self, path: str) -> Optional[Skill]:
        """Parse a .md skill file with YAML frontmatter."""
        with open(path, 'r', encoding='utf-8') as fh:
            content = fh.read()

        if not content.startswith('---'):
            return None

        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        meta = yaml.safe_load(parts[1])
        template = parts[2].strip()

        if not meta or 'name' not in meta:
            return None

        return Skill(
            name=meta['name'],
            description=meta.get('description', ''),
            template=template,
            requires_bridge=meta.get('requires_bridge', False),
            requires_llm=meta.get('requires_llm', True),
            timeout=meta.get('timeout', 60),
            input_vars=meta.get('input', '').split(',') if isinstance(meta.get('input'), str) else meta.get('input', []),
            output_format=meta.get('output_format', 'text'),
            source_path=path,
        )

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        if not self._loaded:
            self.load_all()
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        """List all available skills with metadata."""
        if not self._loaded:
            self.load_all()
        return [
            {
                "name": s.name,
                "description": s.description,
                "requires_bridge": s.requires_bridge,
                "input_vars": s.input_vars,
                "output_format": s.output_format,
            }
            for s in self._skills.values()
        ]
```

## Example Skill Files to Create:

### skills/technical_analysis.md
```markdown
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
```

### skills/morning_briefing.md
```markdown
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
```

### skills/stock_comparison.md
```markdown
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
Arabic output with table format.
```

## API Endpoint (add to dashboard_api.py):
```python
@app.get("/api/skills")
async def list_skills():
    loader = SkillLoader("skills/")
    return {"skills": loader.list_skills()}
```

## Integration with tg_intent_router.py:
```python
# When user sends /skill technical_analysis CLEANING
# or future: auto-detect "حلل سهم CLEANING" → skill lookup
loader = SkillLoader("skills/")
skill = loader.get("technical_analysis")
if skill:
    ok, err = skill.validate_inputs(ticker="CLEANING")
    if ok:
        prompt = skill.render(ticker="CLEANING")
        # Send prompt to LLM...
```

## Execution:
```
1. Create skills/ directory
2. Create skill_loader.py
3. Create 3 example skill .md files
4. Add /api/skills endpoint
5. quick_check.py + smoke_test.py
6. git commit -m "feat: add skill/plugin system with loader + 3 example skills (#20 Tier3)"
```
