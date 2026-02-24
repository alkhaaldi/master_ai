import json, subprocess

r = subprocess.run(['curl','-s','-H','Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDVlZWRkMzk0MjY0MDk2OTY0YThlNjYyZDU0NTYzYiIsImlhdCI6MTc3MTI1NDI4NywiZXhwIjoyMDg2NjE0Mjg3fQ.Ws_86k8u0abSGfBZMYxKVSxzO8r6kX2yyIXPicjyFd0','http://localhost:8123/api/states'], capture_output=True, text=True)
entities = json.loads(r.stdout)

# Build compact map: arabic_name -> [entity_ids]
room_map = {}

def add(room, eid, ename):
    if room not in room_map:
        room_map[room] = []
    room_map[room].append(f"{eid}={ename}")

for e in entities:
    eid = e['entity_id']
    name = e['attributes'].get('friendly_name', '')
    domain = eid.split('.')[0]
    if domain not in ['light','switch','cover','climate','fan','scene','media_player']:
        continue
    nl = name.lower()
    el = eid.lower()
    
    # Room detection
    if 'office' in nl or 'office' in el or ('room_1' in el and 'room_1' not in 'bathroom'):
        add('المكتب/Office', eid, name)
    elif 'living' in nl or 'living' in el:
        add('صالة المعيشة/Living', eid, name)
    elif 'kitchen' in nl or 'kitchen' in el:
        add('المطبخ/Kitchen', eid, name)
    elif 'ديوانية' in nl or 'ldywny' in el or 'men_room' in el or 'diwaniya' in nl:
        add('الديوانية/Diwaniya', eid, name)
    elif 'استقبال' in nl or 'lstqbl' in el:
        add('صالة الاستقبال/Reception', eid, name)
    elif 'my room' in nl or 'my_room' in el:
        add('غرفة الماستر/Master', eid, name)
    elif 'my bath' in nl or 'my_bath' in el:
        add('حمام الماستر', eid, name)
    elif 'my dress' in nl or 'my_dress' in el:
        add('ملابس الماستر', eid, name)
    elif 'salon' in nl or 'salon' in el or 'my sweet' in nl or 'my_sweet' in el or 'صالتي' in nl:
        add('صالتي/Salon', eid, name)
    elif 'aisha' in nl or 'aisha' in el or 'ausha' in nl:
        add('غرفة عيشة/Aisha', eid, name)
    elif 'room 2' in nl or 'room_2' in el:
        add('غرفة 2', eid, name)
    elif 'room 3' in nl or 'room_3' in el:
        add('غرفة 3', eid, name)
    elif 'room 4' in nl or 'room_4' in el:
        add('غرفة 4', eid, name)
    elif 'room 5' in nl or 'room_5' in el:
        add('غرفة 5', eid, name)
    elif 'guest' in nl or 'guest' in el:
        add('غرفة الضيوف/Guest', eid, name)
    elif 'maid' in nl or 'maid' in el:
        add('غرفة الخادمة/Maid', eid, name)
    elif 'mama' in nl or 'mama' in el:
        add('غرفة ماما/Mama', eid, name)
    elif 'balcony' in nl or 'balcony' in el:
        add('البلكونة/Balcony', eid, name)
    elif 'laundry' in nl or 'laundry' in el:
        add('غرفة الغسيل/Laundry', eid, name)
    elif 'ground' in nl or 'ground' in el or 'أرضي' in nl:
        add('الأرضي/Ground', eid, name)
    elif 'stair' in nl or 'stair' in el or 'درج' in nl:
        add('الدرج/Stairs', eid, name)
    elif 'outdoor' in nl or 'parking' in nl:
        add('الخارجي/Outdoor', eid, name)
    elif 'dining' in nl or 'dining' in el:
        add('غرفة الطعام/Dining', eid, name)
    elif '1st floor' in nl or '1st_floor' in el:
        add('ممر الدور الأول', eid, name)
    elif 'scene' in domain:
        add('المشاهد/Scenes', eid, name)

# Save compact version
with open('/home/pi/master_ai/entity_map.json', 'w') as f:
    json.dump(room_map, f, ensure_ascii=False, indent=2)

# Print summary
total = 0
for room in sorted(room_map):
    count = len(room_map[room])
    total += count
    print(f"{room}: {count}")
print(f"\nTotal mapped: {total}")
