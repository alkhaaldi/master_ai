import sqlite3

conn = sqlite3.connect('/var/lib/homeassistant/share/master_ai/data/audit.db')
c = conn.cursor()

c.execute('''
    SELECT symbol, signal_type, mode, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
    FROM confluence_signals 
    WHERE is_active = 1
    GROUP BY symbol, signal_type, mode
    HAVING cnt > 1
''')
dupes = c.fetchall()
total_deleted = 0
for row in dupes:
    sym, sig, mode, cnt, ids = row
    id_list = [int(x) for x in ids.split(',')]
    keep_id = max(id_list)
    delete_ids = [x for x in id_list if x != keep_id]
    if delete_ids:
        placeholders = ','.join('?' * len(delete_ids))
        c.execute(f'DELETE FROM confluence_signals WHERE id IN ({placeholders})', delete_ids)
        total_deleted += len(delete_ids)
        print(f'  {sym}: kept id={keep_id}, deleted {len(delete_ids)} dupes')

conn.commit()
conn.close()
print(f'Total deleted: {total_deleted}')
