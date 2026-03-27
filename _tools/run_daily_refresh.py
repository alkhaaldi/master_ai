"""Run daily refresh and check results. Run from /home/pi/master_ai"""
import sys, os, json, sqlite3

# Auto-switch to venv python if not already using it
VENV_PY = '/home/pi/master_ai/venv/bin/python3'
if sys.executable != VENV_PY and os.path.exists(VENV_PY):
    print(f"[re-exec] switching from {sys.executable} to {VENV_PY}")
    os.execv(VENV_PY, [VENV_PY] + sys.argv)

sys.path.insert(0, '/home/pi/master_ai')
os.chdir('/home/pi/master_ai')

# 0. Ensure DB columns exist (ALTER TABLE)
# NOTE: stock_radar uses data/life.db NOT data/master_ai.db
print("=== Step 2: Ensuring DB columns ===")
try:
    conn = sqlite3.connect('data/life.db')
    for col in ['stoch_k REAL', 'adx REAL', 'rsi_divergence TEXT', 'atr REAL']:
        try:
            conn.execute(f'ALTER TABLE stock_radar_daily ADD COLUMN {col}')
            print(f'  Added: {col}')
        except:
            print(f'  Already exists: {col.split()[0]}')
    conn.commit()
    conn.close()
    print('  DB OK')
except Exception as e:
    print(f'  DB ALTER ERROR: {e}')

# 1. Check tvDatafeed
print("\n=== Step 5: tvDatafeed check ===")
try:
    from tvDatafeed import TvDatafeed, Interval
    print('  tvDatafeed OK')
except ImportError:
    print('  NOT installed — trying multiple pip paths...')
    import subprocess
    pip_candidates = [
        [sys.executable, '-m', 'pip', 'install', 'tvDatafeed', '--break-system-packages'],
        ['/srv/homeassistant/bin/pip', 'install', 'tvDatafeed'],
        ['/home/pi/master_ai/venv/bin/pip', 'install', 'tvDatafeed'],
        ['pip3', 'install', 'tvDatafeed', '--break-system-packages'],
    ]
    installed = False
    for cmd in pip_candidates:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                print(f'  Installed via: {cmd[0]}')
                installed = True
                break
            else:
                print(f'  Failed ({cmd[0]}): {(r.stderr or r.stdout)[-120:].strip()}')
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            print(f'  Skip {cmd[0]}: {e}')
    if not installed:
        print('  Could not install — run manually:')
        print('    /srv/homeassistant/bin/pip install tvDatafeed')
        print('    OR: pip3 install tvDatafeed --break-system-packages')

# 2. Trigger refresh
print("\n=== Step 6: refresh_daily_snapshot() ===")
try:
    from stock_radar import refresh_daily_snapshot
    result = refresh_daily_snapshot()
    print(json.dumps(result, default=str, indent=2)[:3000])
except Exception as e:
    print(f'ERROR: {e}')
    import traceback; traceback.print_exc()

# 3. Check DB
print("\n=== Step 7: DB verify ===")
try:
    c = sqlite3.connect('data/life.db')
    c.row_factory = sqlite3.Row
    cols = [d[1] for d in c.execute('PRAGMA table_info(stock_radar_daily)').fetchall()]
    new_cols = [x for x in ['stoch_k','adx','rsi_divergence','atr'] if x in cols]
    missing  = [x for x in ['stoch_k','adx','rsi_divergence','atr'] if x not in cols]
    print(f'  Present: {new_cols}')
    print(f'  Missing: {missing}')
    if new_cols:
        rows = c.execute(f"SELECT symbol,{','.join(new_cols)} FROM stock_radar_daily ORDER BY rowid DESC LIMIT 5").fetchall()
        for r in rows:
            print(' ', json.dumps(dict(r), default=str))
    c.close()
except Exception as e:
    print(f'  DB ERROR: {e}')
    import traceback; traceback.print_exc()
