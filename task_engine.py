import sqlite3, logging
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).parent / 'data' / 'life.db'

PRIORITY_MAP   = {'high': 3, 'med': 2, 'low': 1}
PRIORITY_LABEL = {3: '🔴 عالي', 2: '🟡 متوسط', 1: '🟢 منخفض'}
STATUS_LABEL   = {'todo': '⏳ قيد الانتظار', 'in_progress': '⚡ جاري', 'done': '✅ منجز', 'cancelled': '❌ ملغي'}
CATEGORY_LABEL = {'personal': '👤 شخصي', 'work': '🏭 عمل'}

_DDL = (
    'CREATE TABLE IF NOT EXISTS task_categories ('
    'id INTEGER PRIMARY KEY AUTOINCREMENT,'
    'name TEXT UNIQUE NOT NULL,'
    "color TEXT DEFAULT '#888888',"
    'created_at TEXT DEFAULT (datetime(' + chr(39) + 'now' + chr(39) + ')));'
    'INSERT OR IGNORE INTO task_categories (name, color) VALUES'
    " ('personal', '#4A90D9'), ('work', '#E8873A');"
    'CREATE TABLE IF NOT EXISTS tasks ('
    'id INTEGER PRIMARY KEY AUTOINCREMENT,'
    'title TEXT NOT NULL, description TEXT,'
    "category TEXT DEFAULT 'personal',"
    'priority INTEGER DEFAULT 2,'
    "status TEXT DEFAULT 'todo',"
    'due_date TEXT, due_time TEXT,'
    "source TEXT DEFAULT 'manual',"
    'source_ref TEXT, tags TEXT,'
    'created_at TEXT DEFAULT (datetime(' + chr(39) + 'now' + chr(39) + ')),'
    'updated_at TEXT DEFAULT (datetime(' + chr(39) + 'now' + chr(39) + ')),'
    'completed_at TEXT,'
    "created_by TEXT DEFAULT 'user');"
    'CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);'
    'CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);'
    'CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category);'
    'CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC);'
)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def init_tasks_db():
    with get_db() as conn:
        conn.executescript(_DDL)
    logger.info('[task_engine] DB ready')

def task_create(title, category='personal', priority='med', due_date=None,
                due_time=None, description=None, tags=None, source='manual', source_ref=None):
    p = PRIORITY_MAP.get(str(priority).lower(), 2)
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO tasks (title,description,category,priority,status,'
            'due_date,due_time,tags,source,source_ref) VALUES (?,?,?,?,' + chr(39) + 'todo' + chr(39) + ',?,?,?,?,?)',
            (title, description, category, p, due_date, due_time, tags, source, source_ref))
        tid = cur.lastrowid
    return task_get(tid)

def task_get(task_id):
    with get_db() as conn:
        row = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    return dict(row) if row else None

def task_update(task_id, title=None, status=None, priority=None, due_date=None,
                due_time=None, description=None, tags=None, category=None):
    fields = {}
    if title       is not None: fields['title']       = title
    if status      is not None:
        fields['status'] = status
        if status == 'done': fields['completed_at'] = datetime.now().isoformat()
    if priority    is not None: fields['priority']    = PRIORITY_MAP.get(str(priority).lower(), 2)
    if due_date    is not None: fields['due_date']    = due_date
    if due_time    is not None: fields['due_time']    = due_time
    if description is not None: fields['description'] = description
    if tags        is not None: fields['tags']        = tags
    if category    is not None: fields['category']    = category
    if not fields: return task_get(task_id)
    fields['updated_at'] = datetime.now().isoformat()
    clause = ', '.join(k + '=?' for k in fields)
    with get_db() as conn:
        conn.execute('UPDATE tasks SET ' + clause + ' WHERE id=?',
                     list(fields.values()) + [task_id])
    return task_get(task_id)

def task_done(task_id):   return task_update(task_id, status='done')

def task_delete(task_id):
    with get_db() as conn:
        cur = conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    return cur.rowcount > 0

def task_list(status=None, category=None, priority=None,
              due_today=False, due_overdue=False, limit=50):
    conds, params = [], []
    if status:
        conds.append('status=?'); params.append(status)
    else:
        conds.append("status NOT IN ('done','cancelled')")
    if category: conds.append('category=?');  params.append(category)
    if priority: conds.append('priority=?');  params.append(PRIORITY_MAP.get(str(priority).lower(), 2))
    td = date.today().isoformat()
    if due_today:   conds.append('due_date=?');                            params.append(td)
    if due_overdue: conds.append('due_date < ? AND due_date IS NOT NULL'); params.append(td)
    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''
    sql = ('SELECT * FROM tasks ' + where +
           ' ORDER BY priority DESC, due_date ASC NULLS LAST, created_at DESC LIMIT ?')
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def task_search(query, limit=20):
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM tasks WHERE (title LIKE ? OR description LIKE ?)'
            " AND status NOT IN ('done','cancelled') ORDER BY priority DESC LIMIT ?",
            ('%' + query + '%', '%' + query + '%', limit)).fetchall()
    return [dict(r) for r in rows]

def task_stats():
    with get_db() as conn:
        by_status = {r['status']: r['cnt'] for r in
            conn.execute('SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status').fetchall()}
        by_cat = {r['category']: r['cnt'] for r in
            conn.execute('SELECT category, COUNT(*) as cnt FROM tasks '
                "WHERE status NOT IN ('done','cancelled') GROUP BY category").fetchall()}
        td = date.today().isoformat()
        overdue   = conn.execute('SELECT COUNT(*) as cnt FROM tasks '
            "WHERE due_date<? AND status NOT IN ('done','cancelled')", (td,)).fetchone()['cnt']
        due_today = conn.execute('SELECT COUNT(*) as cnt FROM tasks '
            "WHERE due_date=? AND status NOT IN ('done','cancelled')", (td,)).fetchone()['cnt']
    return {'by_status': by_status, 'by_category': by_cat,
            'overdue': overdue, 'due_today': due_today,
            'total_active': sum(v for k,v in by_status.items() if k not in ('done','cancelled'))}

def _fmt_task(t):
    pri    = PRIORITY_LABEL.get(t['priority'], '')
    status = STATUS_LABEL.get(t['status'], t['status'])
    cat    = CATEGORY_LABEL.get(t['category'], t['category'])
    due    = (' | 📅 ' + t['due_date']) if t.get('due_date') else ''
    return (pri + ' [' + str(t['id']) + '] ' + t['title'] +
            chr(10) + '   ' + status + ' | ' + cat + due)

def format_task_list(tasks, title='📋 المهام'):
    if not tasks:
        return title + chr(10) + chr(10) + 'ما فين مهام ✅'
    lines = ['*' + title + '*' + chr(10)]
    for t in tasks:
        lines.append(_fmt_task(t))
    return chr(10).join(lines)

def format_tasks_summary():
    s = task_stats()
    if s['total_active'] == 0:
        return '📋 المهام: لا توجد مهام نشطة'
    parts = ['📋 *المهام النشطة:* ' + str(s['total_active'])]
    if s['overdue']:   parts.append('⚠️ متأخرة: ' + str(s['overdue']))
    if s['due_today']: parts.append('📌 اليوم: ' + str(s['due_today']))
    ip   = s['by_status'].get('in_progress', 0)
    todo = s['by_status'].get('todo', 0)
    if ip:   parts.append('⚡ جارية: ' + str(ip))
    if todo: parts.append('⏳ منتظرة: ' + str(todo))
    return ' | '.join(parts)

def quick_tasks_active():
    return format_task_list(task_list(limit=20), '📋 مهامك النشطة')
def quick_tasks_today():
    return format_task_list(task_list(due_today=True), '📌 مهام اليوم')
def quick_tasks_overdue():
    return format_task_list(task_list(due_overdue=True), '⚠️ المهام المتأخرة')

def llm_tool_task_list(status=None, category=None, due_today=False, due_overdue=False, limit=20):
    tasks = task_list(status=status, category=category,
                      due_today=due_today, due_overdue=due_overdue, limit=limit)
    return {'tasks': tasks, 'count': len(tasks), 'stats': task_stats()}

def llm_tool_task_create(title, category='personal', priority='med', due_date=None, description=None):
    t = task_create(title=title, category=category, priority=priority,
                    due_date=due_date, description=description, source='llm')
    return {'success': True, 'task': t,
            'message': 'تمت إضافة المهمة #' + str(t['id'])}

def llm_tool_task_update(task_id, status=None, priority=None, due_date=None, title=None):
    t = task_update(int(task_id), status=status, priority=priority, due_date=due_date, title=title)
    if not t:
        return {'success': False, 'message': 'ما لقيت مهمة رقم ' + str(task_id)}
    return {'success': True, 'task': t}

init_tasks_db()
