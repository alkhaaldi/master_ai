import json

with open('/home/pi/master_ai/entities.json') as f:
    data = json.load(f)

# Group by room from friendly names
rooms = {}
for domain, entities in data.items():
    for e in entities:
        name = e['name'].lower()
        eid = e['id']
        
        # Extract room from name
        room = None
        if 'living' in name or 'معيشة' in name or 'صالة' in name: room = 'صالة المعيشة'
        elif 'kitchen' in name or 'مطبخ' in name: room = 'المطبخ'
        elif 'ديوانية' in name or 'diwaniya' in name or 'men_room' in eid: room = 'الديوانية'
        elif 'استقبال' in name or 'lstqbl' in eid: room = 'صالة الاستقبال'
        elif 'my room' in name or 'my_room' in eid: room = 'غرفة الماستر'
        elif 'my bath' in name or 'my_bath' in eid: room = 'حمام الماستر'
        elif 'my dress' in name or 'my_dress' in eid: room = 'ملابس الماستر'
        elif 'aisha' in name or 'aisha' in eid or 'ausha' in name: room = 'غرفة عيشة'
        elif 'room 2' in name or 'room_2' in eid: room = 'غرفة 2'
        elif 'room 3' in name or 'room_3' in eid: room = 'غرفة 3'
        elif 'room 4' in name or 'room_4' in eid: room = 'غرفة 4'
        elif 'room 5' in name or 'room_5' in eid: room = 'غرفة 5'
        elif 'guest' in name or 'guest' in eid: room = 'غرفة الضيوف'
        elif 'maid' in name or 'maid' in eid: room = 'غرفة الخادمة'
        elif 'balcony' in name or 'balcony' in eid: room = 'البلكونة'
        elif 'laundry' in name or 'laundry' in eid: room = 'غرفة الغسيل'
        elif 'ground' in name or 'ground' in eid: room = 'الأرضي'
        elif 'stair' in name or 'stair' in eid or 'درج' in name: room = 'الدرج'
        elif 'entrance' in name or 'مدخل' in name: room = 'المدخل'
        else: room = 'أخرى'
        
        if room not in rooms:
            rooms[room] = []
        
        # Determine type
        etype = domain
        if 'spot' in name: etype = 'spot'
        elif 'strip' in name: etype = 'strip'
        elif 'chandl' in name or 'ثرية' in name or 'ثريا' in name: etype = 'ثرية'
        elif 'mirror' in name or 'مرا' in name: etype = 'مرآة'
        elif 'vent' in name or 'شفاط' in name: etype = 'شفاط'
        
        rooms[room].append({'id': eid, 'name': e['name'], 'type': etype, 'domain': domain})

# Print summary
for room in sorted(rooms):
    items = rooms[room]
    print(f"\n=== {room} ({len(items)}) ===")
    for item in sorted(items, key=lambda x: x['domain']+x['name']):
        print(f"  {item['id']} | {item['name']}")

with open('/home/pi/master_ai/rooms.json', 'w') as f:
    json.dump(rooms, f, ensure_ascii=False, indent=2)
print(f"\nSaved {len(rooms)} rooms to rooms.json")
