# Adhan Automation — Claude Code Deployment Plan
# Date: 2026-03-22
# Status: APPROVED — Execute on RPi

## GOAL
Add prayer-time adhan automation to HA. At each prayer time:
1. Save current state of all 4 Bluesound speakers
2. Stop all speakers  
3. Set volume to 13% (0.13) on all speakers
4. Play adhan_makkah.mp3 on all speakers via Music Assistant
5. Wait ~4.5 min for adhan to finish
6. Restore previous volume on each speaker
7. Resume Quran/whatever was playing before on speakers that were active

## SPEAKERS (4 Bluesound via Music Assistant)
- media_player.office_1_2 (1st floor Speaker)
- media_player.office_2_2 (Office)
- media_player.room_3_2 (Room 3)
- media_player.ground_floor (Ground)

## PRAYER SENSORS (Islamic Prayer Times integration)
- sensor.islamic_prayer_times_fajr_prayer
- sensor.islamic_prayer_times_dhuhr_prayer
- sensor.islamic_prayer_times_asr_prayer
- sensor.islamic_prayer_times_maghrib_prayer
- sensor.islamic_prayer_times_isha_prayer

## ADHAN FILE
Already exists: /var/lib/homeassistant/media/adhan_makkah.mp3
Music Assistant URI: library://track/6
HA media source: media-source://media_source/local/adhan_makkah.mp3

## EXECUTION STEPS

### Step 1: Read current scripts.yaml and automations.yaml
```bash
cat /var/lib/homeassistant/homeassistant/scripts.yaml | head -20
cat /var/lib/homeassistant/homeassistant/automations.yaml | head -20
```
Understand the format before adding.

### Step 2: Add the script to scripts.yaml
Read the full spec from: /var/lib/homeassistant/share/master_ai/_tools/adhan_automation.yaml
Add the script section (adhan_play_and_resume) to scripts.yaml.

IMPORTANT: The script must:
- Save state BEFORE stopping (variables block)
- Use media_player.play_media with the correct media_content_id
- Try BOTH formats for play_media:
  - First try: media-source://media_source/local/adhan_makkah.mp3
  - If that doesn't work with Music Assistant speakers, use: library://track/6
- Wait 4:30 for adhan
- Restore volumes individually (each speaker had different volume)
- Resume playback only on speakers that WERE playing

### Step 3: Add 5 automations to automations.yaml
Each automation:
- Trigger: time at prayer sensor
- Action: call script.adhan_play_and_resume
- Use unique IDs: adhan_fajr, adhan_dhuhr, adhan_asr, adhan_maghrib, adhan_isha

### Step 4: Validate YAML
```bash
cd /var/lib/homeassistant/homeassistant
python3 -c "import yaml; yaml.safe_load(open('scripts.yaml')); print('scripts OK')"
python3 -c "import yaml; yaml.safe_load(open('automations.yaml')); print('automations OK')"
```

### Step 5: Reload HA
```bash
# Reload scripts and automations via HA API
curl -s -X POST -H "Authorization: Bearer $(cat ~/.ha_token)" \
  -H "Content-Type: application/json" \
  http://localhost:8123/api/services/script/reload

curl -s -X POST -H "Authorization: Bearer $(cat ~/.ha_token)" \
  -H "Content-Type: application/json" \
  http://localhost:8123/api/services/automation/reload
```

### Step 6: Verify
```bash
# Check script exists
curl -s -H "Authorization: Bearer $(cat ~/.ha_token)" \
  http://localhost:8123/api/states/script.adhan_play_and_resume | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['entity_id'], d['state'])"

# Check automations exist
for prayer in fajr dhuhr asr maghrib isha; do
  curl -s -H "Authorization: Bearer $(cat ~/.ha_token)" \
    http://localhost:8123/api/states/automation.adhan_${prayer} | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['entity_id'], d['state'])" 2>/dev/null || echo "adhan_${prayer}: NOT FOUND"
done
```

### Step 7: Test (optional)
```bash
# Manually trigger the script to test
curl -s -X POST -H "Authorization: Bearer $(cat ~/.ha_token)" \
  -H "Content-Type: application/json" \
  http://localhost:8123/api/services/script/adhan_play_and_resume
```

## NOTES
- Do NOT remove existing prayer automations (prayer_fajr_announcement etc.) — those are Alexa TTS, keep both
- The script mode is "single" — if already running, won't trigger again
- Volume 13 = 0.13 in HA (0.0 to 1.0 scale)
- The adhan file is ~4 min long, we wait 4:30 to be safe
