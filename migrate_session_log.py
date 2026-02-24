#!/usr/bin/env python3
"""Add session_log table and update knowledge base"""
import sqlite3
from datetime import datetime

DB = "/home/pi/master_ai/data/tasks.db"
conn = sqlite3.connect(DB)

# 1. Create session_log table
conn.execute("""
    CREATE TABLE IF NOT EXISTS session_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_date TEXT NOT NULL,
        summary TEXT NOT NULL,
        changes_made TEXT DEFAULT '',
        decisions TEXT DEFAULT '',
        blockers TEXT DEFAULT '',
        next_steps TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
""")
print("session_log table created")

# 2. Update knowledge #7 - wrong network topology
now = datetime.utcnow().isoformat() + "Z"
conn.execute("""
    UPDATE knowledge SET
        content = 'Nokia 5G -> BE800(110.1) -> ES226GC-P PoE switch(110.20, MAC 10:82:3d:65:96:02) -> ES206GC-P 6-port switch(110.72, MAC f0:74:8d:9b:62:e2) -> 8x RAP APs(110.10-18) -> PC(110.132) + RPi(110.21). Office router EW3200GX is OFF/missing. Dahua NVR at 111.90 (needs office router for access). Bluesound speakers all OFF. 110.160 is a Tuya device NOT a switch!',
        updated_at = ?
    WHERE id = 7
""", (now,))
print("Knowledge #7 (topology) updated")

# 3. Update knowledge #18 - ruijie integration
conn.execute("""
    UPDATE knowledge SET
        content = 'Script: /home/pi/master_ai/ruijie_integration.py, cron every 5min. GROUP_ID=9104528 (Salem home_Auto). Fixed Feb 21 2026: field mapping corrected (mac not macAddress, productClass not productModel, serialNumber not sn, band="2.4G"/"5G"). Creates sensors: ruijie_network_overview, ruijie_clients_total, ruijie_weak_clients, sensor.ruijie_ap_*. Each AP sensor now includes: mac, model(RAP2200(E)), serial, clients count, radio channels, power, utilization.',
        updated_at = ?
    WHERE id = 18
""", (now,))
print("Knowledge #18 (ruijie integration) updated")

# 4. Add new knowledge - verified device IPs
conn.execute("""
    INSERT INTO knowledge (category, topic, content, tags, created_at, updated_at)
    VALUES ('network', 'Verified Device IP Map (Feb 21 2026)', 
    'INFRASTRUCTURE: BE800 Router=110.1(f0:a7:31), ES226GC-P PoE Switch=110.20(10:82:3d), ES206GC-P Switch=110.72(f0:74:8d), RPi5=110.21, PC=110.132(20:57:9e). APs: 1stfloor=110.10(e0:5d:54), DEWANIA=110.11(9c:2b:a6), Right-Room@SF=110.13(ec:b9:70), Myroom=110.14(ec:b9:70), Dana-Room=110.15(ec:b9:70), Reception=110.16(ec:b9:70), Livingroom=110.17(10:82:3d), Dana-living=110.18(ec:b9:70). OFFLINE: Office router EW3200GX(was 110.32), Bluesound speakers(110.150,110.9,111.239,111.53). NVR=111.90(unreachable without office router). 110.128=nginx(unknown device). 110.209=Ruijie MAC(possible RAP2260 not in cloud).',
    'network,ips,devices,verified', ?, ?)
""", (now, now))
print("Knowledge #21 (verified IPs) added")

# 5. Insert first session log
conn.execute("""
    INSERT INTO session_log (session_date, summary, changes_made, decisions, blockers, next_steps, created_at)
    VALUES (?, 
    'Full system audit + network scan. Built complete mental model of Master AI v4.0, read server.py (1130 lines), all modules, 910 HA entities, network topology. Fixed Ruijie integration field mapping. Discovered ES226GC-P is at 110.20 not 110.160. Found second switch ES206GC-P at 110.72. Office router is OFF.',
    'Fixed ruijie_integration.py: mac/model/serial/band field names corrected. Added per-AP client count, radio channels, power, utilization. Updated memory and knowledge base with correct IPs. Created session_log table for cross-conversation continuity.',
    'Network topology corrected. 110.160 is Tuya device not switch. No real IP conflicts found. Need session_log system for persistence.',
    '8 items need user input: Dahua camera creds, Samsung TV IP, Telegram bot token, Gmail for calendar, TTLock creds, baby monitor device, kitchen sensor, Tuya IoT creds.',
    'Ready to start: Stock monitoring, HACS cards, Alexa volume fix, AC sleep mode, Ruijie AP naming. Update /claude endpoint to include session_log.',
    ?)
""", (now, now))
print("Session #1 logged")

conn.commit()
conn.close()
print("ALL DONE")
