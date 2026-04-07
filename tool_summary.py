# -*- coding: utf-8 -*-
"""
Tool Usage Summary — generate short Arabic labels for tool operations.
Inspired by Claude Code's toolUseSummary system.

Uses Gemini Flash to generate a 5-10 word Arabic summary of what a tool did.
Non-critical: errors return None, never propagate.
"""

import json
import logging
import os
import urllib.request

logger = logging.getLogger("tool_summary")

GEMINI_KEY = ""
_gk = os.path.expanduser("~/.gemini_key")
if os.path.exists(_gk):
    GEMINI_KEY = open(_gk).read().strip()

SUMMARY_PROMPT = (
    "Generate a very short Arabic summary (5-10 words max) of this tool operation result. "
    "Focus on: what was analyzed, key finding, and verdict. "
    "Examples:\n"
    '- "حلل EQUIPMENT — RSI 41, انتظار"\n'
    '- "رادار: 3 إشارات جديدة، CLEANING أقوى"\n'
    '- "أخبار: 12 خبر جديد، 2 مهم"\n'
    '- "حالة المكيفات: 3 شغال، 1 طافي"\n'
    "Return ONLY the summary text, nothing else."
)

MIN_OUTPUT_LENGTH = 500  # only summarize long outputs


async def generate_summary(tool_name: str, tool_output: str) -> str | None:
    """Generate a 1-line Arabic summary of a tool operation.
    Returns None if output is short, no API key, or on any error."""
    if not tool_output or len(tool_output) < MIN_OUTPUT_LENGTH:
        return None
    if not GEMINI_KEY:
        return None

    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent?key=" + GEMINI_KEY
        )
        body = json.dumps({
            "contents": [{
                "role": "user",
                "parts": [{"text": f"{SUMMARY_PROMPT}\n\nTool: {tool_name}\nOutput:\n{tool_output[:1000]}"}],
            }],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 100,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=8)
        result = json.loads(resp.read().decode())

        # Extract text from response
        for c in result.get("candidates", []):
            for p in c.get("content", {}).get("parts", []):
                text = p.get("text", "").strip()
                if text and not p.get("thought", False):
                    # Validate: should be short
                    if len(text) < 200:
                        logger.debug(f"[summary] {tool_name}: {text}")
                        return text

        return None
    except Exception as e:
        logger.warning(f"[summary] Failed for {tool_name}: {e}")
        return None
