"""
self_check.py — Post-response validation + tool outcome memory
ChatGPT Plan #3 (Self-check) + #13 (Tool outcome memory)
"""
import json, logging, time
from datetime import datetime

log = logging.getLogger("self_check")

# ═══ SELF-CHECK: Validate final answer before sending ═══

def validate_answer(answer: str, user_text: str, tools_used: list, tool_results: list = None) -> dict:
    """Check final answer for common issues. Returns {ok, issues, action}."""
    issues = []
    tool_results = tool_results or []
    
    # 1. Empty or too short
    if not answer or len(answer.strip()) < 3:
        issues.append("empty_response")
    
    # 2. Gave up despite having tool results
    gave_up_phrases = ["لا أعرف", "ما أقدر", "مو متأكد", "ما عندي", "لا أستطيع"]
    if any(p in answer for p in gave_up_phrases) and tools_used:
        # Check if any tool actually succeeded
        has_success = any(
            r and (
                (isinstance(r, dict) and not r.get("error")) or
                (isinstance(r, str) and '"error"' not in r[:200])
            )
            for r in tool_results
        )
        if has_success:
            issues.append("gave_up_despite_tools")
    
    # 3. Date context missing for date questions
    date_triggers = ["العيد", "رمضان", "الأربعين", "باجر", "عقبه", "متى"]
    date_words = ["هجري", "ميلادي", "تاريخ", "اليوم", "غد", "مارس", "أبريل", "شوال", "رمضان"]
    if any(t in user_text for t in date_triggers):
        if not any(w in answer for w in date_words) and len(answer) > 20:
            issues.append("missing_date_context")
    
    # 4. Entity confusion — mentioned wrong room/device
    # (light check: if user asked about specific room but answer mentions different one)
    
    # 5. Repetitive answer (same sentence repeated)
    sentences = [s.strip() for s in answer.split('.') if len(s.strip()) > 10]
    if len(sentences) > 2:
        unique = set(sentences)
        if len(unique) < len(sentences) * 0.6:
            issues.append("repetitive_content")
    
    # 6. Answer too long for simple question
    if len(user_text.split()) <= 4 and len(answer) > 500:
        issues.append("overly_verbose")
    
    # Decide action
    if not issues:
        return {"ok": True, "issues": [], "action": "send"}
    
    severity = len(issues)
    if severity >= 3 or "empty_response" in issues:
        return {"ok": False, "issues": issues, "action": "retry"}
    elif "gave_up_despite_tools" in issues:
        return {"ok": False, "issues": issues, "action": "retry"}
    else:
        return {"ok": True, "issues": issues, "action": "send_with_note"}


# ═══ TOOL OUTCOME MEMORY: Save tool execution results ═══

def save_tool_outcomes(user_text: str, tools_used: list, tool_results: list = None):
    """Save tool outcomes to structured memory for future learning."""
    if not tools_used:
        return
    
    try:
        import structured_memory as smem
    except ImportError:
        return
    
    tool_results = tool_results or []
    
    for i, tool_name in enumerate(tools_used):
        result_text = str(tool_results[i])[:200] if i < len(tool_results) else ""
        success = '"error"' not in result_text and '"blocked"' not in result_text
        
        if success:
            try:
                smem.save_lesson(
                    content=f"Tool {tool_name} succeeded for '{user_text[:50]}'",
                    category="tool_success",
                    key=f"ok_{tool_name}_{int(time.time())}",
                    tags=f"tool,{tool_name},success",
                )
            except Exception:
                pass
        if not success:
            # Save failed tool as lesson
            error_msg = ""
            try:
                err_data = json.loads(result_text) if result_text.startswith("{") else {}
                error_msg = err_data.get("error", result_text[:100])
            except:
                error_msg = result_text[:100]
            
            smem.save_lesson(
                content=f"Tool {tool_name} failed for '{user_text[:50]}': {error_msg}",
                category="tool_error",
                key=f"err_{tool_name}_{int(time.time())}",
                tags=f"tool,{tool_name},error",
            )
            log.info(f"Saved tool error lesson: {tool_name}")


# ═══ SESSION SUMMARY: Save episodic memory for complex interactions ═══

def save_session_summary(user_text: str, answer: str, tools_used: list, user_id: str = "default"):
    """Save session summary to structured memory (ChatGPT Plan #6)."""
    if len(tools_used) < 2:
        return
    
    try:
        import structured_memory as smem
    except ImportError:
        return
    
    summary = f"سأل '{user_text[:60]}' — استخدم {', '.join(set(tools_used))} — رد {len(answer)} حرف"
    smem.save_event(
        content=summary,
        category="session",
        key=f"sess_{int(time.time())}",
        tags="session," + ",".join(set(tools_used)),
    )
    log.info(f"Session summary saved: {len(tools_used)} tools")

