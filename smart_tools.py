"""
smart_tools.py - Enhanced tool wrappers with richer results
ChatGPT Plan #11 (smarter tools) + #20 (distributed intelligence)

Wraps existing tools to add:
- Structured results with confidence
- Context enrichment (room names, entity labels)
- Aggregation support (all ACs, all lights in room)
- Why-matched explanations for memory search
"""
import json, logging
from datetime import datetime

log = logging.getLogger("smart_tools")

# ═══ ENHANCED MEMORY SEARCH ═══

def smart_memory_search(query, smem_module=None):
    """Enhanced memory search: returns matches + why + extracted entities."""
    if not smem_module:
        return {"results": [], "count": 0}
    
    results = smem_module.get_memories(search=query, limit=10)
    enhanced = []
    query_words = set(query.lower().split())
    
    for r in results:
        content_lower = r["content"].lower()
        matched_words = [w for w in query_words if w in content_lower]
        enhanced.append({
            "content": r["content"],
            "type": r.get("type", "fact"),
            "category": r.get("category", ""),
            "confidence": r.get("confidence", 0),
            "matched_on": matched_words,
            "relevance": round(len(matched_words) / max(len(query_words), 1), 2),
        })
    
    # Sort by relevance
    enhanced.sort(key=lambda x: x["relevance"], reverse=True)
    
    return {
        "results": enhanced[:5],
        "count": len(enhanced),
        "query": query,
        "best_match": enhanced[0]["content"] if enhanced else None,
    }


# ═══ ENHANCED SHIFT RESULT ═══

def enrich_shift_result(raw_result):
    """Add structured metadata to shift results."""
    try:
        data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except:
        return raw_result
    
    if isinstance(data, dict) and "shift" in data:
        shift_map = {
            "morning": "صباحي",
            "afternoon": "عصري", 
            "night": "ليلي",
            "off": "إجازة",
            "M": "صباحي",
            "A": "عصري",
            "N": "ليلي",
            "O": "إجازة",
        }
        data["shift_ar"] = shift_map.get(data.get("shift",""), data.get("shift",""))
        data["source"] = "schedule_table"
        data["confidence"] = 0.98
    
    return data


# ═══ ENHANCED HA STATE ═══

def enrich_ha_state(entity_id, raw_result, entity_map=None):
    """Add room name, friendly name, and device type to HA state results."""
    try:
        data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except:
        return raw_result
    
    if not isinstance(data, (list, dict)):
        return data
    
    # Try to load entity_map for room info
    room_map = {}
    if entity_map:
        room_map = entity_map
    else:
        try:
            with open("/home/pi/master_ai/entity_map.json", "r") as f:
                room_map = json.load(f)
        except:
            pass
    
    # For single entity result
    if isinstance(data, dict) and "state" in data:
        eid = data.get("entity_id", entity_id)
        data["_room"] = _find_room(eid, room_map)
        data["_domain"] = eid.split(".")[0] if "." in eid else ""
        data["_confidence"] = 0.95
    
    # For list of entities
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "entity_id" in item:
                eid = item["entity_id"]
                item["_room"] = _find_room(eid, room_map)
                item["_domain"] = eid.split(".")[0] if "." in eid else ""
    
    return data


def _find_room(entity_id, room_map):
    """Find which room an entity belongs to."""
    for room_name, room_data in room_map.items():
        # Handle list-of-strings format: ["entity_id=name", ...]
        if isinstance(room_data, list):
            for item in room_data:
                eid = item.split("=")[0].strip() if "=" in str(item) else str(item).strip()
                if eid == entity_id:
                    return room_name
            continue
        if isinstance(room_data, dict):
            entities = room_data.get("entities", [])
            if isinstance(entities, list):
                for e in entities:
                    eid = e.get("id","") if isinstance(e, dict) else str(e)
                    if eid == entity_id:
                        return room_name
            elif isinstance(entities, dict):
                for domain, elist in entities.items():
                    if isinstance(elist, list):
                        for e in elist:
                            eid = e.get("id","") if isinstance(e, dict) else str(e)
                            if eid == entity_id:
                                return room_name
    return ""


# ═══ TOOL RESULT SUMMARIZER ═══

def summarize_tool_result(tool_name, raw_result):
    """Create a brief human-readable summary of tool results."""
    try:
        data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except:
        return {"summary": str(raw_result)[:100], "type": "raw"}
    
    if isinstance(data, dict):
        if "error" in data:
            return {"summary": f"Error: {data['error']}", "type": "error", "ok": False}
        if "state" in data:
            return {
                "summary": f"{data.get('entity_id','?')}: {data['state']}",
                "type": "state",
                "ok": True,
            }
    
    if isinstance(data, list):
        return {
            "summary": f"{len(data)} items returned",
            "type": "list",
            "ok": True,
            "count": len(data),
        }
    
    return {"summary": str(data)[:100], "type": "unknown", "ok": True}
