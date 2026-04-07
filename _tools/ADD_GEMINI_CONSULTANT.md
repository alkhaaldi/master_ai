# Add Gemini Consultant — `ask_gemini.py`

## Overview
Create `ask_gemini.py` on the Windows PC (`C:\Users\MS1\Temp\`) as a Gemini consultant tool,
mirroring the structure of `ask_chatgpt.py`. Same flags, same logging pattern, same HA integration.

**Gemini's Role:** Research, news analysis, long document review, code review.  
**NOT for:** Trading analysis (hallucination risk — confirmed by user).

---

## Prerequisites
1. User gets Gemini API key from https://aistudio.google.com/apikey
2. Save to `C:\Users\MS1\.gemini_key` (single line, no trailing newline)

---

## Step 1: Create `C:\Users\MS1\Temp\ask_gemini.py`

Full script below. Key differences from ask_chatgpt.py:
- Uses Google Generative Language API (REST, no SDK needed)
- Model: `gemini-2.5-pro` primary, `gemini-2.0-flash` fallback
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- API key goes as query param `?key=...`
- Logs to `~/gemini_logs/conversations.md`

### SYSTEM_PROMPT
Same as ChatGPT but with Gemini-specific additions:

```python
SYSTEM_PROMPT = r"""You are a Home Assistant + Master AI expert consultant.
You have COMPLETE knowledge of this smart home system in Kuwait.
Owner: Salem, KNPC Unit 114 Controller, Shift A (AABBCCDD rotation).

PLATFORM: HA on RPi5, Music Assistant addon, Master AI v9+ (FastAPI, ~84 .py files, ~27K lines)
Network: /22, BE800 router, ES226GC-P PoE, 9 RAPs, RPi@192.168.109.123

BLUESOUND (Music Assistant ONLY, native disabled): SYNC GROUP
  LEADER: media_player.office_1_2 ("1st floor Speaker")
  FOLLOWERS: office_2_2, room_3_2, ground_floor
  ALL playback -> LEADER ONLY. Volume -> per-speaker.

CLIMATE (8 ACs Tuya): Guard max 23. Stubborn bedroom 21 (10PM-6AM).
158 lights, 28 covers, 15 fans, 18 media_players, 16 cameras, 36 automations

YOUR SPECIALTY: Research, news analysis, long document summaries, code review.
Do NOT give trading buy/sell advice — you tend to hallucinate numbers.
Give direct answers. Be concise. English unless asked Arabic."""
```

### API Call Function
```python
def ask_gemini_pro(question, context=""):
    """Gemini 2.5 Pro via REST API"""
    model = "gemini-2.5-pro"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    
    user_msg = question
    if context:
        user_msg = f"Live data:\n```\n{context[:8000]}\n```\n\nQuestion: {question}"
    
    body = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 4000
        }
    }).encode()
    
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    
    # Extract text from response
    answer = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            answer += part.get("text", "")
    
    usage = data.get("usageMetadata", {})
    in_t = usage.get("promptTokenCount", 0)
    out_t = usage.get("candidatesTokenCount", 0)
    return answer, in_t, out_t, model
```

### Fallback Function
```python
def ask_gemini_flash(question, context=""):
    """Fallback: Gemini 2.0 Flash"""
    model = "gemini-2.0-flash"
    # Same structure as above, just different model name
    # (copy the function, change model variable)
```

### Main Function + CLI
```python
def ask(question, context=""):
    try:
        answer, in_t, out_t, model = ask_gemini_pro(question, context)
    except Exception as e:
        print(f"[Gemini Pro failed: {e}] Falling back to Flash...", file=sys.stderr)
        try:
            answer, in_t, out_t, model = ask_gemini_flash(question, context)
        except Exception as e2:
            print(f"ERROR: Both models failed. {e2}"); sys.exit(1)
    
    print(answer)
    print(f"\n--- model: {model} | tokens: in={in_t} out={out_t} ---")
    _log(question, answer, context, {"in": in_t, "out": out_t}, model)

# CLI parsing — identical to ask_chatgpt.py
if __name__ == "__main__":
    # Same arg parsing: --ha, --file, --context, positional question
```

### Logging
```python
def _log(question, answer, context, tokens, model):
    log_dir = os.path.expanduser("~/gemini_logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "conversations.md"), "a", encoding="utf-8") as lf:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lf.write(f"\n---\n## {ts} [{model}]\n**Q:** {question[:500]}\n\n")
        if context: lf.write(f"**Context:** ({len(context)} chars)\n\n")
        lf.write(f"**A:**\n{answer}\n\n")
```

### HA Summary Function
Copy `ha_get()` and `get_ha_summary()` exactly from `ask_chatgpt.py` — identical code.

---

## Step 2: Test
```bash
# Basic test
python C:\Users\MS1\Temp\ask_gemini.py "what is 2+2"

# HA test  
python C:\Users\MS1\Temp\ask_gemini.py --ha "how many lights are on?"

# File test
python C:\Users\MS1\Temp\ask_gemini.py --file some_prompt.md
```

---

## Step 3: Add Telegram Command (Claude Code task)

In `tg_intent_router.py`, add handler for `/جيمني` or `/gemini`:

```python
# In the command routing section, add:
elif cmd in ['/جيمني', '/gemini']:
    question = text.replace(cmd, '', 1).strip()
    if not question:
        return "Usage: /جيمني <السؤال>"
    # Shell out to ask_gemini.py on PC? No — Gemini API is public,
    # so better to call it directly from RPi.
    # Option A: Copy ask_gemini.py to RPi and call locally
    # Option B: Add gemini_client.py to Master AI
```

### Recommended: Option B — Native Gemini in Master AI

Create `gemini_client.py` in Master AI root:

```python
"""Gemini API client for Master AI"""
import os, json, urllib.request

API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    key_file = os.path.expanduser("~/.gemini_key")
    if os.path.exists(key_file):
        API_KEY = open(key_file).read().strip()

def ask_gemini(question: str, model: str = "gemini-2.5-pro", 
               system: str = "", max_tokens: int = 4000) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    
    body = {"contents": [{"role": "user", "parts": [{"text": question}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens}}
    
    if system:
        body["system_instruction"] = {"parts": [{"text": system}]}
    
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    
    return "".join(
        part.get("text", "")
        for c in result.get("candidates", [])
        for part in c.get("content", {}).get("parts", [])
    )
```

Then in `tg_intent_router.py`:
```python
from gemini_client import ask_gemini

# In command handler:
elif cmd in ['/جيمني', '/gemini']:
    question = text.replace(cmd, '', 1).strip()
    if not question:
        return "Usage: /جيمني <السؤال>"
    try:
        answer = ask_gemini(question)
        return f"🔮 Gemini:\n{answer[:3500]}"
    except Exception as e:
        return f"❌ Gemini error: {e}"
```

---

## Step 4: Add `.gemini_key` to RPi
```bash
# SSH to RPi and create the key file:
echo "YOUR_GEMINI_API_KEY_HERE" > ~/.gemini_key
chmod 600 ~/.gemini_key
```

---

## Step 5: Update Memory / Preferences

After completion, update the user preferences to include:
- Gemini consultant: `C:\Users\MS1\Temp\ask_gemini.py` (Gemini 2.5 Pro + 2.0 Flash fallback)
- Gemini key at `~/.gemini_key` (both PC and RPi)
- Telegram: `/جيمني` command
- Gemini logs at `~/gemini_logs/conversations.md`
- Role: Research, news, docs, code review. NOT trading.

---

## Summary of Files to Create/Edit

| File | Location | Who |
|------|----------|-----|
| `ask_gemini.py` | `C:\Users\MS1\Temp\` | Claude Code or manual |
| `gemini_client.py` | Master AI root | Claude Code |
| `tg_intent_router.py` | Master AI root (edit) | Claude Code |
| `.gemini_key` | `~/.gemini_key` (PC + RPi) | User manual |

---

## Consultant Roles — Final Matrix

| Consultant | Model | Specialty | NOT for | Command |
|-----------|-------|-----------|---------|---------|
| Claude.ai | Opus 4.6 | Planning, design, HTML, trading, Pine | Backend execution | Chat |
| Claude Code | Opus 4.6 | Python, DB, git, bash, testing | Frontend design | Terminal |
| ChatGPT | GPT-5.4 | HA+Bluesound+Network, architecture | — | `/chatgpt` or script |
| **Gemini** | **2.5 Pro** | **Research, news, docs, code review** | **Trading numbers** | **`/جيمني` or script** |
