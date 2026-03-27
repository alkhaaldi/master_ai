"""
confidence_engine.py - Confidence-aware execution + response layers + uncertainty
ChatGPT Plan #10/#14/#16
"""
import logging

try:
    from feedback_learner import get_confidence_adjustment as _fb_adj
    _FB_OK = True
except Exception:
    _FB_OK = False
log = logging.getLogger("confidence")

def score_tool_call(tool_name, args, user_text=""):
    score = 0.0
    notes = []
    if tool_name == "ha_call_service":
        d = args.get("domain","")
        s = args.get("service","")
        sd = args.get("service_data",{})
        eid = sd.get("entity_id","")
        if d: score += 0.2
        if s: score += 0.2
        if eid and eid != "*": score += 0.4
        elif eid == "*":
            score += 0.1
            notes.append("wildcard")
        if s in ("unlock","open_cover") and len(user_text.strip()) < 8:
            score -= 0.2
            notes.append("short_destructive")
        if d == "climate":
            t = sd.get("temperature",0)
            if t and t > 23:
                return {"score": 0.05, "level": "low", "notes": ["temp_above_23_hard_block"]}
    elif tool_name == "ha_get_state":
        eid = args.get("entity_id","")
        score = 0.95 if (eid and eid != "*") else 0.7 if eid == "*" else 0.3
    elif tool_name == "ssh_run":
        cmd = args.get("cmd","").lower()
        if any(x in cmd for x in ["rm ","kill","shutdown","reboot","mkfs"]):
            score = 0.1
            notes.append("dangerous")
        elif any(x in cmd for x in ["cat ","grep ","ls ","df ","free ","uptime"]):
            score = 0.9
        else:
            score = 0.6
    elif tool_name.startswith("memory_"):
        score = 0.9
    elif tool_name in ("get_weather","get_shift","http_request"):
        score = 0.85
    else:
        score = 0.5
    # Apply feedback learning adjustment
    if _FB_OK:
        entity_id = ""
        if tool_name == "ha_call_service":
            entity_id = args.get("service_data", {}).get("entity_id", "")
        elif tool_name == "ha_get_state":
            entity_id = args.get("entity_id", "")
        if entity_id:
            adj = _fb_adj(entity_id)
            if adj != 0:
                score += adj
                notes.append(f"fb_adj:{adj:+.2f}")
    score = round(min(1.0,max(0.0,score)),2)
    level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
    return {"score": score, "level": level, "notes": notes}

def choose_response_layer(user_text, tools_used, scores=None):
    wc = len(user_text.split())
    scores = scores or []
    avg = sum(s.get("score",0.5) for s in scores) / max(len(scores),1)
    if wc <= 5 and avg >= 0.8 and len(tools_used) <= 1:
        return "brief"
    if wc >= 15 or avg < 0.5 or len(tools_used) >= 3:
        return "detailed"
    return "normal"

def get_uncertainty_prefix(level):
    return {"high":"","medium":"\u0627\u0644\u0623\u063a\u0644\u0628 ","low":"\u0645\u0648 \u0645\u062a\u0623\u0643\u062f \u0628\u0633 \u064a\u0645\u0643\u0646 "}.get(level,"")
