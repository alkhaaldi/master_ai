#!/usr/bin/env python3
"""Analyze sub-radar YAML structure."""
import yaml, sys

YAML_PATH = "/var/lib/homeassistant/homeassistant/master_ai_dashboard.yaml"
with open(YAML_PATH, 'r', encoding='utf-8') as f:
    d = yaml.safe_load(f)

for v in d.get('views', []):
    if v.get('path') == 'sub-radar':
        cards = v.get('cards', [])
        print(f"Top-level cards: {len(cards)}")
        for i, c in enumerate(cards):
            t = c.get('type', '?')
            kids = c.get('cards', [])
            print(f"  [{i}] {t} -> {len(kids)} children")
            for j, k in enumerate(kids):
                kt = k.get('type', '?')
                kk = k.get('cards', [])
                title = ''
                if kt == 'custom:mushroom-title-card':
                    title = k.get('title', '')[:40]
                print(f"    [{j}] {kt} -> {len(kk)} ch {title}")
                if kt == 'custom:stack-in-card':
                    for m, sub in enumerate(kk):
                        st = sub.get('type', '?')
                        stitle = ''
                        if st == 'custom:mushroom-title-card':
                            stitle = sub.get('title', '')[:40]
                        sc = sub.get('cards', [])
                        print(f"      [{m}] {st} -> {len(sc)} ch {stitle}")
