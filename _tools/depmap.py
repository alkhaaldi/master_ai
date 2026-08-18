#!/usr/bin/env python3
"""
depmap.py — Dependency map generator for Master AI.

Static analysis only: no project module imports, no DB writes, no network calls,
no service interaction.

Usage:
    python3 _tools/depmap.py                           # regenerate all outputs
    python3 _tools/depmap.py --who-consumes THING      # query consumers

THING may be:
  - an endpoint path     e.g.  /dashboard/radar
  - an HTML page path    e.g.  www/trading/analysis.html
  - a Python symbol      e.g.  check_symbol
  - a Python module/file e.g.  stock_radar  or  stock_radar.py
  - a SQL table name     e.g.  audit_log
"""

import ast
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------------
PROJ_ROOT = Path(__file__).resolve().parent.parent   # master_ai/
TOOLS_DIR = PROJ_ROOT / "_tools"
WWW_DIR   = PROJ_ROOT / "www" / "trading"
HA_CONFIG = Path("/var/lib/homeassistant/homeassistant/configuration.yaml")
JSON_OUT  = TOOLS_DIR / "dependency_map.json"
MD_OUT    = TOOLS_DIR / "DEPENDENCY_MAP.md"

# Files that host FastAPI route definitions
FASTAPI_FILES = ["server.py", "dashboard_api.py"]

# Directories excluded from Python scanning, with stated reason
EXCLUDED_DIRS: dict[str, str] = {
    "venv":        "third-party packages (~20 k files), contains no project code",
    "_archive":    "deprecated/retired code, intentionally decoupled from live system",
    "__pycache__": "Python bytecode cache, not source",
    "backups":     "backup archives, not source code",
    "data":        "data files, not source code",
    "logs":        "log files, not source code",
    "audit":       "audit database directory, not source code",
}

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _rel(path: Path) -> str:
    """Relative path from project root, always with forward slashes."""
    try:
        return str(path.relative_to(PROJ_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _endpoint_of_url(url: str) -> str:
    """Extract /path from a full URL."""
    try:
        return urlparse(url).path or url
    except Exception:
        return url


# ---------------------------------------------------------------------------
# Scanner 1 — Python files list
# ---------------------------------------------------------------------------

def find_py_files() -> list[Path]:
    """All .py files in the project excluding configured directories."""
    result = []
    for f in PROJ_ROOT.rglob("*.py"):
        rel_parts = f.relative_to(PROJ_ROOT).parts
        if any(p in EXCLUDED_DIRS for p in rel_parts):
            continue
        if any(p.startswith(".") for p in rel_parts):
            continue
        result.append(f)
    return sorted(result)


def _resolve_module(name: str) -> str | None:
    """Map a module name to a project-relative path, or None if not local."""
    if not name:
        return None
    # Handle dotted names: from a.b import c → try a/b.py and a.py
    base = name.split(".")[0]
    candidates = [
        PROJ_ROOT / (base + ".py"),
        TOOLS_DIR / (base + ".py"),
        PROJ_ROOT / base / "__init__.py",
    ]
    for c in candidates:
        if c.exists():
            return _rel(c)
    return None


# ---------------------------------------------------------------------------
# Scanner 2 — Python imports via ast
# ---------------------------------------------------------------------------

def scan_python_imports(py_files: list[Path]) -> list[dict]:
    """Extract import edges. Skips files with syntax errors (reports them)."""
    edges = []
    parse_errors = []
    for fpath in py_files:
        src = fpath.read_text(errors="replace")
        try:
            tree = ast.parse(src, filename=str(fpath))
        except SyntaxError as e:
            parse_errors.append({"file": _rel(fpath), "error": str(e)})
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append({
                        "importer": _rel(fpath),
                        "imported_module": alias.name,
                        "resolved": _resolve_module(alias.name),
                        "line": node.lineno,
                        "names": [],
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [a.name for a in node.names]
                edges.append({
                    "importer": _rel(fpath),
                    "imported_module": module,
                    "resolved": _resolve_module(module),
                    "line": node.lineno,
                    "names": names,
                })
    return edges, parse_errors


# ---------------------------------------------------------------------------
# Scanner 3 — FastAPI route definitions
# ---------------------------------------------------------------------------

_ROUTE_RE = re.compile(
    r'@(?:app|router)\.'
    r'(?P<method>get|post|put|delete|patch|head|options|websocket)\s*\('
    r'\s*(?:["\'])(?P<path>[^"\']+)["\']',
    re.IGNORECASE,
)
_DEF_RE = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)\s*\(', re.MULTILINE)


def scan_routes(files: list[str]) -> list[dict]:
    """Extract (@app|@router).METHOD(path) decorators and the handler name."""
    routes = []
    for fname in files:
        fpath = PROJ_ROOT / fname
        if not fpath.exists():
            continue
        text = fpath.read_text(errors="replace")
        for m in _ROUTE_RE.finditer(text):
            line_num = text[: m.start()].count("\n") + 1
            after = text[m.end():]
            fn_match = _DEF_RE.search(after)
            # Only accept handler if it is within ~5 lines
            handler = None
            if fn_match:
                gap = text[m.end(): m.end() + fn_match.start()].count("\n")
                if gap <= 5:
                    handler = fn_match.group(1)
            routes.append({
                "method": m.group("method").upper(),
                "path": m.group("path"),
                "handler": handler,
                "file": fname,
                "line": line_num,
            })
    return routes


# ---------------------------------------------------------------------------
# Scanner 4 — HTML / JS fetch() calls
# ---------------------------------------------------------------------------

_FETCH_OPEN_RE = re.compile(r'fetch\s*\(\s*(?P<arg>.{1,200})')
_NAV_PATH_RE   = re.compile(r'path\s*:\s*"(/trading/[^"]+)"')
_HREF_TRADING_RE = re.compile(r'href=["\'](?P<url>/trading/[^"\']+)["\']')


def _classify_fetch_arg(arg: str) -> tuple[str | None, bool, str]:
    """
    Parse the first argument of a fetch() call.

    Returns (endpoint, is_dynamic, raw_pattern) where:
      endpoint     - the base path if statically determinable, else None
      is_dynamic   - True when the URL depends on a runtime variable
      raw_pattern  - first 120 chars of the raw argument (for the dynamic section)
    """
    raw = arg.strip()[:120]
    stripped = arg.strip()

    for q in ('"', "'", "`"):
        if stripped.startswith(q):
            close = stripped.find(q, 1)
            if close <= 0:
                return None, True, raw  # unclosed quote
            url = stripped[1:close]
            if not url.startswith("/"):
                return None, True, raw  # not an API path

            base = url.split("?")[0]  # drop query string

            # Template variable inside the string literal
            if "${" in url:
                return base.split("${")[0], True, raw

            # Concatenation immediately after the closing quote
            after = stripped[close + 1:].lstrip()
            if after.startswith("+"):
                return base, True, raw

            # Clean static URL
            return base, False, raw

    # Does not start with a string quote — fully dynamic (variable, expression…)
    return None, True, raw


def scan_html_requests(html_dir: Path) -> tuple[list[dict], list[dict]]:
    """
    Scan www/trading/ HTML files (and nav.js) for endpoint references.

    Returns (static_list, dynamic_list).
    """
    static: list[dict] = []
    dynamic: list[dict] = []

    for fpath in sorted(html_dir.glob("*.html")):
        lines = fpath.read_text(errors="replace").splitlines()
        for ln, line in enumerate(lines, 1):
            for m in _FETCH_OPEN_RE.finditer(line):
                endpoint, is_dyn, raw = _classify_fetch_arg(m.group("arg"))
                if is_dyn:
                    dynamic.append({
                        "page": _rel(fpath),
                        "line": ln,
                        "pattern": raw,
                        "note": "runtime variable — full endpoint not statically determinable",
                    })
                elif endpoint:
                    static.append({
                        "page": _rel(fpath),
                        "endpoint": endpoint,
                        "line": ln,
                        "kind": "fetch",
                    })

            # href links to /trading/* pages
            for m in _HREF_TRADING_RE.finditer(line):
                static.append({
                    "page": _rel(fpath),
                    "endpoint": m.group("url"),
                    "line": ln,
                    "kind": "href",
                })

    # nav.js — shared navigation links
    nav_js = html_dir / "nav.js"
    if nav_js.exists():
        nav_text = nav_js.read_text(errors="replace")
        for m in _NAV_PATH_RE.finditer(nav_text):
            ln = nav_text[: m.start()].count("\n") + 1
            static.append({
                "page": _rel(nav_js),
                "endpoint": m.group(1),
                "line": ln,
                "kind": "nav_link",
            })

    return static, dynamic


# ---------------------------------------------------------------------------
# Scanner 5 — Home Assistant REST sensors in configuration.yaml
# ---------------------------------------------------------------------------

_HA_RESOURCE_RE = re.compile(r"^\s*-\s*resource:\s*[\"']?(http[^\s\"']+)[\"']?")
_HA_UID_RE      = re.compile(r"^\s+unique_id:\s*(\S+)")
_HA_INTERVAL_RE = re.compile(r"^\s+scan_interval:\s*(\d+)")


def scan_ha_config(config_path: Path) -> list[dict]:
    """Extract REST sensor definitions that point at the master_ai service."""
    if not config_path.exists():
        return []

    sensors = []
    lines = config_path.read_text(errors="replace").splitlines()

    i = 0
    while i < len(lines):
        rm = _HA_RESOURCE_RE.match(lines[i])
        if rm:
            url = rm.group(1)
            if ":9000" in url or "master_ai" in url.lower():
                endpoint = _endpoint_of_url(url)
                uid = None
                interval = 60
                for j in range(i + 1, min(i + 25, len(lines))):
                    if _HA_RESOURCE_RE.match(lines[j]):
                        break
                    um = _HA_UID_RE.match(lines[j])
                    if um:
                        uid = um.group(1)
                    im = _HA_INTERVAL_RE.match(lines[j])
                    if im:
                        interval = int(im.group(1))
                sensors.append({
                    "sensor_id": uid or "unknown",
                    "url": url,
                    "endpoint": endpoint,
                    "scan_interval_sec": interval,
                    "file": str(config_path),
                    "line": i + 1,
                })
        i += 1

    return sensors


# ---------------------------------------------------------------------------
# Scanner 6 — SQL table usage in Python files
# ---------------------------------------------------------------------------

# Regex that captures the table name after SQL read keywords
_SQL_READ_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+[`\"']?([A-Za-z_]\w*)[`\"']?",
    re.IGNORECASE,
)
# Regex that captures table name after SQL write keywords
_SQL_WRITE_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?|"
    r"DELETE\s+FROM|DROP\s+TABLE(?:\s+IF\s+EXISTS)?)\s+[`\"']?([A-Za-z_]\w*)[`\"']?",
    re.IGNORECASE,
)
# Words that look like table names but are SQL keywords or Python builtins
_NOT_TABLES = frozenset({
    "select", "where", "from", "join", "table", "index", "into", "order",
    "group", "by", "limit", "on", "and", "or", "not", "is", "null", "as",
    "set", "values", "left", "right", "inner", "outer", "full", "cross",
    "self", "none", "true", "false", "int", "str", "list", "dict", "cls",
    "kwargs", "args", "async", "await", "return", "if", "else", "elif",
    "for", "while", "try", "except", "with", "pass", "raise", "def",
})


def _is_likely_table(name: str) -> bool:
    return name.lower() not in _NOT_TABLES and len(name) >= 3


def scan_sql(py_files: list[Path]) -> list[dict]:
    """Extract SQL read/write table references from Python source."""
    edges = []
    for fpath in py_files:
        lines = fpath.read_text(errors="replace").splitlines()
        for ln, line in enumerate(lines, 1):
            # Skip comment lines
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for m in _SQL_READ_RE.finditer(line):
                name = m.group(1)
                if _is_likely_table(name):
                    edges.append({
                        "file": _rel(fpath),
                        "line": ln,
                        "table": name.lower(),
                        "operation": "read",
                    })
            for m in _SQL_WRITE_RE.finditer(line):
                keyword = m.group(1).upper()
                name = m.group(2)
                if not _is_likely_table(name):
                    continue
                if "CREATE" in keyword:
                    op = "create"
                elif "INSERT" in keyword:
                    op = "write"
                elif "DELETE" in keyword or "DROP" in keyword:
                    op = "delete"
                else:
                    op = "write"  # UPDATE
                edges.append({
                    "file": _rel(fpath),
                    "line": ln,
                    "table": name.lower(),
                    "operation": op,
                })
    return edges


# ---------------------------------------------------------------------------
# Scanner 7 — Schedules (cron + asyncio startup tasks)
# ---------------------------------------------------------------------------

def scan_crontab() -> list[dict]:
    """Read the pi user's crontab and extract schedule entries."""
    for cmd in (["crontab", "-l", "-u", "pi"], ["crontab", "-l"]):
        try:
            out = subprocess.check_output(
                cmd, stderr=subprocess.DEVNULL, text=True, timeout=5
            )
            break
        except Exception:
            out = None
    if not out:
        return []

    schedules = []
    for ln, line in enumerate(out.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        schedule = " ".join(parts[:5])
        command = parts[5]
        fm = re.search(r"python3?\s+([\w./]+\.py)", command)
        target_file = fm.group(1) if fm else None
        schedules.append({
            "kind": "cron",
            "schedule": schedule,
            "command": command[:120],
            "target_file": target_file,
            "target_fn": None,
            "file": "crontab(pi)",
            "line": ln,
        })
    return schedules


_ASYNCIO_TASK_RE = re.compile(r"asyncio\.create_task\(\s*(\w+)\s*\(")


def scan_asyncio_tasks(py_files: list[Path]) -> list[dict]:
    """Find asyncio.create_task(fn()) calls — these are startup schedulers."""
    tasks = []
    for fpath in py_files:
        lines = fpath.read_text(errors="replace").splitlines()
        for ln, line in enumerate(lines, 1):
            for m in _ASYNCIO_TASK_RE.finditer(line):
                tasks.append({
                    "kind": "asyncio_startup_task",
                    "schedule": "on_startup",
                    "command": None,
                    "target_file": _rel(fpath),
                    "target_fn": m.group(1),
                    "file": _rel(fpath),
                    "line": ln,
                })
    return tasks


# ---------------------------------------------------------------------------
# Scanner 8 — Shell scripts in _tools/
# ---------------------------------------------------------------------------

def scan_shell_scripts() -> list[dict]:
    """Parse _tools/*.sh for python and systemctl calls."""
    scripts = []
    for fpath in sorted(TOOLS_DIR.glob("*.sh")):
        lines = fpath.read_text(errors="replace").splitlines()
        python_calls: list[dict] = []
        service_calls: list[dict] = []
        for ln, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if re.search(r"\bpython3?\b", s):
                python_calls.append({"line": ln, "cmd": s[:120]})
            if re.search(r"\bsystemctl\b", s):
                service_calls.append({"line": ln, "cmd": s[:120]})
        scripts.append({
            "file": _rel(fpath),
            "python_calls": python_calls,
            "service_calls": service_calls,
        })
    return scripts


# ---------------------------------------------------------------------------
# Reverse index
# ---------------------------------------------------------------------------

def build_reverse_index(data: dict) -> dict:
    """Build endpoint, table, and symbol consumer indexes."""

    # ── Endpoints ──────────────────────────────────────────────────────────
    ep_index: dict[str, dict] = {}

    for route in data["routes"]:
        path = route["path"]
        if path not in ep_index:
            ep_index[path] = {"defined": [], "consumers": []}
        ep_index[path]["defined"].append({
            "file": route["file"],
            "line": route["line"],
            "handler": route["handler"],
            "method": route["method"],
        })

    for req in data["html_requests"]:
        ep = req["endpoint"]
        if ep not in ep_index:
            ep_index[ep] = {"defined": [], "consumers": []}
        ep_index[ep]["consumers"].append({
            "kind": req["kind"],
            "file": req["page"],
            "line": req["line"],
        })

    for sensor in data["ha_sensors"]:
        ep = sensor["endpoint"]
        if ep not in ep_index:
            ep_index[ep] = {"defined": [], "consumers": []}
        ep_index[ep]["consumers"].append({
            "kind": "ha_sensor",
            "sensor_id": sensor["sensor_id"],
            "file": sensor["file"],
            "line": sensor["line"],
        })

    # ── SQL tables ─────────────────────────────────────────────────────────
    tbl_index: dict[str, dict] = {}

    for edge in data["sql_edges"]:
        t = edge["table"]
        if t not in tbl_index:
            tbl_index[t] = {"readers": [], "writers": [], "creators": [], "deleters": []}
        entry = {"file": edge["file"], "line": edge["line"]}
        op = edge["operation"]
        if op == "read":
            tbl_index[t]["readers"].append(entry)
        elif op == "write":
            tbl_index[t]["writers"].append(entry)
        elif op == "create":
            tbl_index[t]["creators"].append(entry)
        elif op == "delete":
            tbl_index[t]["deleters"].append(entry)

    # ── Python symbols (from X import Y) ───────────────────────────────────
    sym_index: dict[str, dict] = {}

    for edge in data["python_imports"]:
        if not edge["resolved"]:
            continue
        for name in edge["names"]:
            key = f"{edge['imported_module']}.{name}"
            if key not in sym_index:
                sym_index[key] = {"defined_in": edge["resolved"], "imported_by": []}
            sym_index[key]["imported_by"].append(
                {"file": edge["importer"], "line": edge["line"]}
            )

    # ── Zero consumers ─────────────────────────────────────────────────────
    zero_endpoints = [
        {"path": path, "defined": info["defined"]}
        for path, info in ep_index.items()
        if info["defined"] and not info["consumers"]
    ]
    tables_never_read = [
        t for t, info in tbl_index.items()
        if not info["readers"] and (info["writers"] or info["creators"])
    ]
    tables_never_written = [
        t for t, info in tbl_index.items()
        if not info["writers"] and not info["creators"] and info["readers"]
    ]

    return {
        "endpoints": ep_index,
        "tables": tbl_index,
        "python_symbols": sym_index,
        "zero_consumers": {
            "endpoints": sorted(zero_endpoints, key=lambda x: x["path"]),
            "tables_never_read": sorted(tables_never_read),
            "tables_never_written": sorted(tables_never_written),
        },
    }


# ---------------------------------------------------------------------------
# Query mode
# ---------------------------------------------------------------------------

COVERAGE_NOTE = """\
Coverage domains this scanner handles:
  endpoint     — FastAPI @app/@router decorators, HTML fetch(), HA REST sensors
  html_page    — nav.js path: entries, href=/trading/... attributes, /trading/{page} route
  python_sym   — "from X import Y" statements in Python files
  python_mod   — same import edges, grouped by module
  sql_table    — FROM/JOIN (read) and INSERT INTO/UPDATE/CREATE TABLE/DELETE FROM (write) in .py files
  schedule     — crontab(pi) entries and asyncio.create_task() startup calls
Not covered: Telegram command dispatch, dynamic endpoint construction, runtime module
  loading (importlib), HA template sensors that read attributes rather than URLs.\
"""


def who_consumes(data: dict, thing: str) -> int:
    """Print all known consumers of THING. Returns 0 if found, 1 if not."""
    rev = data["reverse_index"]
    found = False

    # ── Endpoint path (starts with /) ──────────────────────────────────────
    if thing.startswith("/"):
        norm = thing.rstrip("/") or "/"
        matches = {
            p: info
            for p, info in rev["endpoints"].items()
            if p.rstrip("/") == norm
        }
        if matches:
            found = True
            for path, info in matches.items():
                print(f"\n[ENDPOINT] {path}")
                if info["defined"]:
                    print("  Defined in:")
                    for d in info["defined"]:
                        print(f"    {d['file']}:{d['line']}  {d['method']} handler={d['handler']}")
                else:
                    print("  Defined in: (not found in scanned files)")
                if info["consumers"]:
                    print("  Consumers:")
                    for c in info["consumers"]:
                        if c["kind"] == "ha_sensor":
                            print(f"    [ha_sensor] {c['file']}:{c['line']}  sensor_id={c['sensor_id']}")
                        else:
                            print(f"    [{c['kind']}] {c['file']}:{c['line']}")
                else:
                    print("  Consumers: NONE detected")
                    print("  Note: dynamic callers (Telegram, runtime URL construction) are not covered.")

    # ── HTML / JS file ─────────────────────────────────────────────────────
    if ".html" in thing or ".js" in thing:
        found = True
        stem = Path(thing).stem                # e.g.  analysis
        nav_path = f"/trading/{stem}"
        print(f"\n[HTML PAGE] {thing}")
        print(f"  Served by: server.py  @app.get(\"/trading/{{page}}\") → {nav_path}")

        nav_refs = [
            r for r in data["html_requests"]
            if r.get("endpoint") == nav_path
        ]
        if nav_refs:
            print(f"  Nav / href references ({len(nav_refs)}):")
            for r in nav_refs:
                print(f"    [{r['kind']}] {r['page']}:{r['line']}")
        else:
            print("  Nav / href references: none found in scanned HTML and nav.js")

        # Dynamic fetch calls FROM this page
        dyn = [d for d in data["dynamic_requests"] if d["page"].endswith(thing.split("/")[-1])]
        if dyn:
            print(f"  Dynamic API calls from this page ({len(dyn)}):")
            for d in dyn:
                print(f"    line {d['line']}: {d['pattern']}")

        # Static fetch calls FROM this page
        sta = [r for r in data["html_requests"] if r["page"].endswith(thing.split("/")[-1]) and r["kind"] == "fetch"]
        if sta:
            print(f"  Static API calls from this page ({len(sta)}):")
            for s in sta:
                print(f"    {s['endpoint']}  (line {s['line']})")

    # ── Python symbol ──────────────────────────────────────────────────────
    # Match both "check_symbol" and "module.check_symbol"
    sym_matches = [
        (key, info)
        for key, info in rev["python_symbols"].items()
        if key.split(".")[-1] == thing or key == thing
    ]
    if sym_matches:
        found = True
        for key, info in sym_matches:
            print(f"\n[PYTHON SYMBOL] {key}")
            print(f"  Defined in: {info['defined_in']}")
            if info["imported_by"]:
                print(f"  Imported by ({len(info['imported_by'])}):")
                for imp in info["imported_by"]:
                    print(f"    {imp['file']}:{imp['line']}")
            else:
                print("  Imported by: NONE (no 'from X import <symbol>' found outside its module)")

    # ── Python module / file ───────────────────────────────────────────────
    mod_name = Path(thing).stem  # stock_radar.py → stock_radar
    mod_edges = [
        e for e in data["python_imports"]
        if e["imported_module"] == mod_name
        or e["imported_module"].split(".")[-1] == mod_name
        or e.get("resolved") == thing
    ]
    # Avoid double-printing if already covered by symbol match
    if mod_edges and (not sym_matches):
        found = True
        print(f"\n[PYTHON MODULE] {thing}  (as imported module)")
        for e in mod_edges:
            names_str = ", ".join(e["names"]) if e["names"] else "(entire module)"
            print(f"  {e['importer']}:{e['line']}  names=[{names_str}]")

    # ── SQL table ──────────────────────────────────────────────────────────
    thing_lower = thing.lower()
    if thing_lower in rev["tables"]:
        found = True
        info = rev["tables"][thing_lower]
        print(f"\n[SQL TABLE] {thing_lower}")
        for e in info.get("creators", []):
            print(f"  CREATE  {e['file']}:{e['line']}")
        for e in info.get("writers", []):
            print(f"  WRITE   {e['file']}:{e['line']}")
        for e in info.get("readers", []):
            print(f"  READ    {e['file']}:{e['line']}")
        for e in info.get("deleters", []):
            print(f"  DELETE  {e['file']}:{e['line']}")
        if not any(info.get(k) for k in ("creators", "writers", "readers", "deleters")):
            print("  (no references found)")

    if not found:
        print(f"\n[NOT FOUND] '{thing}' matched nothing in any scanned domain.")
        print()
        print(COVERAGE_NOTE)
        print()
        print("Possible reasons the query returned nothing:")
        print("  a) The name does not appear in the project under that exact spelling.")
        print("  b) References are constructed at runtime (dynamic import, string concat).")
        print(f"  c) The file lives in an excluded directory: {', '.join(EXCLUDED_DIRS)}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Output — JSON
# ---------------------------------------------------------------------------

def write_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))


# ---------------------------------------------------------------------------
# Output — Markdown
# ---------------------------------------------------------------------------

def write_markdown(data: dict, path: Path) -> None:
    meta = data["meta"]
    rev  = data["reverse_index"]
    zc   = rev["zero_consumers"]

    L: list[str] = []

    def h(level: int, text: str) -> None:
        L.append(f"\n{'#' * level} {text}\n")

    def row(*cells: str) -> str:
        return "| " + " | ".join(str(c) for c in cells) + " |"

    L.append("# Master AI — Dependency Map\n")
    L.append(f"**Generated:** {meta['generated_at']}  ")
    L.append(f"**Commit:** {meta['git_sha']}  ")
    L.append(f"**Elapsed:** {meta['elapsed_sec']:.2f} s  ")
    L.append("")

    h(2, "Scan coverage")
    L.append(row("Item", "Count"))
    L.append(row("---", "---"))
    for k, v in meta["counts"].items():
        L.append(row(k.replace("_", " "), v))
    L.append("")

    L.append("**Excluded directories**\n")
    for d, reason in meta["excluded_dirs"].items():
        L.append(f"- `{d}/` — {reason}")
    L.append("")

    if meta.get("parse_errors"):
        h(3, "Files with syntax errors (skipped)")
        for e in meta["parse_errors"]:
            L.append(f"- `{e['file']}`: {e['error']}")
        L.append("")

    # ── Routes ──
    h(2, "FastAPI routes")
    L.append(row("Method", "Path", "Handler", "File", "Line"))
    L.append(row("---", "---", "---", "---", "---"))
    for r in sorted(data["routes"], key=lambda x: (x["path"], x["method"])):
        L.append(row(r["method"], f"`{r['path']}`", r["handler"] or "?", r["file"], r["line"]))
    L.append("")

    # ── HA sensors ──
    h(2, "Home Assistant REST sensors")
    L.append(row("sensor_id", "endpoint", "interval"))
    L.append(row("---", "---", "---"))
    for s in data["ha_sensors"]:
        L.append(row(s["sensor_id"], f"`{s['endpoint']}`", f"{s['scan_interval_sec']}s"))
    L.append("")

    # ── Schedules ──
    h(2, "Schedules")
    L.append(row("kind", "schedule", "target"))
    L.append(row("---", "---", "---"))
    for s in data["schedules"]:
        target = s.get("target_fn") or s.get("target_file") or (s.get("command") or "")[:60]
        L.append(row(s["kind"], s["schedule"], target))
    L.append("")

    # ── Shell scripts ──
    h(2, "Shell scripts in _tools/")
    for sh in data["shell_scripts"]:
        L.append(f"\n**{sh['file']}**\n")
        for c in sh["python_calls"]:
            L.append(f"- python (line {c['line']}): `{c['cmd']}`")
        for c in sh["service_calls"]:
            L.append(f"- systemctl (line {c['line']}): `{c['cmd']}`")
    L.append("")

    # ── Endpoint reverse index ──
    h(2, "Endpoint reverse index")
    L.append(
        "_For each endpoint: where it is defined and every detected consumer._\n"
        "_Endpoints with no consumers are retire-safely candidates — but verify dynamic callers._\n"
    )
    for ep_path in sorted(rev["endpoints"]):
        info = rev["endpoints"][ep_path]
        cons = info["consumers"]
        defn = info["defined"]
        L.append(f"\n### `{ep_path}`\n")
        if defn:
            for d in defn:
                L.append(f"- **Defined:** `{d['file']}:{d['line']}` `{d['method']}` handler=`{d['handler']}`")
        else:
            L.append("- **Defined:** _(not in scanned files)_")
        if cons:
            for c in cons:
                if c["kind"] == "ha_sensor":
                    L.append(f"- **[{c['kind']}]** `{c['file']}:{c['line']}` sensor=`{c['sensor_id']}`")
                else:
                    L.append(f"- **[{c['kind']}]** `{c['file']}:{c['line']}`")
        else:
            L.append("- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)")
        L.append("")

    # ── Dynamic requests ──
    h(2, "Dynamic requests (unresolvable URLs)")
    L.append("_fetch() calls whose URL is built at runtime — base path noted where detectable._\n")
    if data["dynamic_requests"]:
        for d in data["dynamic_requests"]:
            L.append(f"- `{d['page']}:{d['line']}` — `{d['pattern']}`")
    else:
        L.append("_(none found)_")
    L.append("")

    # ── SQL reverse index ──
    h(2, "SQL table reverse index")
    for tname in sorted(rev["tables"]):
        info = rev["tables"][tname]
        L.append(f"\n### `{tname}`\n")
        for e in info.get("creators", []):
            L.append(f"- **CREATE** `{e['file']}:{e['line']}`")
        for e in info.get("writers", []):
            L.append(f"- **WRITE** `{e['file']}:{e['line']}`")
        for e in info.get("readers", []):
            L.append(f"- **READ** `{e['file']}:{e['line']}`")
        for e in info.get("deleters", []):
            L.append(f"- **DELETE** `{e['file']}:{e['line']}`")
        L.append("")

    # ── Python symbol index ──
    h(2, "Python symbol reverse index")
    L.append("_Symbols explicitly imported with `from X import Y` across file boundaries._\n")
    L.append(
        "Note: symbols called via `module.func()` after `import module` are tracked in the "
        "module import list above, not here.\n"
    )
    for sym in sorted(rev["python_symbols"]):
        info = rev["python_symbols"][sym]
        L.append(f"\n### `{sym}`\n")
        L.append(f"- **Defined in:** `{info['defined_in']}`")
        if info["imported_by"]:
            for imp in info["imported_by"]:
                L.append(f"- **Imported by:** `{imp['file']}:{imp['line']}`")
        else:
            L.append("- **Imported by:** NONE")
        L.append("")

    # ── Zero-consumer summary ──
    h(2, "Zero-consumer summary (retire-safely candidates)")
    L.append(
        "> If this list seems too short, check the dynamic requests section and the "
        "excluded directories — that is where scanner blind spots surface first.\n"
    )

    h(3, "Endpoints with no detected consumers")
    if zc["endpoints"]:
        for ep in zc["endpoints"]:
            L.append(f"\n**`{ep['path']}`**")
            for d in ep["defined"]:
                L.append(f"  - `{d['file']}:{d['line']}` handler=`{d['handler']}`")
    else:
        L.append("_(all scanned endpoints have at least one detected consumer)_")
    L.append("")

    h(3, "Tables never read (write-only)")
    if zc["tables_never_read"]:
        for t in zc["tables_never_read"]:
            L.append(f"- `{t}`")
    else:
        L.append("_(none)_")
    L.append("")

    h(3, "Tables never written (read-only)")
    if zc["tables_never_written"]:
        for t in zc["tables_never_written"]:
            L.append(f"- `{t}`")
    else:
        L.append("_(none)_")
    L.append("")

    path.write_text("\n".join(L))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # ── Query mode ──────────────────────────────────────────────────────────
    if "--who-consumes" in sys.argv:
        idx = sys.argv.index("--who-consumes")
        if idx + 1 >= len(sys.argv):
            print("Usage: python3 depmap.py --who-consumes THING", file=sys.stderr)
            return 1
        thing = sys.argv[idx + 1]
        if not JSON_OUT.exists():
            print(f"ERROR: {JSON_OUT} not found. Run depmap.py without --who-consumes first.",
                  file=sys.stderr)
            return 1
        data = json.loads(JSON_OUT.read_text())
        return who_consumes(data, thing)

    # ── Generate mode ───────────────────────────────────────────────────────
    t0 = time.monotonic()

    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJ_ROOT, text=True, stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except Exception:
        git_sha = "unknown"

    print(f"depmap: scanning {PROJ_ROOT}")

    py_files = find_py_files()
    print(f"  python files  : {len(py_files)}")
    html_files = sorted(WWW_DIR.glob("*.html"))
    print(f"  html files    : {len(html_files)}")

    print("  [1/7] python imports …")
    py_imports, parse_errors = scan_python_imports(py_files)

    print("  [2/7] fastapi routes …")
    routes = scan_routes(FASTAPI_FILES)

    print("  [3/7] html requests …")
    html_requests, dynamic_requests = scan_html_requests(WWW_DIR)

    print("  [4/7] ha config …")
    ha_sensors = scan_ha_config(HA_CONFIG)

    print("  [5/7] sql edges …")
    sql_edges = scan_sql(py_files)

    print("  [6/7] schedules …")
    schedules = scan_crontab() + scan_asyncio_tasks(py_files)

    print("  [7/7] shell scripts …")
    shell_scripts = scan_shell_scripts()

    elapsed = round(time.monotonic() - t0, 3)

    data: dict = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": git_sha,
            "elapsed_sec": elapsed,
            "counts": {
                "python_files_scanned": len(py_files),
                "html_files_scanned": len(html_files),
                "yaml_files_scanned": 1 if HA_CONFIG.exists() else 0,
                "routes_found": len(routes),
                "ha_sensors_found": len(ha_sensors),
                "python_import_edges": len(py_imports),
                "sql_edges": len(sql_edges),
                "schedules_found": len(schedules),
                "shell_scripts_found": len(shell_scripts),
                "dynamic_requests_found": len(dynamic_requests),
                "parse_errors": len(parse_errors),
            },
            "excluded_dirs": EXCLUDED_DIRS,
            "parse_errors": parse_errors,
        },
        "python_imports": py_imports,
        "routes": routes,
        "html_requests": html_requests,
        "ha_sensors": ha_sensors,
        "sql_edges": sql_edges,
        "schedules": schedules,
        "shell_scripts": shell_scripts,
        "dynamic_requests": dynamic_requests,
    }

    print("  building reverse index …")
    data["reverse_index"] = build_reverse_index(data)

    print(f"  writing {JSON_OUT} …")
    write_json(data, JSON_OUT)

    print(f"  writing {MD_OUT} …")
    write_markdown(data, MD_OUT)

    elapsed_total = round(time.monotonic() - t0, 3)
    # Update elapsed in the JSON with the full time including writes
    data["meta"]["elapsed_sec"] = elapsed_total
    write_json(data, JSON_OUT)

    print(f"\ndone in {elapsed_total:.2f}s")
    print(f"  JSON : {JSON_OUT}")
    print(f"  MD   : {MD_OUT}")
    print("\ncounts:")
    for k, v in data["meta"]["counts"].items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
