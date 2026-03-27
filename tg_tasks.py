import logging, re
from datetime import date, timedelta
from task_engine import (
    task_create, task_update, task_done, task_delete,
    task_list, task_search, task_stats, task_get,
    format_task_list, format_tasks_summary,
    quick_tasks_active, quick_tasks_today, quick_tasks_overdue,
    PRIORITY_LABEL, STATUS_LABEL, CATEGORY_LABEL, PRIORITY_MAP
)
logger = logging.getLogger(__name__)

def _parse_priority(text):
    t = text.lower()
    if any(w in t for w in ['عالي','urgent','high','مهم','ضروري']): return 'high'
    if any(w in t for w in ['منخفض','low','بعدين']): return 'low'
    return 'med'

def _parse_category(text):
    if any(w in text.lower() for w in ['عمل','work','knpc','شيفت','وردية']): return 'work'
    return 'personal'

def _parse_due_date(text):
    today = date.today()
    t = text.lower()
    if any(w in t for w in ['اليوم','today']): return today.isoformat()
    if any(w in t for w in ['باجر','بكرة','tomorrow']): return (today + timedelta(days=1)).isoformat()
    if any(w in t for w in ['بعد باجر','بعد بكرة']): return (today + timedelta(days=2)).isoformat()
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    if m: return m.group(1)
    return None

def _fmt_detail(t):
    if not t: return 'ما لقيت المهمة'
    pri    = PRIORITY_LABEL.get(t['priority'],'')
    status = STATUS_LABEL.get(t['status'], t['status'])
    cat    = CATEGORY_LABEL.get(t['category'], t['category'])
    out    = ['*[' + str(t['id']) + '] ' + t['title'] + '*',
              'الحالة: ' + status,
              'التصنيف: ' + cat,
              'الأولوية: ' + pri]
    if t.get('due_date'): out.append('الاستحقاق: 📅 ' + t['due_date'])
    if t.get('description'): out.append('ملاحظات: ' + t['description'])
    out.append('الإنشاء: ' + t['created_at'][:16])
    return chr(10).join(out)

def handle_tasks_command(args=''):
    args = args.strip()
    if not args: return quick_tasks_active()
    parts = args.split(None, 1)
    cmd  = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ''
    if cmd in ('today','اليوم'): return quick_tasks_today()
    if cmd in ('overdue','متأخرة'): return quick_tasks_overdue()
    if cmd in ('work','عمل'): return format_task_list(task_list(category='work'), '🏭 مهام العمل')
    if cmd in ('personal','شخصي'): return format_task_list(task_list(category='personal'), '👤 المهام الشخصية')
    if cmd in ('done','منجزة'): return format_task_list(task_list(status='done'), '✅ المهام المنجزة')
    if cmd in ('stats','إحصائيات','احصائيات'):
        s = task_stats()
        out = ['📊 *إحصائيات المهام*', '']
        for st, cnt in s['by_status'].items(): out.append(STATUS_LABEL.get(st,st) + ': ' + str(cnt))
        out += ['', '⚠️ متأخرة: ' + str(s['overdue']), '📌 اليوم: ' + str(s['due_today'])]
        return chr(10).join(out)
    if cmd in ('add','اضف','أضف','ضيف'):
        if not rest: return '❌ اكتب عنوان المهمة'
        priority = _parse_priority(rest)
        category = _parse_category(rest)
        due_date = _parse_due_date(rest)
        title = re.sub(r'\b(اليوم|باجر|بكرة|tomorrow|today)\b', '', rest, flags=re.IGNORECASE).strip()
        title = re.sub(r'\s+', ' ', title).strip() or rest
        t = task_create(title=title, category=category, priority=priority, due_date=due_date)
        due_str = (chr(10) + '📅 ' + t['due_date']) if t.get('due_date') else ''
        return ('✅ *تمت إضافة المهمة #' + str(t['id']) + '*' +
                chr(10) + chr(10) + t['title'] + chr(10) +
                CATEGORY_LABEL.get(t['category'],'') + ' | ' + PRIORITY_LABEL.get(t['priority'],'') + due_str)
    if cmd in ('finish','خلصت','انجزت'):
        try:
            t = task_done(int(rest))
            return ('✅ تمت إنجاز #' + rest + ': ' + t['title']) if t else 'ما لقيت مهمة ' + rest
        except (ValueError, TypeError): return '❌ اكتب رقم المهمة'
    if cmd in ('cancel','الغ','ألغ'):
        try:
            t = task_update(int(rest), status='cancelled')
            return ('❌ تم إلغاء #' + rest + ': ' + t['title']) if t else 'ما لقيت مهمة ' + rest
        except (ValueError, TypeError): return '❌ اكتب رقم المهمة'
    if cmd in ('delete','احذف','حذف'):
        try:
            tid = int(rest)
            t = task_get(tid)
            if t and task_delete(tid): return '🗑 تم حذف #' + str(tid) + ': ' + t['title']
            return 'ما لقيت مهمة ' + rest
        except (ValueError, TypeError): return '❌ اكتب رقم المهمة'
    if cmd in ('view','شوف','تفاصيل'):
        try: return _fmt_detail(task_get(int(rest)))
        except (ValueError, TypeError): return '❌ اكتب رقم المهمة'
    if cmd in ('search','بحث','دور'):
        if not rest: return '❌ اكتب كلمة للبحث'
        return format_task_list(task_search(rest), '🔍 ' + rest)
    if cmd in ('help','مساعدة'):
        h = ['📋 *أوامر المهام*','',
             '/tasks — كل المهام النشطة',
             '/tasks today — مهام اليوم',
             '/tasks overdue — المتأخرة',
             '/tasks work — مهام العمل',
             '/tasks done — المنجزة',
             '/tasks stats — إحصائيات',
             '/tasks add <عنوان>',
             '/tasks finish <رقم>',
             '/tasks cancel <رقم>',
             '/tasks delete <رقم>',
             '/tasks view <رقم>',
             '/tasks search <كلمة>']
        return chr(10).join(h)
    t = task_create(title=args, priority=_parse_priority(args),
                    category=_parse_category(args), due_date=_parse_due_date(args))
    return '✅ أضفت مهمة #' + str(t['id']) + ': ' + t['title']

def llm_tool_task_list(status=None, category=None, due_today=False, due_overdue=False, limit=20):
    tasks = task_list(status=status, category=category, due_today=due_today, due_overdue=due_overdue, limit=limit)
    return {'tasks': tasks, 'count': len(tasks), 'stats': task_stats()}

def llm_tool_task_create(title, category='personal', priority='med', due_date=None, description=None):
    t = task_create(title=title, category=category, priority=priority, due_date=due_date, description=description, source='llm')
    return {'success': True, 'task': t, 'message': 'تمت إضافة #' + str(t['id'])}

def llm_tool_task_update(task_id, status=None, priority=None, due_date=None, title=None):
    t = task_update(int(task_id), status=status, priority=priority, due_date=due_date, title=title)
    if not t: return {'success': False, 'message': 'ما لقيت مهمة #' + str(task_id)}
    return {'success': True, 'task': t}
