#!/usr/bin/env python3
"""Generate PROJECT_STATE.md from server.py + live /system/context."""
import os, re, json, tempfile, urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(BASE, "server.py")
OUTPUT = os.path.join(BASE, "PROJECT_STATE.md")
ENV = os.path.join(BASE, ".env")


def _read_server():
    info = {}
    with open(SERVER) as f:
        src = f.read()
    m = re.search(r'VERSION\s*=\s*"([^"]+)"', src)
    info["version"] = m.group(1) if m else "unknown"
    m = re.search(r'SCHEMA_VERSION\s*=\s*"([^"]+)"', src)
    info["schema_version"] = m.group(1) if m else "unknown"
    info["has_ensure_schema"] = "def ensure_schema" in src
    info["has_schema_endpoints"] = "/schema" in src
    info["has_event_engine"] = "class EventEngine" in src
    info["has_plugins"] = "class PluginRegistry" in src
    info["line_count"] = src.count("\n") + 1
    eps = re.findall(r'@app\.(get|post|put|delete|patch)\("([^"]+)"', src)
    info["endpoints"] = [{"method": m.upper(), "path": p} for m, p in eps]
    return info


def _get_api_key():
    if os.path.exists(ENV):
        with open(ENV) as f:
            for line in f:
                if line.startswith("MASTER_AI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("MASTER_AI_API_KEY")


def _fetch_context(api_key):
    if not api_key:
        return None
    try:
        req = urllib.request.Request(
            "http://localhost:9000/system/context",
            headers={"X-API-Key": api_key},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [warn] Could not fetch /system/context: {e}")
        return None


def _build_md(info, ctx):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    a = lines.append

    a("# Master AI - Project State")
    a("")
    a(f"**Generated:** {ts}  ")
    a(f"**Version:** {info['version']}  ")
    a(f"**Schema:** {info['schema_version']}  ")
    a(f"**Lines:** {info['line_count']}  ")
    a("**URL:** https://ai.salem-home.com  ")
    a("**Service:** systemd master-ai on port 9000  ")
    a("**Platform:** Raspberry Pi 5 / FastAPI / Python 3  ")
    a("")

    a("## Architecture")
    a("")
    a("- Single-file FastAPI server (server.py)")
    a("- SQLite audit.db (WAL mode) for events, jobs, sessions, schema migrations")
    a("- data/policy.json for event engine risk thresholds")
    a(f"- Plugin system: {info.get('has_plugins', False)}")
    a(f"- Event Engine: {info.get('has_event_engine', False)}")
    a(f"- Schema migrations: {info.get('has_ensure_schema', False)}")
    a("")

    a(f"## Endpoints ({len(info['endpoints'])})")
    a("")
    for ep in sorted(info["endpoints"], key=lambda x: x["path"]):
        a(f"- {ep['method']} {ep['path']}")
    a("")

    if ctx:
        a("## Live System State")
        a("")
        if ctx.get("policy"):
            pol = ctx["policy"]
            th = pol.get("thresholds", {})
            a(f"**Policy:** v{pol.get('policy_version', '?')}, "
              f"thresholds: auto<={th.get('auto_max','?')}, "
              f"approval<={th.get('approval_max','?')}, "
              f"block>={th.get('block_min','?')}")
        if ctx.get("autonomy"):
            au = ctx["autonomy"]
            a(f"**Autonomy:** enabled={au.get('enabled')}, level={au.get('level')}, "
              f"allow_medium={au.get('allow_medium')}, allow_high={au.get('allow_high')}")
        if ctx.get("db"):
            db = ctx["db"]
            a(f"**DB:** {db.get('tables_count')} tables, WAL={db.get('wal_mode')}")
        if ctx.get("schema"):
            sc = ctx["schema"]
            lm = sc.get("last_migration", {})
            a(f"**Schema:** v{sc.get('schema_version')}, drift={sc.get('drift_count')}, "
              f"last_migration_ok={lm.get('ok') if lm else '?'}")
        if ctx.get("git"):
            g = ctx["git"]
            tags_str = ", ".join(g.get("tags", [])[:5])
            a(f"**Git:** branch={g.get('branch')}, commit={g.get('commit')}, "
              f"tags={tags_str}")
        if ctx.get("plugins"):
            p = ctx["plugins"]
            if isinstance(p, dict) and p.get("count") is not None:
                a(f"**Plugins:** {p['count']} registered")
        if ctx.get("warnings"):
            a(f"**Warnings:** {', '.join(ctx['warnings'])}")
        a("")

    a("## Deployment")
    a("")
    a("Git-based ONLY. Never use manual file uploads.")
    a("")
    a("1. Edit locally, commit, push to GitHub (alkhaaldi/master_ai)")
    a("2. SSH to RPi: `ssh pi@192.168.109.123`")
    a("3. Run: `~/master_ai/update.sh`")
    a("4. Rollback: `~/master_ai/deploy_tag.sh vX.X.X`")
    a("")

    a("## How to Use in New Chats")
    a("")
    a("Start any new AI conversation about this project with:")
    a("")
    a('> "Read /system/context from https://ai.salem-home.com before responding."')
    a("")
    a("Or if the API is down, provide this file as context.")
    a("")

    a("## Regenerate This File")
    a("")
    a("```bash")
    a("cd ~/master_ai && ./scripts/update_state.sh")
    a("```")

    return "\n".join(lines) + "\n"


def main():
    print(f"[generate_project_state] Reading {SERVER}...")
    info = _read_server()
    print(f"  version={info['version']}, endpoints={len(info['endpoints'])}")

    api_key = _get_api_key()
    ctx = _fetch_context(api_key)
    if ctx:
        print(f"  Live context loaded: v{ctx.get('version')}")
    else:
        print("  No live context (API key missing or server down)")

    md = _build_md(info, ctx)

    fd, tmp = tempfile.mkstemp(dir=BASE, suffix=".md.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(md)
        os.rename(tmp, OUTPUT)
        print(f"  Written {OUTPUT} ({len(md)} bytes)")
    except Exception as e:
        print(f"  [ERROR] Write failed: {e}")
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


if __name__ == "__main__":
    main()
