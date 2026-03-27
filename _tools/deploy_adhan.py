#!/usr/bin/env python3
"""Deploy adhan automation to HA - scripts.yaml + automations.yaml"""
import yaml, sys, os

SCRIPTS_FILE = "/var/lib/homeassistant/homeassistant/scripts.yaml"
AUTO_FILE = "/var/lib/homeassistant/homeassistant/automations.yaml"

ADHAN_SCRIPT = '''
adhan_play_and_resume:
  alias: "تشغيل الأذان وإرجاع القرآن"
  description: "يوقف القرآن، يشغل الأذان على كل السماعات، وبعدين يرجع القرآن"
  icon: mdi:mosque
  mode: single
  sequence:
    - variables:
        speaker_1: "media_player.office_1_2"
        speaker_2: "media_player.office_2_2"
        speaker_3: "media_player.room_3_2"
        speaker_4: "media_player.ground_floor"
        was_playing_1: "{{ is_state('media_player.office_1_2', 'playing') }}"
        was_playing_2: "{{ is_state('media_player.office_2_2', 'playing') }}"
        was_playing_3: "{{ is_state('media_player.room_3_2', 'playing') }}"
        was_playing_4: "{{ is_state('media_player.ground_floor', 'playing') }}"
        vol_1: "{{ state_attr('media_player.office_1_2', 'volume_level') | float(0.1) }}"
        vol_2: "{{ state_attr('media_player.office_2_2', 'volume_level') | float(0.1) }}"
        vol_3: "{{ state_attr('media_player.room_3_2', 'volume_level') | float(0.1) }}"
        vol_4: "{{ state_attr('media_player.ground_floor', 'volume_level') | float(0.1) }}"
        content_1: "{{ state_attr('media_player.office_1_2', 'media_content_id') | default('') }}"
        content_2: "{{ state_attr('media_player.office_2_2', 'media_content_id') | default('') }}"
        content_3: "{{ state_attr('media_player.room_3_2', 'media_content_id') | default('') }}"
        content_4: "{{ state_attr('media_player.ground_floor', 'media_content_id') | default('') }}"
    - action: media_player.media_stop
      target:
        entity_id:
          - media_player.office_1_2
          - media_player.office_2_2
          - media_player.room_3_2
          - media_player.ground_floor
    - delay:
        seconds: 1
    - action: media_player.volume_set
      target:
        entity_id:
          - media_player.office_1_2
          - media_player.office_2_2
          - media_player.room_3_2
          - media_player.ground_floor
      data:
        volume_level: 0.13
    - delay:
        seconds: 1
    - action: media_player.play_media
      target:
        entity_id:
          - media_player.office_1_2
          - media_player.office_2_2
          - media_player.room_3_2
          - media_player.ground_floor
      data:
        media_content_id: "media-source://media_source/local/adhan_makkah.mp3"
        media_content_type: "music"
    - delay:
        minutes: 4
        seconds: 30
    - action: media_player.media_stop
      target:
        entity_id:
          - media_player.office_1_2
          - media_player.office_2_2
          - media_player.room_3_2
          - media_player.ground_floor
    - delay:
        seconds: 2
    - action: media_player.volume_set
      target:
        entity_id: media_player.office_1_2
      data:
        volume_level: "{{ vol_1 }}"
    - action: media_player.volume_set
      target:
        entity_id: media_player.office_2_2
      data:
        volume_level: "{{ vol_2 }}"
    - action: media_player.volume_set
      target:
        entity_id: media_player.room_3_2
      data:
        volume_level: "{{ vol_3 }}"
    - action: media_player.volume_set
      target:
        entity_id: media_player.ground_floor
      data:
        volume_level: "{{ vol_4 }}"
    - delay:
        seconds: 1
    - if:
        - condition: template
          value_template: "{{ was_playing_1 == 'True' and content_1 != '' }}"
      then:
        - action: media_player.play_media
          target:
            entity_id: media_player.office_1_2
          data:
            media_content_id: "{{ content_1 }}"
            media_content_type: "music"
    - if:
        - condition: template
          value_template: "{{ was_playing_2 == 'True' and content_2 != '' }}"
      then:
        - action: media_player.play_media
          target:
            entity_id: media_player.office_2_2
          data:
            media_content_id: "{{ content_2 }}"
            media_content_type: "music"
    - if:
        - condition: template
          value_template: "{{ was_playing_3 == 'True' and content_3 != '' }}"
      then:
        - action: media_player.play_media
          target:
            entity_id: media_player.room_3_2
          data:
            media_content_id: "{{ content_3 }}"
            media_content_type: "music"
    - if:
        - condition: template
          value_template: "{{ was_playing_4 == 'True' and content_4 != '' }}"
      then:
        - action: media_player.play_media
          target:
            entity_id: media_player.ground_floor
          data:
            media_content_id: "{{ content_4 }}"
            media_content_type: "music"
'''

ADHAN_AUTOMATIONS = '''
- id: adhan_fajr
  alias: "أذان الفجر"
  description: "تشغيل الأذان عند وقت صلاة الفجر"
  triggers:
    - trigger: time
      at: sensor.islamic_prayer_times_fajr_prayer
  actions:
    - action: script.adhan_play_and_resume

- id: adhan_dhuhr
  alias: "أذان الظهر"
  description: "تشغيل الأذان عند وقت صلاة الظهر"
  triggers:
    - trigger: time
      at: sensor.islamic_prayer_times_dhuhr_prayer
  actions:
    - action: script.adhan_play_and_resume

- id: adhan_asr
  alias: "أذان العصر"
  description: "تشغيل الأذان عند وقت صلاة العصر"
  triggers:
    - trigger: time
      at: sensor.islamic_prayer_times_asr_prayer
  actions:
    - action: script.adhan_play_and_resume

- id: adhan_maghrib
  alias: "أذان المغرب"
  description: "تشغيل الأذان عند وقت صلاة المغرب"
  triggers:
    - trigger: time
      at: sensor.islamic_prayer_times_maghrib_prayer
  actions:
    - action: script.adhan_play_and_resume

- id: adhan_isha
  alias: "أذان العشاء"
  description: "تشغيل الأذان عند وقت صلاة العشاء"
  triggers:
    - trigger: time
      at: sensor.islamic_prayer_times_isha_prayer
  actions:
    - action: script.adhan_play_and_resume
'''

errors = []

# Step 1: Append script
try:
    with open(SCRIPTS_FILE, 'r', encoding='utf-8') as f:
        existing = f.read()
    if 'adhan_play_and_resume' in existing:
        print("SKIP: adhan_play_and_resume already in scripts.yaml")
    else:
        with open(SCRIPTS_FILE, 'a', encoding='utf-8') as f:
            f.write("\n# === Adhan Automation Script (2026-03-22) ===\n")
            f.write(ADHAN_SCRIPT.strip() + "\n")
        print("OK: Added adhan_play_and_resume to scripts.yaml")
except Exception as e:
    errors.append(str(e))
    print(f"ERROR scripts: {e}")

# Step 2: Append automations
try:
    with open(AUTO_FILE, 'r', encoding='utf-8') as f:
        existing = f.read()
    if 'adhan_fajr' in existing:
        print("SKIP: adhan automations already in automations.yaml")
    else:
        with open(AUTO_FILE, 'a', encoding='utf-8') as f:
            f.write("\n# === Adhan Prayer Automations (2026-03-22) ===\n")
            f.write(ADHAN_AUTOMATIONS.strip() + "\n")
        print("OK: Added 5 adhan automations to automations.yaml")
except Exception as e:
    errors.append(str(e))
    print(f"ERROR automations: {e}")

# Step 3: Validate YAML
for fname in [SCRIPTS_FILE, AUTO_FILE]:
    try:
        with open(fname, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        print(f"YAML OK: {os.path.basename(fname)}")
    except Exception as e:
        errors.append(str(e))
        print(f"YAML ERROR {os.path.basename(fname)}: {e}")

if errors:
    print(f"\nFAILED: {len(errors)} errors")
    sys.exit(1)
else:
    print("\nALL OK - ready for reload")
