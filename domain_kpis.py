"""
domain_kpis.py - Domain KPIs for Phase 7.5
TG command: /kpi
Unified snapshot of all domains
"""
import sqlite3
import logging
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

logger = logging.getLogger("domain_kpis")
LIFE = Path(__file__).parent / "data" / "life.db"

def _q1(sql, params=()):
    c = sqlite3.connect(str(LIFE))
    c.row_factory = sqlite3.Row
    r = c.execute(sql, params).fetchone()
    c.close()
    return dict(r) if r else {}

def _qn(sql, params=()):
    c = sqlite3.connect(str(LIFE))
    c.row_factory = sqlite3.Row
    r = c.execute(sql, params).fetchall()
    c.close()
    return [dict(x) for x in r]

def build_kpi_report():
    NL = chr(10)
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day_ago_utc = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    week_ago_utc = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = ["\U0001f4ca Domain KPIs", ""]

    # Health
    try:
        hl = _q1("SELECT COUNT(*) as c FROM health_logs WHERE log_date>=?", (week_ago,))
        ls = _q1("SELECT value,log_date FROM health_logs WHERE log_type='sleep' ORDER BY log_date DESC LIMIT 1")
        le = _q1("SELECT value,log_date FROM health_logs WHERE log_type='exercise' ORDER BY log_date DESC LIMIT 1")
        lw = _q1("SELECT value,log_date FROM health_logs WHERE log_type='weight' ORDER BY log_date DESC LIMIT 1")
        parts = [f"{hl.get('c',0)} logs/week"]
        if ls: parts.append(f"sleep:{ls['value']}h")
        if le: parts.append(f"exercise:{le['value']}min")
        if lw: parts.append(f"weight:{lw['value']}kg")
        lines.append(f"\U0001f4aa Health: {' | '.join(parts)}")
    except Exception:
        lines.append("\U0001f4aa Health: N/A")

    # Trading
    try:
        tw = _q1("SELECT COUNT(*) as c FROM trade_journal WHERE trade_date>=?", (week_ago,))
        ur = _q1("SELECT COUNT(*) as c FROM trade_journal WHERE action IN ('sell','close') AND (review IS NULL OR review='')")
        lines.append(f"\U0001f4c8 Trading: {tw.get('c',0)}/week | {ur.get('c',0)} unreviewed")
    except Exception:
        lines.append("\U0001f4c8 Trading: N/A")

    # TradingView
    try:
        tv24 = _q1("SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at>=?", (day_ago_utc,))
        tv7 = _q1("SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at>=?", (week_ago_utc,))
        tvs = _q1("SELECT COUNT(*) as c FROM tv_alert_events WHERE received_at>=? AND evaluation_label='strong_watch'", (week_ago_utc,))
        wl = _q1("SELECT COUNT(*) as c FROM tv_watchlists WHERE is_active=1")
        lines.append(f"\U0001f4e1 TV: {tv24.get('c',0)} today | {tv7.get('c',0)}/week | {tvs.get('c',0)} strong | WL:{wl.get('c',0)}")
    except Exception:
        lines.append("\U0001f4e1 TV: N/A")

    # Calendar
    try:
        ce = _q1("SELECT COUNT(*) as c FROM calendar_events WHERE start_time>=? AND start_time<?", (today+'T00:00:00', today+'T23:59:59'))
        cw = _q1("SELECT COUNT(*) as c FROM calendar_events WHERE start_time>=?", (week_ago+'T00:00:00',))
        lines.append(f"\U0001f4c5 Calendar: {ce.get('c',0)} today | {cw.get('c',0)}/week")
    except Exception:
        lines.append("\U0001f4c5 Calendar: N/A")

    # Tasks
    try:
        to = _q1("SELECT COUNT(*) as c FROM tasks WHERE status='active'")
        tod = _q1("SELECT COUNT(*) as c FROM tasks WHERE status='active' AND due_date IS NOT NULL AND due_date<?", (today,))
        td = _q1("SELECT COUNT(*) as c FROM tasks WHERE status='done' AND updated_at>=?", (week_ago,))
        lines.append(f"\U0001f4cb Tasks: {to.get('c',0)} open | {tod.get('c',0)} overdue | {td.get('c',0)} done/week")
    except Exception:
        lines.append("\U0001f4cb Tasks: N/A")

    # Relationships
    try:
        occ = _qn("SELECT title, occasion_date FROM occasions WHERE occasion_date>=? ORDER BY occasion_date LIMIT 3", (today,))
        lines.append(f"\U0001f465 Occasions: {len(occ)} upcoming")
        for o in occ[:2]:
            lines.append(f"  {o.get('occasion_date','')} {o.get('title','')}")
    except Exception:
        lines.append("\U0001f465 Occasions: N/A")

    # Expenses
    try:
        ew = _q1("SELECT COALESCE(SUM(amount),0) as s FROM expense_entries WHERE spent_at>=?", (week_ago,))
        em = _q1("SELECT COALESCE(SUM(amount),0) as s FROM expense_entries WHERE spent_at>=?", ((date.today()-timedelta(days=30)).isoformat(),))
        lines.append(f"\U0001f4b0 Expenses: {ew.get('s',0):.1f}/week | {em.get('s',0):.1f}/month KWD")
    except Exception:
        lines.append("\U0001f4b0 Expenses: N/A")

    # News
    try:
        nd = _q1("SELECT COUNT(*) as c FROM news_digests WHERE created_at>=?", (today+'T00:00:00',))
        nw = _q1("SELECT COUNT(*) as c FROM news_digests WHERE created_at>=?", (week_ago+'T00:00:00',))
        lines.append(f"\U0001f4f0 News: {nd.get('c',0)} today | {nw.get('c',0)}/week")
    except Exception:
        lines.append("\U0001f4f0 News: N/A")

    return NL.join(lines)

def handle_kpi():
    return build_kpi_report()
