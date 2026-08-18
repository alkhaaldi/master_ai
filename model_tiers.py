"""
model_tiers.py — Single source of truth for LLM model names.

Three tiers, each overridable by environment variable:
  MAI_MODEL_CHEAP    — summarisation, extraction, triage
  MAI_MODEL_ROUTINE  — everyday chat, tool use, device control
  MAI_MODEL_DEEP     — complex reasoning, analysis (opt-in only)
"""

import os

MODEL_CHEAP   = os.getenv("MAI_MODEL_CHEAP",   "claude-haiku-4-5-20251001")
MODEL_ROUTINE = os.getenv("MAI_MODEL_ROUTINE",  "claude-sonnet-4-6")
MODEL_DEEP    = os.getenv("MAI_MODEL_DEEP",     "claude-opus-4-6")


def tiers() -> dict:
    """Return resolved tier names for reporting."""
    return {
        "cheap":   MODEL_CHEAP,
        "routine": MODEL_ROUTINE,
        "deep":    MODEL_DEEP,
    }
