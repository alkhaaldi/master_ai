import logging, json, asyncio, re
from datetime import datetime
from pathlib import Path
from typing import Dict
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent
P_CRITICAL,P_HIGH,P_NORMAL,P_LOW = 4,3,2,1
PRIORITY_LABEL = {4:'🚨 عاجل',3:'🔴 مهم',2:'🟡 عادي',1:'🟢 منخفض'}
SOURCE_LABEL  = {'gmail':'📧 Gmail','outlook':'💼 KNPC'}
_HIGH_SENDERS = ['ffk023','fraij','faisal','m.fraij','anthropic','alert','alarm']
_CRITICAL_KW  = ['shutdown','emergency','trip','critical','action required','urgent','asap','طارئ','عاجل','ضروري']
_SPAM_KW      = ['quarantine','trip bypass','webmaster','newsletter','unsubscribe','meditechalert','timeoffrequest']

def _fast_priority(msg):
    fa = (msg.get('from','') + ' ' + msg.get('sender','')).lower()
    sb = msg.get('subject','').lower()
    bp = msg.get('body_preview','').lower()
    combo = sb + ' ' + bp
    if any(k in combo for k in _SPAM_KW):    return P_LOW
    if any(k in fa    for k in _HIGH_SENDERS): return P_HIGH
    if any(k in combo for k in _CRITICAL_KW): return P_CRITICAL
    if msg.get('unread'): return P_NORMAL
    return P_LOW

async def _triage_haiku(messages):
    candidates = [m for m in messages if m.get('_priority') == P_NORMAL and m.get('unread')]
    if not candidates: return messages
    try:
        import anthropic as ac
        client = ac.Anthropic()
        items = []
        for i,m in enumerate(candidates):
            items.append(str(i) + '. FROM:' + m.get('from','') + ' SUBJ:' + m.get('subject','') + ' PRE:' + m.get('body_preview','')[:80])
        prompt = ('Classify each email: 1=low 2=normal 3=high 4=critical.' + chr(10) +
                  'Reply ONLY JSON array of integers.' + chr(10) + chr(10).join(items))
        resp = client.messages.create(model='claude-haiku-4-5-20251001', max_tokens=80,
            messages=[{'role':'user','content':prompt}])
        hit = re.search(r'\[([0-9, ]+)\]', resp.content[0].text)
        if hit:
            scores = [int(x.strip()) for x in hit.group(1).split(',')]
            for i,msg in enumerate(candidates):
                if i < len(scores): msg['_priority'] = max(1,min(4,scores[i]))
    except Exception as e:
        logger.warning('[inbox] haiku triage: ' + str(e))
    return messages

async def fetch_unified_inbox(hours=24, limit=20):
    from tg_email import get_gmail_summary, get_outlook_summary
    messages, errors = [], []
    try:
        gm, err = await get_gmail_summary(hours=hours, limit=limit)
        if gm:
            for m in gm: m['source']='gmail'; m['_priority']=_fast_priority(m); messages.append(m)
        if err: errors.append('Gmail: ' + str(err))
    except Exception as e: errors.append('Gmail: ' + str(e))
    try:
        om, err = await get_outlook_summary(hours=hours, limit=limit)
        if om:
            for m in om: m['source']='outlook'; m['_priority']=_fast_priority(m); messages.append(m)
        if err and 'غير مربوط' not in str(err): errors.append('Outlook: ' + str(err))
    except Exception as e:
        if 'غير مربوط' not in str(e): errors.append('Outlook: ' + str(e))
    if messages: messages = await _triage_haiku(messages)
    messages.sort(key=lambda m: (-(m.get('_priority',1)), not m.get('unread',False)))
    return {'messages': messages[:limit], 'errors': errors, 'total': len(messages),
            'hours': hours, 'fetched_at': datetime.now().isoformat()}

def format_inbox_tg(data, show_limit=10):
    msgs   = data.get('messages',[])
    errors = data.get('errors',[])
    hours  = data.get('hours',24)
    if not msgs:
        out = '📬 *الـ Inbox فاضي*' + chr(10) + 'ما في رسائل خلال آخر ' + str(hours) + ' ساعة ✅'
        if errors: out += chr(10)+chr(10)+'⚠️ '+chr(10).join(errors)
        return out
    lines  = ['📬 *الـ Inbox* — آخر '+str(hours)+' ساعة ('+str(data['total'])+' رسالة)','']
    shown  = 0
    for pri in [P_CRITICAL,P_HIGH,P_NORMAL,P_LOW]:
        group = [m for m in msgs if m.get('_priority')==pri]
        if not group or shown>=show_limit: continue
        lines.append(PRIORITY_LABEL[pri])
        for m in group:
            if shown>=show_limit: break
            src    = SOURCE_LABEL.get(m.get('source',''),'📧')
            unread = '● ' if m.get('unread') else '  '
            sender = (m.get('sender') or m.get('from_name') or m.get('from',''))[:25]
            subj   = m.get('subject','(no subject)')[:45]
            ts     = (m.get('date') or m.get('time',''))[:16]
            lines.append(unread + src + ' *' + sender + '*')
            lines.append('   ' + subj + (' ⏰ '+ts if ts else ''))
            lines.append('')
            shown += 1
    if data['total']>show_limit: lines.append('... و '+str(data['total']-show_limit)+' رسالة أخرى')
    if errors: lines.append(''); [lines.append('⚠️ '+e) for e in errors]
    return chr(10).join(lines)

async def inbox_digest(hours=24):
    data  = await fetch_unified_inbox(hours=hours, limit=30)
    msgs  = data.get('messages',[])
    if not msgs: return '📬 الـ Inbox: لا توجد رسائل'
    crit  = sum(1 for m in msgs if m.get('_priority')==P_CRITICAL)
    high  = sum(1 for m in msgs if m.get('_priority')==P_HIGH)
    unrd  = sum(1 for m in msgs if m.get('unread'))
    parts = ['📬 *الـ Inbox:* ' + str(data['total']) + ' رسالة']
    if crit: parts.append('🚨 عاجل: '+str(crit))
    if high: parts.append('🔴 مهم: '+str(high))
    if unrd: parts.append('📬 غير مقروء: '+str(unrd))
    top = msgs[0] if msgs else None
    if top: parts.append('• '+top.get('subject','')[:40])
    return ' | '.join(parts[:3]) + (chr(10)+parts[3] if len(parts)>3 else '')

async def inbox_weekly_digest():
    data   = await fetch_unified_inbox(hours=168, limit=50)
    msgs   = data.get('messages',[])
    if not msgs: return '📬 الـ Inbox الأسبوعي: لا توجد رسائل'
    by_src = {}; by_pri = {P_CRITICAL:0,P_HIGH:0,P_NORMAL:0,P_LOW:0}
    for m in msgs:
        s = m.get('source','other'); by_src[s]=by_src.get(s,0)+1
        p = m.get('_priority',P_LOW); by_pri[p]=by_pri.get(p,0)+1
    lines = ['📬 *ملخص الـ Inbox الأسبوعي*','','إجمالي: '+str(data['total'])+' رسالة']
    for s,c in by_src.items(): lines.append(SOURCE_LABEL.get(s,s)+': '+str(c))
    lines.append('')
    for p,lbl in [(P_CRITICAL,'🚨 عاجل'),(P_HIGH,'🔴 مهم'),(P_NORMAL,'🟡 عادي')]:
        if by_pri[p]: lines.append(lbl+': '+str(by_pri[p]))
    return chr(10).join(lines)

def llm_tool_inbox_summary(hours=24, limit=10):
    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            data = pool.submit(asyncio.run, fetch_unified_inbox(hours=hours, limit=limit)).result(timeout=25)
        return {'success':True,'inbox':data,'formatted':format_inbox_tg(data,show_limit=limit)}
    except Exception as e:
        return {'success':False,'error':str(e)}

# ─── Smart Suggestions: Email → Task ──────────────────────────────────────
_ACTION_KEYWORDS = [
    'please', 'action required', 'kindly', 'respond', 'reply', 'confirm', 'approve', 'review',
    'يرجى', 'مطلوب', 'أفديت', 'رد', 'تأكيد', 'موافقة', 'مراجعة',
    'deadline', 'due', 'submit', 'send', 'complete', 'follow up', 'follow-up', 'asap',
]

def _has_action_item(msg):
    text = (msg.get('subject','') + ' ' + msg.get('body_preview','')).lower()
    return any(k in text for k in _ACTION_KEYWORDS)

async def suggest_tasks_from_inbox(hours=24, max_suggestions=3):
    data = await fetch_unified_inbox(hours=hours, limit=20)
    msgs = data.get('messages', [])
    suggestions = []
    for m in msgs:
        if not m.get('unread'): continue
        if m.get('_priority', P_LOW) < P_NORMAL: continue
        if not _has_action_item(m): continue
        src     = SOURCE_LABEL.get(m.get('source',''), '')
        sender  = (m.get('sender') or m.get('from_name') or m.get('from',''))[:20]
        subject = m.get('subject','')[:45]
        suggestions.append({
            'title':    'رد على: ' + subject,
            'category': 'work' if m.get('source') == 'outlook' else 'personal',
            'priority': 'high' if m.get('_priority',0) >= P_HIGH else 'med',
            'source':   'email',
            'source_ref': m.get('id',''),
            'display':  src + ' ' + sender + ': ' + subject,
        })
        if len(suggestions) >= max_suggestions: break
    return suggestions

async def format_email_task_suggestions() -> str:
    suggestions = await suggest_tasks_from_inbox()
    if not suggestions:
        return ''
    lines = ['💡 *اقتراحات مهام من الإيميل:*']
    for i, s in enumerate(suggestions):
        lines.append(str(i+1) + '. ' + s['display'])
    lines.append('')
    lines.append("قل 'أضف مهام من الإيميل' وأضيفها تلقائياً")
    return chr(10).join(lines)

async def auto_create_tasks_from_inbox(hours=24):
    suggestions = await suggest_tasks_from_inbox(hours=hours)
    if not suggestions: return []
    from task_engine import task_create, task_list
    # Dedup: check existing tasks with same source_ref
    existing = task_list(status='all', limit=100)
    existing_refs = {t.get('source_ref') for t in existing if t.get('source_ref')}
    created = []
    for s in suggestions:
        if s.get('source_ref') and s['source_ref'] in existing_refs:
            continue  # skip duplicate
        t = task_create(
            title=s['title'],
            category=s['category'],
            priority=s['priority'],
            source='email',
            source_ref=s['source_ref'],
        )
        created.append(t)
    return created


# ─── Logbook Auto-Task ──────────────────────────────────────────────────────
_LOGBOOK_PATTERNS = [r'log\s*book', r'e-?log', r'controller.*logbook']

async def auto_create_logbook_task(hours=24):
    """If a logbook email arrived, auto-create a review task."""
    import re
    data = await fetch_unified_inbox(hours=hours, limit=20)
    msgs = data.get('messages', [])
    from task_engine import task_create, task_list
    existing = task_list(status='all', limit=100)
    existing_refs = {t.get('source_ref') for t in existing if t.get('source_ref')}
    created = []
    for m in msgs:
        subj = m.get('subject', '')
        if not any(re.search(p, subj, re.I) for p in _LOGBOOK_PATTERNS):
            continue
        ref = m.get('id', '')
        if ref and ref in existing_refs:
            continue
        from datetime import datetime, timedelta
        due = (datetime.now() + timedelta(hours=4)).strftime('%Y-%m-%d')
        t = task_create(
            title='راجع logbook: ' + subj[:40],
            category='work',
            priority='high',
            due_date=due,
            source='email',
            source_ref=ref,
        )
        created.append(t)
        logger.info(f'[inbox] auto-created logbook task: {subj[:40]}')
    return created
