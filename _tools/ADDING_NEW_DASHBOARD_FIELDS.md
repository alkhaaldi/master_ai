# Adding New Dashboard Fields — Checklist

Every time you add a new field to `/dashboard/extended` or any sensor-backed endpoint, follow this exact order. Do not skip steps.

## Checklist

### 1. Endpoint updated?
- [ ] Field added to the correct endpoint in `server.py`
- [ ] Returns a value in all cases (success, empty, error)
- [ ] Error case has logging (not silent `except: pass`)

### 2. JSON tested?
- [ ] `curl -s -H 'X-API-Key: KEY' http://localhost:9000/dashboard/extended | python3 -m json.tool`
- [ ] New field appears in output
- [ ] Value is correct type (list/dict/bool/string/number)
- [ ] Value is not null when data exists

### 3. configuration.yaml updated?
- [ ] `rest:` sensor has the new field in `json_attributes`
- [ ] YAML reloaded or HA restarted

### 4. Sensor sees the field?
- [ ] Check in HA Developer Tools → States
- [ ] Sensor entity shows the new attribute
- [ ] Value matches what the endpoint returns

### 5. Dashboard YAML updated?
- [ ] Card/template references the new attribute correctly
- [ ] Handles empty/null gracefully (no errors in UI)

### 6. Visual verification done?
- [ ] Open dashboard in browser
- [ ] Field displays correctly
- [ ] Edge cases tested (empty list, stale data, error state)

## Common Mistakes

- Adding field to dashboard before checking endpoint → wasted time
- Forgetting `json_attributes` in configuration.yaml → sensor never sees it
- Silent `except: pass` in endpoint → field disappears without warning
- Not testing empty state → dashboard breaks when no data

## Quick Test Command

```bash
# One-liner: check if field exists in endpoint
curl -s -H 'X-API-Key: KEY' http://localhost:9000/dashboard/extended | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('YOUR_FIELD:', d.get('your_field', 'MISSING'))"
```
