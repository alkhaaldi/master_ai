"""Phase C3: Ask vs Agent Router — classifies messages as chat or action.

Chat messages go to direct LLM (fast, no planning).
Action messages go to iterative_engine (planning + execution).
"""
import re, logging

logger = logging.getLogger("tg_router")

# Keywords that indicate an ACTION (smart home, system, etc.)
ACTION_KEYWORDS = {
    # Smart home verbs
    "\u0634\u063a\u0644", "\u0637\u0641\u064a", "\u0627\u0641\u062a\u062d", "\u0633\u0643\u0631",
    "\u0632\u064a\u062f", "\u0646\u0642\u0635", "\u0627\u0636\u0628\u0637",
    "\u0648\u0642\u0641", "\u0648\u0644\u0639", "\u062e\u0644\u0647", "\u062e\u0644\u064a\u0647",
    # Smart home nouns
    "\u0646\u0648\u0631", "\u0645\u0643\u064a\u0641", "\u0633\u062a\u0627\u0631\u0629",
    "\u0634\u0641\u0627\u0637", "\u0645\u0646\u0642\u064a", "\u062a\u0644\u0641\u0632\u064a\u0648\u0646",
    "\u0633\u0645\u0627\u0639\u0629", "\u0633\u0628\u0648\u062a", "\u0633\u062a\u0631\u064a\u0628",
    # System commands
    "restart", "backup", "deploy", "update", "ssh", "status",
    "\u062a\u0634\u062e\u064a\u0635", "\u0627\u0644\u0646\u0638\u0627\u0645",
    # Rooms
    "\u0627\u0644\u0645\u0639\u064a\u0634\u0629", "\u0627\u0644\u062f\u064a\u0648\u0627\u0646\u064a\u0629",
    "\u063a\u0631\u0641\u0629", "\u0627\u0644\u0645\u0637\u0628\u062e",
    "\u0627\u0644\u0627\u0633\u062a\u0642\u0628\u0627\u0644", "\u0627\u0644\u0645\u0627\u0633\u062a\u0631",
    # HA specific
    "entity", "automation", "scene", "\u0645\u0634\u0647\u062f",
}

# Patterns that indicate CHAT (general questions, greetings, etc.)
CHAT_PATTERNS = [
    r"^(\u0647\u0644\u0627|\u0645\u0631\u062d\u0628\u0627|\u0627\u0644\u0633\u0644\u0627\u0645|hi|hello|hey|\u0634\u0644\u0648\u0646\u0643|\u0643\u064a\u0641\u0643|\u0634\u062e\u0628\u0627\u0631\u0643)\\b",  # greetings
    r"^(\u0634\u0646\u0648|\u0644\u064a\u0634|\u0643\u064a\u0641|\u0645\u062a\u0649|\u0648\u064a\u0646|\u0645\u0646\u0648)\\s",  # question words
    r"(\u0634\u0646\u0648 \u0631\u0623\u064a\u0643|\u0634\u0644\u0648\u0646|\u0634\u0642\u0635\u062f\u0643|\u0639\u0637\u0646\u064a \u0641\u0643\u0631\u0629)",  # opinion/advice
    r"^(thank|\u0634\u0643\u0631\u0627|\u0645\u0634\u0643\u0648\u0631|\u062a\u0633\u0644\u0645|\u0627\u062d\u0633\u0646\u062a)",  # thanks
]

_chat_re = [re.compile(p, re.IGNORECASE) for p in CHAT_PATTERNS]


def classify_message(text: str) -> str:
    """Classify a Telegram message as 'chat' or 'action'.
    
    Returns: 'chat' for conversational, 'action' for smart home/system commands.
    """
    text_lower = text.strip().lower()
    words = set(text_lower.split())
    
    # If starts with /, it's always an action (already handled by commands)
    if text_lower.startswith("/"):
        return "action"
    
    # Check for action keywords
    action_hits = words & ACTION_KEYWORDS
    if action_hits:
        return "action"
    
    # Check for chat patterns
    for pat in _chat_re:
        if pat.search(text_lower):
            return "chat"
    
    # Short messages without action words → likely chat
    if len(words) <= 3 and not action_hits:
        return "chat"
    
    # Default: let the engine decide (action)
    return "action"
