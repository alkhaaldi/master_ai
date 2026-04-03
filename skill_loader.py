"""
Skill/Plugin loader for Master AI (Pattern #20 Tier3).

Loads .md skill files from skills/ directory.
Each skill has YAML frontmatter (metadata) + body (prompt template).

Usage:
    loader = SkillLoader("skills/")
    skill = loader.get("technical_analysis")
    prompt = skill.render(ticker="CLEANING")
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("skill_loader")


@dataclass
class Skill:
    name: str
    description: str = ""
    template: str = ""
    requires_bridge: bool = False
    requires_llm: bool = True
    timeout: int = 60
    input_vars: list = field(default_factory=list)
    output_format: str = "text"
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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "requires_bridge": self.requires_bridge,
            "requires_llm": self.requires_llm,
            "timeout": self.timeout,
            "input_vars": self.input_vars,
            "output_format": self.output_format,
        }


def _parse_yaml_frontmatter(text: str) -> dict:
    """Parse YAML frontmatter without requiring PyYAML.
    Handles simple key: value pairs only."""
    result = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, _, val = line.partition(':')
            key = key.strip()
            val = val.strip()
            if val.lower() == 'true':
                result[key] = True
            elif val.lower() == 'false':
                result[key] = False
            elif val.isdigit():
                result[key] = int(val)
            else:
                result[key] = val
    return result


class SkillLoader:
    """Load and manage skill files from a directory."""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            skills_dir = os.path.join(os.path.dirname(__file__), "skills")
        self.skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}
        self._loaded = False

    def load_all(self) -> int:
        """Load all .md skill files. Returns count loaded."""
        if not os.path.isdir(self.skills_dir):
            os.makedirs(self.skills_dir, exist_ok=True)
            return 0

        count = 0
        for f in sorted(os.listdir(self.skills_dir)):
            if not f.endswith('.md'):
                continue
            try:
                skill = self._parse_file(os.path.join(self.skills_dir, f))
                if skill:
                    self._skills[skill.name] = skill
                    count += 1
            except Exception as e:
                logger.warning("[skills] Failed to load %s: %s", f, e)

        self._loaded = True
        logger.info("[skills] Loaded %d skills from %s", count, self.skills_dir)
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

        meta = _parse_yaml_frontmatter(parts[1])
        template = parts[2].strip()

        if not meta or 'name' not in meta:
            return None

        input_raw = meta.get('input', '')
        if isinstance(input_raw, str) and input_raw:
            input_vars = [v.strip() for v in input_raw.split(',')]
        elif isinstance(input_raw, list):
            input_vars = input_raw
        else:
            input_vars = []

        return Skill(
            name=meta['name'],
            description=meta.get('description', ''),
            template=template,
            requires_bridge=bool(meta.get('requires_bridge', False)),
            requires_llm=bool(meta.get('requires_llm', True)),
            timeout=int(meta.get('timeout', 60)),
            input_vars=input_vars,
            output_format=meta.get('output_format', 'text'),
            source_path=path,
        )

    def get(self, name: str) -> Optional[Skill]:
        if not self._loaded:
            self.load_all()
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        if not self._loaded:
            self.load_all()
        return [s.to_dict() for s in self._skills.values()]

    def reload(self) -> int:
        """Force reload all skills."""
        self._skills.clear()
        self._loaded = False
        return self.load_all()
