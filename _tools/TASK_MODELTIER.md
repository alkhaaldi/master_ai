# TASK MODELTIER - stop paying Opus prices for routine work

## Why

`llm_call()` in server.py uses `claude-opus-4-6` as its primary model. Every
Telegram message, every `/ask`, every event the house raises, and every memory
extraction goes through that path. Most of it is turning on a light or reading a
sensor. He is paying the most expensive model for that.

Model names are also hardcoded in at least five files, so nobody can see or
change the cost profile in one place.

## Do

### 1. One place that declares the tiers

Create `model_tiers.py` at the repo root. Three names, each overridable by an
environment variable so nothing needs a code edit later:

```
MODEL_CHEAP    default claude-haiku-4-5-20251001   env MAI_MODEL_CHEAP
MODEL_ROUTINE  default claude-sonnet-4-6           env MAI_MODEL_ROUTINE
MODEL_DEEP     default claude-opus-4-6             env MAI_MODEL_DEEP
```

Expose a `tiers()` dict for reporting. No other logic in that module.

### 2. Route the call sites

- `server.py` `llm_call()` (around line 1168): default to MODEL_ROUTINE. Add an
  optional `model: str = None` argument so a caller can ask for MODEL_DEEP
  explicitly. Do not change any caller's behaviour beyond the default.
- `server.py` streaming call (around line 7476): identify what that path serves
  before you touch it. If it is the interactive chat or Telegram stream, use
  MODEL_ROUTINE. If it is a deliberate deep-analysis endpoint, leave it on
  MODEL_DEEP and say so in the report.
- `chat_v7.py` model map (around line 223): keep both keys, but make the default
  selection MODEL_ROUTINE. Opus only when a caller explicitly asks for it.
- `chat_v7.py` advisor (around line 489): route through MODEL_ROUTINE rather
  than the hardcoded name it has now.
- The memory extractor (wired at `server.py` around 7553): find the model it
  uses and put it on MODEL_CHEAP. Extraction is a summarising job.
- `inbox_engine.py` (line 30 area) and `tg_logbook.py` (line 128 area): replace
  the hardcoded names with MODEL_CHEAP and MODEL_ROUTINE respectively. Same
  models as today for inbox - this is about removing the hardcoding.

### 3. Make the choice visible

- Log the model name on every LLM call at INFO, once per call, no payload.
- Add a `models` block to `/system/context` reporting the three resolved names.
  Additive only. Do not change or remove any existing key in that response.

## Verify

- `grep -rn "claude-opus" --include=*.py .` outside `_archive` and `venv` must
  return only `model_tiers.py`. Same for `claude-sonnet` and `claude-haiku`.
- `_tools/quick_check.py`, then `_tools/smoke_test.py`, then
  `_tools/db_sanity.py`.
- `bash _tools/restart_master_ai.sh` - the market is closed, so this is allowed.
- After the restart, fetch `/health` and `/system/context` and paste the
  `models` block into the report.
- Send one real request through the chat path and show the log line proving
  which model answered.

## Out of scope

- Do NOT change when the event engine fires or what it is allowed to do. Only
  which model it reaches. Whether the house should act unattended at all is his
  decision, not this task's.
- Do not touch the API key, `.env`, or any credential.
- Do not change prompts, tool definitions, or any answer's content.
- Do not migrate the database or add a table.
- The tree carries in-flight work from a parallel session: `dashboard_api.py`,
  `www/trading/home.html`, `www/trading/home-control.html`,
  `_tools/OPEN_ITEMS.md`, `_tools/REPORT_TELEGRAM_ALERTS.md`. Leave them alone.
- If a call site turns out to be load-bearing for quality in a way this plan
  gets wrong, stop and write it in the report instead of deciding alone.

## Commit

Stage by name only, and only the files you actually changed. Blanket staging is
blocked by a hook.
