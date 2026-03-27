#!/usr/bin/env python3
"""Master AI V7 Benchmark Runner v3 — timeout fix + per-question timeout + retry"""
import json, asyncio, time, sys, os
import httpx
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("MASTER_AI_API_KEY", "")
BASE = "http://localhost:9000"

async def run_benchmark(max_q=None, cat_filter=None, timeout=120):
    with open("benchmark.json") as f:
        questions = json.load(f)
    
    if cat_filter:
        questions = [q for q in questions if q.get("category") == cat_filter]
    if max_q:
        questions = questions[:max_q]
    
    results = {"passed": 0, "failed": 0, "errors": 0, "total": len(questions), "details": [], "by_category": {}}
    
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        for i, test in enumerate(questions):
            q = test["q"]
            cat = test.get("category", "unknown")
            check = test.get("check", "non_empty")
            t0 = time.time()
            
            await asyncio.sleep(7)  # rate limit protection
            
            # Clear context before each question
            try:
                await client.post(f"{BASE}/chat/clear",
                    headers={"X-API-Key": API_KEY, "Authorization": f"Bearer {API_KEY}"},
                    params={"user_id": "api_ask"})
            except:
                pass
            
            try:
                # Use asyncio.wait_for for hard timeout (catches hung connections)
                async def do_ask():
                    r = await client.post(f"{BASE}/ask",
                        headers={"X-API-Key": API_KEY, "Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                        json={"message": q, "user_id": "api_ask"})
                    return r
                
                r = await asyncio.wait_for(do_ask(), timeout=timeout)
                d = r.json()
                resp = d.get("response", "")
                ms = round((time.time() - t0) * 1000)
                
                # Validate
                ok = validate_check(check, resp)
                
                if cat not in results["by_category"]:
                    results["by_category"][cat] = {"passed": 0, "failed": 0}
                results["by_category"][cat]["passed" if ok else "failed"] += 1
                if ok:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                
                results["details"].append({"cat": cat, "q": q, "ok": ok, "time_ms": ms, "len": len(resp), "preview": resp[:80]})
                icon = "OK" if ok else "FAIL"
                print(f"  [{i+1}/{len(questions)}] {icon} ({ms}ms) {q[:40]} -> {resp[:50]}")
                
            except (httpx.ReadTimeout, asyncio.TimeoutError):
                ms = round((time.time() - t0) * 1000)
                results["errors"] += 1
                if cat not in results["by_category"]:
                    results["by_category"][cat] = {"passed": 0, "failed": 0}
                results["by_category"][cat]["failed"] += 1
                results["details"].append({"cat": cat, "q": q, "ok": False, "time_ms": ms, "len": 0, "preview": f"TIMEOUT ({ms}ms)"})
                print(f"  [{i+1}/{len(questions)}] TIMEOUT ({ms}ms) {q[:40]}")
                continue
            except Exception as e:
                ms = round((time.time() - t0) * 1000)
                results["errors"] += 1
                if cat not in results["by_category"]:
                    results["by_category"][cat] = {"passed": 0, "failed": 0}
                results["by_category"][cat]["failed"] += 1
                results["details"].append({"cat": cat, "q": q, "ok": False, "time_ms": ms, "error": str(e)[:80], "preview": f"ERROR: {e}"})
                print(f"  [{i+1}/{len(questions)}] ERROR ({ms}ms) {q[:40]} -> {e}")
                continue
    
    # Summary
    total = results["total"]
    passed = results["passed"]
    pct = round(passed / total * 100, 1) if total else 0
    print(f"\n{'='*50}")
    print(f"  RESULTS: {passed}/{total} passed ({pct}%)")
    print(f"  Errors/Timeouts: {results['errors']}")
    print(f"{'='*50}")
    for cat, stats in sorted(results["by_category"].items()):
        ct = stats["passed"] + stats["failed"]
        cp = round(stats["passed"] / ct * 100) if ct else 0
        print(f"  {cat}: {stats['passed']}/{ct} ({cp}%)")
    
    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = f"benchmark_results_{ts}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out_file}")
    return results


def validate_check(check: str, resp: str) -> bool:
    """Validate response against check rule. Returns True if passed."""
    resp_lower = resp.lower().strip()
    
    if check == "non_empty":
        return len(resp_lower) > 5
    
    elif check.startswith("contains_any:"):
        words = check.split(":", 1)[1].split("|")
        # Case-insensitive match
        return any(w.lower() in resp_lower for w in words)
    
    elif check.startswith("contains_all:"):
        words = check.split(":", 1)[1].split("|")
        return all(w.lower() in resp_lower for w in words)
    
    elif check == "non_empty":
        return len(resp_lower) > 5
    
    else:
        # Unknown check type — treat as non_empty
        return len(resp_lower) > 5


if __name__ == "__main__":
    cat = None
    max_q = None
    timeout = 120
    
    for arg in sys.argv[1:]:
        if arg.startswith("--cat="):
            cat = arg.split("=", 1)[1]
        elif arg.startswith("--max="):
            max_q = int(arg.split("=", 1)[1])
        elif arg.startswith("--timeout="):
            timeout = int(arg.split("=", 1)[1])
    
    print(f"Master AI Benchmark Runner v3")
    print(f"  Timeout: {timeout}s | Category: {cat or 'all'} | Max: {max_q or 'all'}")
    print(f"{'='*50}")
    asyncio.run(run_benchmark(max_q=max_q, cat_filter=cat, timeout=timeout))
