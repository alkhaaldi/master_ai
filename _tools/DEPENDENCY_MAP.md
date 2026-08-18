# Master AI — Dependency Map

**Generated:** 2026-08-18T12:36:00.658386+00:00  
**Commit:** 4b2ecd8  
**Elapsed:** 2.67 s  


## Scan coverage

| Item | Count |
| --- | --- |
| python files scanned | 356 |
| html files scanned | 20 |
| yaml files scanned | 3 |
| routes found | 188 |
| ha sensors found | 9 |
| ha rest commands found | 2 |
| ha shell commands found | 7 |
| ha yaml edges found | 17 |
| telegram commands found | 124 |
| python import edges | 2250 |
| sql edges | 2410 |
| schedules found | 55 |
| shell scripts found | 4 |
| dynamic requests found | 13 |
| parse errors | 0 |

**Excluded directories**

- `venv/` — third-party packages (~20 k files), contains no project code
- `_archive/` — deprecated/retired code, intentionally decoupled from live system
- `__pycache__/` — Python bytecode cache, not source
- `backups/` — backup archives, not source code
- `data/` — data files, not source code
- `logs/` — log files, not source code
- `audit/` — audit database directory, not source code


## FastAPI routes

| Method | Path | Handler | File | Line |
| --- | --- | --- | --- | --- |
| POST | `/action/execute` | action_execute_endpoint | server.py | 4908 |
| POST | `/agent` | agent_endpoint | server.py | 4191 |
| GET | `/aliases` | aliases_endpoint | server.py | 8437 |
| GET | `/anomalies` | get_anomalies_ep | server.py | 4058 |
| GET | `/anomalies` | anomalies_endpoint | server.py | 9285 |
| GET | `/api/analyze` | api_analyze | server.py | 8115 |
| POST | `/api/analyze/refresh` | api_analyze_refresh | server.py | 8142 |
| POST | `/api/analyze/refresh-all` | api_analyze_refresh_all | server.py | 8148 |
| GET | `/api/brain/stats` | api_brain_stats | dashboard_api.py | 3500 |
| POST | `/api/collect-now` | api_collect_now | dashboard_api.py | 3260 |
| GET | `/api/context-health` | api_context_health | dashboard_api.py | 3589 |
| GET | `/api/data-freshness` | api_data_freshness | dashboard_api.py | 3164 |
| GET | `/api/data-health` | api_data_health | dashboard_api.py | 3153 |
| GET | `/api/decisions-now` | api_decisions_now | server.py | 3615 |
| GET | `/api/flags` | get_feature_flags | server.py | 8071 |
| POST | `/api/flags/{name}/toggle` | toggle_feature_flag | server.py | 8075 |
| GET | `/api/hooks/log` | get_hooks_log | server.py | 8280 |
| GET | `/api/hooks/stats` | get_hooks_stats | server.py | 8276 |
| GET | `/api/intent-analytics` | api_intent_analytics | dashboard_api.py | 3439 |
| GET | `/api/kairos/log` | get_kairos_log | server.py | 8269 |
| GET | `/api/kairos/status` | get_kairos_status | server.py | 8263 |
| GET | `/api/latency-stats` | api_latency_stats | dashboard_api.py | 3638 |
| GET | `/api/memory-extraction/stats` | api_memory_extraction_stats | dashboard_api.py | 3387 |
| GET | `/api/news` | api_news | server.py | 8300 |
| POST | `/api/news/refresh-boursa` | api_news_refresh_boursa | server.py | 8314 |
| POST | `/api/news/refresh-gemini` | api_news_refresh_gemini | server.py | 8337 |
| POST | `/api/paper-trade/close` | api_paper_trade_close | dashboard_api.py | 2400 |
| POST | `/api/paper-trade/open` | api_paper_trade_open | dashboard_api.py | 2388 |
| POST | `/api/portfolio-alert-ack` | api_portfolio_alert_ack | dashboard_api.py | 3341 |
| POST | `/api/portfolio-monitor` | api_portfolio_monitor | dashboard_api.py | 3328 |
| GET | `/api/portfolio-status` | api_portfolio_status | dashboard_api.py | 3298 |
| POST | `/api/portfolio/add-more` | api_add_more | server.py | 8195 |
| POST | `/api/portfolio/partial-sell` | api_partial_sell | server.py | 8174 |
| GET | `/api/portfolio/transactions/{trade_id}` | api_trade_transactions | server.py | 8216 |
| GET | `/api/radar/progress` | api_radar_progress | dashboard_api.py | 3632 |
| POST | `/api/refresh-analysis` | api_refresh_analysis | server.py | 8163 |
| POST | `/api/review-now` | manual_review | server.py | 3673 |
| GET | `/api/risk-config` | api_risk_config_get | dashboard_api.py | 3117 |
| POST | `/api/risk-config` | api_risk_config_update | dashboard_api.py | 3126 |
| GET | `/api/service-health` | get_service_health | server.py | 8090 |
| GET | `/api/skills` | api_skills | dashboard_api.py | 3671 |
| GET | `/api/stocks/profiles` | get_all_stock_profiles | server.py | 3659 |
| GET | `/api/stocks/symbol/{symbol}` | get_stock_personality | server.py | 3653 |
| GET | `/api/symbols` | api_symbols | dashboard_api.py | 3358 |
| GET | `/api/tasks` | get_tasks | server.py | 8228 |
| GET | `/api/tools` | get_tools | server.py | 8284 |
| GET | `/api/tools/{name}` | get_tool_detail | server.py | 8290 |
| POST | `/api/trade/close` | api_trade_close | dashboard_api.py | 3046 |
| POST | `/api/trade/open` | api_trade_open | dashboard_api.py | 3016 |
| POST | `/api/trade/update` | api_trade_update | dashboard_api.py | 3063 |
| GET | `/approvals/pending` | list_pending_approvals | server.py | 4340 |
| POST | `/approve/{approval_id}` | approve_action | server.py | 4292 |
| POST | `/ask` | ask | server.py | 4075 |
| GET | `/audit` | get_audit | server.py | 4841 |
| GET | `/brain/analytics` | analytics_endpoint | server.py | 3296 |
| GET | `/brain/diag` | brain_diag_endpoint | server.py | 3316 |
| GET | `/brain/expertise` | brain_expertise | server.py | 5163 |
| POST | `/brain/feedback` | feedback_endpoint | server.py | 3308 |
| GET | `/brain/stats` | brain_stats_endpoint | server.py | 3251 |
| GET | `/brain/users` | users_endpoint | server.py | 3302 |
| GET | `/bridge/status` | bridge_circuit_status | server.py | 3109 |
| GET | `/calendar/stats` | calendar_stats_endpoint | server.py | 3513 |
| POST | `/calendar/sync` | calendar_sync_endpoint | server.py | 3523 |
| POST | `/chat/clear` | clear_chat_history | server.py | 8365 |
| POST | `/classify` | classify_msg | server.py | 9250 |
| GET | `/claude` | claude_context | server.py | 4496 |
| GET | `/corrections` | get_corrections_stats | server.py | 9214 |
| POST | `/corrections/decay` | decay_corrections_endpoint | server.py | 9223 |
| GET | `/cost` | cost_dashboard | server.py | 9297 |
| POST | `/daily-snapshot/refresh` | refresh_daily_snapshot_manual | server.py | 3127 |
| GET | `/dashboard` | ha_dashboard | dashboard_api.py | 151 |
| GET | `/dashboard/alerts` | ha_dashboard_alerts | dashboard_api.py | 1336 |
| GET | `/dashboard/analysis` | ha_dashboard_analysis | dashboard_api.py | 1487 |
| GET | `/dashboard/brain` | dashboard_brain | dashboard_api.py | 2599 |
| GET | `/dashboard/brain-insights` | dashboard_brain_insights | dashboard_api.py | 2920 |
| GET | `/dashboard/bridge` | dashboard_bridge | dashboard_api.py | 1879 |
| GET | `/dashboard/bridge/{symbol}` | dashboard_bridge_symbol | dashboard_api.py | 1903 |
| POST | `/dashboard/cmd` | dashboard_cmd | dashboard_api.py | 399 |
| GET | `/dashboard/confluence` | ha_dashboard_confluence | dashboard_api.py | 1423 |
| GET | `/dashboard/ema-active` | dashboard_ema_active | server.py | 3798 |
| GET | `/dashboard/ema-crosses` | dashboard_ema_crosses | server.py | 3686 |
| GET | `/dashboard/ema-live` | dashboard_ema_live | server.py | 3880 |
| GET | `/dashboard/ema-proximity` | dashboard_ema_proximity | server.py | 3753 |
| GET | `/dashboard/equity` | dashboard_equity | dashboard_api.py | 2414 |
| GET | `/dashboard/extended` | ha_dashboard_extended | dashboard_api.py | 1646 |
| GET | `/dashboard/jobs` | dashboard_jobs_list | dashboard_api.py | 431 |
| GET | `/dashboard/journal` | ha_dashboard_journal | dashboard_api.py | 1212 |
| GET | `/dashboard/paper-trading` | dashboard_paper_trading | dashboard_api.py | 2378 |
| GET | `/dashboard/portfolio` | ha_dashboard_portfolio | dashboard_api.py | 1004 |
| GET | `/dashboard/radar` | ha_dashboard_radar | dashboard_api.py | 441 |
| GET | `/dashboard/regime` | dashboard_regime | dashboard_api.py | 2565 |
| GET | `/dashboard/reviews` | dashboard_reviews | server.py | 3666 |
| GET | `/dashboard/risk-status` | dashboard_risk_status | dashboard_api.py | 2424 |
| GET | `/dashboard/scalper` | dashboard_scalper | dashboard_api.py | 2434 |
| GET | `/dashboard/signals` | dashboard_signals | dashboard_api.py | 1965 |
| GET | `/dashboard/signals-30m` | dashboard_signals_30m | dashboard_api.py | 2119 |
| GET | `/dashboard/signals-daily` | dashboard_signals_daily | dashboard_api.py | 1980 |
| GET | `/dashboard/strategies` | dashboard_strategies | dashboard_api.py | 2940 |
| GET | `/dashboard/swing` | dashboard_swing | dashboard_api.py | 2126 |
| POST | `/debug/test_approval` | debug_test_approval | server.py | 3346 |
| POST | `/decompose` | decompose_msg | server.py | 9255 |
| POST | `/deploy` | deploy_file | server.py | 4707 |
| GET | `/dev/context` | dev_context | server.py | 5181 |
| POST | `/dream/run` | dream_run_endpoint | server.py | 3280 |
| GET | `/dream/status` | dream_status_endpoint | server.py | 3271 |
| POST | `/entity-map/arabize` | entity_map_arabize | server.py | 8498 |
| GET | `/entity-map/health` | entity_map_health | server.py | 8485 |
| POST | `/event` | ingest_event | server.py | 4937 |
| GET | `/event_rules` | get_event_rules | server.py | 4985 |
| GET | `/events` | list_events_ep | server.py | 4974 |
| GET | `/events/{event_id}` | get_event_ep | server.py | 4978 |
| GET | `/feedback/digest` | feedback_digest_endpoint | server.py | 9274 |
| GET | `/feedback/stats` | feedback_stats_endpoint | server.py | 9266 |
| GET | `/gmail/auth` | gmail_auth_start | server.py | 3362 |
| GET | `/gmail/callback` | gmail_auth_callback | server.py | 3397 |
| GET | `/google/auth` | google_auth_start | server.py | 3453 |
| GET | `/google/auth/status` | google_auth_status | server.py | 3503 |
| GET | `/google/callback` | google_auth_callback | server.py | 3471 |
| POST | `/ha/service` | ha_call_service_ep | server.py | 4256 |
| GET | `/ha/states` | ha_get_states | server.py | 4265 |
| GET | `/ha/states/{entity_id:path}` | ha_get_state | server.py | 4270 |
| GET | `/health` | health | server.py | 3973 |
| GET | `/health/external` | health_external | server.py | 8046 |
| POST | `/health/external/test` | health_external_test | server.py | 8404 |
| GET | `/history/{entity_id:path}` | entity_history_endpoint | server.py | 3993 |
| GET | `/knowledge` | list_knowledge | server.py | 4603 |
| POST | `/knowledge` | create_knowledge | server.py | 4626 |
| DELETE | `/knowledge/{kid}` | delete_knowledge | server.py | 4649 |
| GET | `/knowledge/{kid}` | get_knowledge | server.py | 4617 |
| PUT | `/knowledge/{kid}` | update_knowledge | server.py | 4637 |
| GET | `/kpi` | kpi_dashboard | server.py | 9308 |
| GET | `/memory` | list_memories_ep | server.py | 4756 |
| POST | `/memory` | create_memory_ep | server.py | 4747 |
| POST | `/memory/message` | save_msg | server.py | 4798 |
| GET | `/memory/recent` | memory_recent | server.py | 4791 |
| GET | `/memory/stats` | mem_stats | server.py | 4769 |
| GET | `/patterns` | patterns_endpoint | server.py | 4040 |
| POST | `/patterns/learn` | patterns_learn_endpoint | server.py | 4067 |
| GET | `/patterns/suggestions` | patterns_suggestions_endpoint | server.py | 4051 |
| GET | `/plugins` | list_plugins | server.py | 4902 |
| POST | `/plugins/{name}/disable` | disable_plugin | server.py | 4922 |
| POST | `/plugins/{name}/enable` | enable_plugin | server.py | 4915 |
| GET | `/router/stats` | router_stats_endpoint | server.py | 8446 |
| GET | `/schema` | schema_status | server.py | 4867 |
| POST | `/schema/ensure` | schema_ensure | server.py | 4887 |
| GET | `/sessions` | list_sessions | server.py | 4568 |
| POST | `/sessions` | create_session | server.py | 4556 |
| GET | `/sessions/latest` | latest_session | server.py | 4578 |
| GET | `/shift` | shift_info | server.py | 4469 |
| POST | `/ssh/run` | ssh_run | server.py | 4283 |
| GET | `/stability` | stability_endpoint | server.py | 8422 |
| POST | `/stats/capture` | stats_capture | server.py | 4454 |
| GET | `/stats/daily` | stats_daily | server.py | 4439 |
| GET | `/stocks/alerts` | stock_alerts_history | server.py | 4688 |
| GET | `/stocks/portfolio` | stock_portfolio | server.py | 4679 |
| GET | `/structured-memory` | smem_stats | server.py | 9142 |
| GET | `/structured-memory/context` | smem_context | server.py | 9147 |
| POST | `/structured-memory/correction` | smem_save_correction | server.py | 9174 |
| POST | `/structured-memory/decay` | smem_decay | server.py | 9203 |
| POST | `/structured-memory/event` | smem_save_event | server.py | 9163 |
| POST | `/structured-memory/fact` | smem_save_fact | server.py | 9152 |
| POST | `/structured-memory/migrate` | smem_migrate | server.py | 9193 |
| GET | `/structured-memory/search` | smem_search | server.py | 9184 |
| POST | `/structured-memory/seed` | smem_seed | server.py | 9198 |
| DELETE | `/structured-memory/{memory_id}` | smem_delete | server.py | 9209 |
| POST | `/system/backup` | backup_endpoint | server.py | 3265 |
| GET | `/system/context` | system_context | server.py | 5019 |
| GET | `/system/diag` | system_diag_endpoint | server.py | 3258 |
| GET | `/system/knowledge` | system_knowledge_endpoint | server.py | 5142 |
| GET | `/system/knowledge/summary` | system_knowledge_summary | server.py | 5152 |
| GET | `/tasks` | list_tasks_ep | server.py | 4662 |
| GET | `/tasks/{task_id}` | get_task_ep | server.py | 4667 |
| GET | `/tg/stats` | tg_stats | server.py | 8374 |
| GET | `/tips` | tips_endpoint | server.py | 3289 |
| GET | `/tool-stats` | tool_stats_endpoint | server.py | 3545 |
| GET | `/traces` | traces_list | server.py | 9242 |
| GET | `/traces/stats` | traces_stats | server.py | 9246 |
| GET | `/trading/{page}` | serve_trading_page | server.py | 3156 |
| POST | `/tradingview/webhook` | tradingview_webhook | server.py | 3554 |
| GET | `/users` | list_users | server.py | 4827 |
| POST | `/users` | create_user | server.py | 4812 |
| POST | `/webhook/event` | webhook_event | server.py | 5004 |
| POST | `/webhook/event/{token}` | webhook_event_legacy | server.py | 4992 |
| GET | `/win/jobs` | win_jobs | server.py | 4421 |
| GET | `/win/poll` | win_poll | server.py | 4398 |
| POST | `/win/register` | win_register | server.py | 4390 |
| POST | `/win/report` | win_report | server.py | 4409 |
| GET | `/world-state` | world_state_endpoint | server.py | 3534 |


## Home Assistant REST sensors

| sensor_id | endpoint | interval |
| --- | --- | --- |
| master_ai_dashboard | `/dashboard` | 30s |
| master_ai_extended | `/dashboard/extended` | 120s |
| master_ai_radar | `/dashboard/radar` | 120s |
| master_ai_portfolio | `/dashboard/portfolio` | 120s |
| master_ai_analysis | `/dashboard/analysis` | 300s |
| master_ai_journal | `/dashboard/journal` | 120s |
| master_ai_alerts | `/dashboard/alerts` | 300s |
| master_ai_confluence | `/dashboard/confluence` | 120s |
| master_ai_signals | `/dashboard/signals` | 120s |


## Home Assistant rest_command definitions

_Entries in `configuration.yaml` `rest_command:` that call port 9000._

| name | method | endpoint | file | line |
| --- | --- | --- | --- | --- |
| master_ai_event | POST | `/webhook/event/6Co3caBiT407a8txFLUEHg1rT8R76QlHVC1-seQmh74` | /var/lib/homeassistant/homeassistant/configuration.yaml | 49 |
| master_ai_tg_cmd | POST | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/configuration.yaml | 62 |


## Home Assistant shell_command definitions

_All entries in `configuration.yaml` `shell_command:` (none currently call master_ai)._

| name | command | file | line |
| --- | --- | --- | --- |
| unlock_kitchen_door | `python3 /config/scripts/tuya_lock.py bf1387ufqg1pslyb` | /var/lib/homeassistant/homeassistant/configuration.yaml | 31 |
| unlock_men_room_door | `python3 /config/scripts/tuya_lock.py bf5888sku0w0208e` | /var/lib/homeassistant/homeassistant/configuration.yaml | 32 |
| unlock_first_floor_door | `python3 /config/scripts/tuya_lock.py bf7b76c21feac56879jlzl` | /var/lib/homeassistant/homeassistant/configuration.yaml | 33 |
| unlock_diwaniya_door | `python3 /config/scripts/tuya_lock.py bf4f0dbf0557c7c0e4v5e9` | /var/lib/homeassistant/homeassistant/configuration.yaml | 34 |
| unlock_ground_door | `python3 /config/scripts/tuya_lock.py bff4c4cbf2c9957114coiq` | /var/lib/homeassistant/homeassistant/configuration.yaml | 35 |
| unlock_main_door | `python3 /config/scripts/tuya_lock.py bf56d71589296efb0buexs` | /var/lib/homeassistant/homeassistant/configuration.yaml | 36 |
| unlock_my_room | `python3 /config/scripts/tuya_lock.py bf0fd882b4c8467ed2fdr0` | /var/lib/homeassistant/homeassistant/configuration.yaml | 37 |


## Home Assistant automation / script references

_Automations and scripts that call master_ai rest_commands or shell_commands._

| kind | alias/name | ref_kind | ref_name | endpoint | file | line |
| --- | --- | --- | --- | --- | --- | --- |
| ha_automation | Master AI - HA Started | rest_command | master_ai_event | `/webhook/event/6Co3caBiT407a8txFLUEHg1rT8R76QlHVC1-seQmh74` | /var/lib/homeassistant/homeassistant/automations.yaml | 455 |
| ha_automation | Master AI - Door Unlocked | rest_command | master_ai_event | `/webhook/event/6Co3caBiT407a8txFLUEHg1rT8R76QlHVC1-seQmh74` | /var/lib/homeassistant/homeassistant/automations.yaml | 480 |
| ha_automation | Master AI - Baby Crying | rest_command | master_ai_event | `/webhook/event/6Co3caBiT407a8txFLUEHg1rT8R76QlHVC1-seQmh74` | /var/lib/homeassistant/homeassistant/automations.yaml | 499 |
| ha_automation | Quran Watchdog - Restart if stopped or hung | rest_command | master_ai_event | `/webhook/event/6Co3caBiT407a8txFLUEHg1rT8R76QlHVC1-seQmh74` | /var/lib/homeassistant/homeassistant/automations.yaml | 694 |
| ha_script | Unlock Diwaniya Door UI | shell_command | unlock_diwaniya_door |  | /var/lib/homeassistant/homeassistant/scripts.yaml | 4 |
| ha_script | Unlock Kitchen Door UI | shell_command | unlock_kitchen_door |  | /var/lib/homeassistant/homeassistant/scripts.yaml | 8 |
| ha_script | تشغيل/إيقاف الرادار | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 19 |
| ha_script | فحص السوق | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 37 |
| ha_script | تقرير الصباح | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 55 |
| ha_script | Backup | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 73 |
| ha_script | حالة الرادار | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 91 |
| ha_script | نظرة الأسهم | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 109 |
| ha_script | تحديث الأخبار | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 127 |
| ha_script | إطفاء الكل | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 145 |
| ha_script | تحديث البريد | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 163 |
| ha_script | مراجعة التداول | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 181 |
| ha_script | TV Sync | rest_command | master_ai_tg_cmd | `/dashboard/cmd` | /var/lib/homeassistant/homeassistant/scripts.yaml | 199 |


## Telegram slash-command dispatch

_Static `if cmd == "/x"` / `cmd.startswith("/x")` entries in Python files._

| command | match_type | file | line |
| --- | --- | --- | --- |
| `/report` | exact | _tools/_patch_phase34.py | 92 |
| `/kairos` | exact | _tools/_patch_phase34.py | 94 |
| `/something` | exact | _tools/depmap.py | 542 |
| `/something` | prefix | _tools/depmap.py | 543 |
| `/tv_stats` | exact | _tools/patchers/phase3_tv_sync_cmd.py | 9 |
| `/kpi` | exact | _tools/patchers/phase3_tv_sync_cmd.py | 14 |
| `/tv_sync` | exact | _tools/patchers/phase3_tv_sync_cmd.py | 20 |
| `/stocks` | exact | _tools/patchers/v12_patch_stocks.py | 9 |
| `/tasks` | exact | _tools/patchers/v12_patch_tasks_calls.py | 9 |
| `/help` | exact | scripts/patch_tg_cmds.py | 6 |
| `/approvals` | exact | scripts/patch_tg_cmds.py | 18 |
| `/backup` | exact | scripts/patch_tg_cmds.py | 31 |
| `/restart` | exact | scripts/patch_tg_cmds.py | 41 |
| `/errors` | exact | scripts/patch_tg_cmds.py | 56 |
| `/start` | exact | server.py | 5362 |
| `/kairos` | exact | server.py | 5365 |
| `/report` | exact | server.py | 5370 |
| `/reset` | exact | server.py | 5378 |
| `/status` | exact | server.py | 5385 |
| `/stats` | exact | server.py | 5392 |
| `/lights` | exact | server.py | 5481 |
| `/covers` | exact | server.py | 5505 |
| `/weather` | exact | server.py | 5521 |
| `/locks` | exact | server.py | 5531 |
| `/media` | exact | server.py | 5541 |
| `/temp` | exact | server.py | 5551 |
| `/health` | exact | server.py | 5577 |
| `/brain` | exact | server.py | 5590 |
| `/learn` | exact | server.py | 5607 |
| `/patterns` | exact | server.py | 5624 |
| `/email` | exact | server.py | 5633 |
| `/scenes` | exact | server.py | 5641 |
| `/summary` | exact | server.py | 5660 |
| `/suggest` | exact | server.py | 5668 |
| `/anomaly` | exact | server.py | 5685 |
| `/diag` | exact | server.py | 5693 |
| `/home` | exact | server.py | 5779 |
| `/rooms` | exact | server.py | 5816 |
| `/devices` | prefix | server.py | 5840 |
| `/find` | prefix | server.py | 5851 |
| `/scenes_dynamic` | exact | server.py | 5873 |
| `/scenes2` | exact | server.py | 5902 |
| `/alloff` | exact | server.py | 5928 |
| `/find` | exact | server.py | 5937 |
| `/cam` | exact | server.py | 5967 |
| `/approvals` | exact | server.py | 5980 |
| `/backup` | exact | server.py | 5993 |
| `/restart` | exact | server.py | 6003 |
| `/errors` | exact | server.py | 6018 |
| `/update_stock` | prefix | server.py | 6035 |
| `/log` | exact | server.py | 6046 |
| `/crash` | exact | server.py | 6051 |
| `/me` | exact | server.py | 6055 |
| `/suggest_tasks` | exact | server.py | 6121 |
| `/life` | exact | server.py | 6129 |
| `/week_summary` | exact | server.py | 6189 |
| `/inbox` | exact | server.py | 6222 |
| `/inbox_week` | exact | server.py | 6226 |
| `/inbox48` | exact | server.py | 6229 |
| `/tasks` | exact | server.py | 6237 |
| `/news` | exact | server.py | 6253 |
| `/news_now` | exact | server.py | 6261 |
| `/news_sources` | exact | server.py | 6275 |
| `/trade` | exact | server.py | 6280 |
| `/close` | exact | server.py | 6311 |
| `/trades` | exact | server.py | 6334 |
| `/journal` | exact | server.py | 6349 |
| `/add_expense` | exact | server.py | 6375 |
| `/spent` | exact | server.py | 6386 |
| `/expenses` | exact | server.py | 6393 |
| `/contacts` | exact | server.py | 6398 |
| `/occasions` | exact | server.py | 6402 |
| `/person` | exact | server.py | 6408 |
| `/فرص` | exact | server.py | 6418 |
| `/تقييم` | exact | server.py | 6467 |
| `/stocks` | exact | server.py | 6491 |
| `/price` | prefix | server.py | 6495 |
| `/radar` | exact | server.py | 6500 |
| `/radar_add` | prefix | server.py | 6504 |
| `/radar_remove` | prefix | server.py | 6509 |
| `/radar_check` | prefix | server.py | 6514 |
| `/radar_last` | exact | server.py | 6519 |
| `/radar_status` | exact | server.py | 6528 |
| `/radar_top` | exact | server.py | 6532 |
| `/radar_toggle` | exact | server.py | 6536 |
| `/news` | prefix | server.py | 6548 |
| `/remind` | prefix | server.py | 6554 |
| `/reminders` | prefix | server.py | 6554 |
| `/reminders` | exact | server.py | 6564 |
| `/cancel` | prefix | server.py | 6569 |
| `/health_log` | exact | server.py | 6578 |
| `/health_summary` | exact | server.py | 6583 |
| `/health_streak` | exact | server.py | 6588 |
| `/trade_review` | exact | server.py | 6604 |
| `/tv_watchlist` | exact | server.py | 6611 |
| `/tv_add` | exact | server.py | 6615 |
| `/tv_remove` | exact | server.py | 6620 |
| `/tv_last` | exact | server.py | 6625 |
| `/tv_summary` | exact | server.py | 6630 |
| `/tv_test` | exact | server.py | 6635 |
| `/tv_stats` | exact | server.py | 6639 |
| `/tv_sync` | exact | server.py | 6643 |
| `/kpi` | exact | server.py | 6648 |
| `/menu` | exact | server.py | 6655 |
| `/shift` | exact | server.py | 6659 |
| `/schedule` | exact | server.py | 6672 |
| `/expense` | prefix | server.py | 6681 |
| `/expenses` | prefix | server.py | 6681 |
| `/health` | prefix | server.py | 6701 |
| `/ping` | exact | server.py | 6722 |
| `/help` | exact | server.py | 6735 |
| `/family` | exact | server.py | 6764 |
| `/guardian` | exact | server.py | 6771 |
| `/timeline` | exact | server.py | 6778 |
| `/today` | exact | server.py | 6791 |
| `/tomorrow` | exact | server.py | 6822 |
| `/week` | exact | server.py | 6851 |
| `/agenda` | exact | server.py | 6860 |
| `/habits` | exact | server.py | 6874 |
| `/cost` | exact | server.py | 6881 |
| `/feedback` | exact | server.py | 6901 |
| `/corrections` | exact | server.py | 6930 |
| `/plans` | exact | server.py | 6978 |
| `/mode` | exact | server.py | 7009 |


## Schedules

| kind | schedule | target |
| --- | --- | --- |
| cron | 10 3 * * * | /bin/bash /home/pi/master_ai/scripts/backup_now.sh >> /home/ |
| cron | 30 3 * * * | /bin/bash /home/pi/master_ai/scripts/gdrive_backup.sh >> /ho |
| cron | 0 4 * * * | entity_map_generator.py |
| cron | 30 5 * * * | tg_morning_report.py |
| cron | 0 */6 * * * | health_watchdog.py |
| cron | */15 9-12 * * 0-4 | _tools/intraday_refresh.py |
| cron | */2 9-12 * * 0-4 | _tools/intraday_refresh.py |
| cron | 0 14 * * 0-4 | _tools/backfill_daily_bars.py |
| cron | 20 14 * * 0-4 | _tools/daily_signal_review.py |
| cron | 30 14 * * * | _tools/nas_backup.py |
| asyncio_startup_task | on_startup | _learn_worker |
| asyncio_startup_task | on_startup | _send_progress_after_delay |
| asyncio_startup_task | on_startup | fn |
| asyncio_startup_task | on_startup | _daily_trading_summary_loop |
| asyncio_startup_task | on_startup | _daily_trading_summary_loop |
| asyncio_startup_task | on_startup | radar_loop |
| asyncio_startup_task | on_startup | _run_bg |
| asyncio_startup_task | on_startup | event_processor_loop |
| asyncio_startup_task | on_startup | telegram_polling_loop |
| asyncio_startup_task | on_startup | weather_alert_loop |
| asyncio_startup_task | on_startup | nightly_summary_scheduler |
| asyncio_startup_task | on_startup | morning_report_scheduler |
| asyncio_startup_task | on_startup | shift_alert_loop |
| asyncio_startup_task | on_startup | entity_health_check_loop |
| asyncio_startup_task | on_startup | brain_snapshot_loop |
| asyncio_startup_task | on_startup | brain_weekly_insight |
| asyncio_startup_task | on_startup | weekly_trading_report_scheduler |
| asyncio_startup_task | on_startup | confluence_scan_loop |
| asyncio_startup_task | on_startup | start_world_state |
| asyncio_startup_task | on_startup | brain_nightly_learning |
| asyncio_startup_task | on_startup | feedback_learning_loop |
| asyncio_startup_task | on_startup | plan_check_loop |
| asyncio_startup_task | on_startup | daily_collection_scheduler |
| asyncio_startup_task | on_startup | market_hours_scanner |
| asyncio_startup_task | on_startup | review_scheduler |
| asyncio_startup_task | on_startup | analysis_daily_scheduler |
| asyncio_startup_task | on_startup | tg_alert_loop |
| asyncio_startup_task | on_startup | proactive_suggestion_loop |
| asyncio_startup_task | on_startup | calendar_sync_loop |
| asyncio_startup_task | on_startup | run_reminder_loop |
| asyncio_startup_task | on_startup | reminder_loop |
| asyncio_startup_task | on_startup | news_scheduler |
| asyncio_startup_task | on_startup | _news_digest_loop |
| asyncio_startup_task | on_startup | radar_loop |
| asyncio_startup_task | on_startup | _daily_trading_summary_loop |
| asyncio_startup_task | on_startup | proactive_loop |
| asyncio_startup_task | on_startup | backup_loop |
| asyncio_startup_task | on_startup | stats_save_loop |
| asyncio_startup_task | on_startup | _dream_scheduler |
| asyncio_startup_task | on_startup | _brain_scheduler |
| asyncio_startup_task | on_startup | learn_from_result |
| asyncio_startup_task | on_startup | _send_progress_after_delay |
| asyncio_startup_task | on_startup | tg_handle_callback |
| asyncio_startup_task | on_startup | tg_handle_message |
| asyncio_startup_task | on_startup | _refresh_loop |


## Shell scripts in _tools/


**_tools/fix_trading_dir.sh**


**_tools/restart_master_ai.sh**

- python (line 18): `curl -s http://localhost:9000/health | python3 -c "`
- systemctl (line 6): `sudo systemctl restart master-ai.service`
- systemctl (line 11): `systemctl is-active master-ai.service`
- systemctl (line 13): `systemctl status master-ai.service --no-pager -l | head -15`

**_tools/run_task.sh**


**_tools/test_ops_guard.sh**

- python (line 36): `chk "tg_send.py"            2 "$G" "python3 _tools/tg_send.py hi"`
- python (line 44): `chk "python execute DELETE"  2 "$G" "python3 -c \"c.execute('DELETE FROM x')\""`
- systemctl (line 24): `chk "systemctl restart"     2 "$GP" "sudo systemctl restart master_ai"`


## Endpoint reverse index

_For each endpoint: where it is defined and every detected consumer._
_Endpoints with no consumers are retire-safely candidates — but verify dynamic callers._


### `/action/execute`

- **Defined:** `server.py:4908` `POST` handler=`action_execute_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/agent`

- **Defined:** `server.py:4191` `POST` handler=`agent_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/aliases`

- **Defined:** `server.py:8437` `GET` handler=`aliases_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/anomalies`

- **Defined:** `server.py:4058` `GET` handler=`get_anomalies_ep`
- **Defined:** `server.py:9285` `GET` handler=`anomalies_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/analyze`

- **Defined:** `server.py:8115` `GET` handler=`api_analyze`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/analyze/refresh`

- **Defined:** `server.py:8142` `POST` handler=`api_analyze_refresh`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/analyze/refresh-all`

- **Defined:** `server.py:8148` `POST` handler=`api_analyze_refresh_all`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/brain/stats`

- **Defined:** `dashboard_api.py:3500` `GET` handler=`api_brain_stats`
- **[fetch]** `www/trading/system.html:335`


### `/api/collect-now`

- **Defined:** `dashboard_api.py:3260` `POST` handler=`api_collect_now`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/context-health`

- **Defined:** `dashboard_api.py:3589` `GET` handler=`api_context_health`
- **[fetch]** `www/trading/system.html:356`


### `/api/data-freshness`

- **Defined:** `dashboard_api.py:3164` `GET` handler=`api_data_freshness`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/data-health`

- **Defined:** `dashboard_api.py:3153` `GET` handler=`api_data_health`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/decisions-now`

- **Defined:** `server.py:3615` `GET` handler=`api_decisions_now`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/flags`

- **Defined:** `server.py:8071` `GET` handler=`get_feature_flags`
- **[fetch]** `www/trading/system.html:419`


### `/api/flags/{name}/toggle`

- **Defined:** `server.py:8075` `POST` handler=`toggle_feature_flag`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/hooks/log`

- **Defined:** `server.py:8280` `GET` handler=`get_hooks_log`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/hooks/stats`

- **Defined:** `server.py:8276` `GET` handler=`get_hooks_stats`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/intent-analytics`

- **Defined:** `dashboard_api.py:3439` `GET` handler=`api_intent_analytics`
- **[fetch]** `www/trading/system.html:300`


### `/api/kairos/log`

- **Defined:** `server.py:8269` `GET` handler=`get_kairos_log`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/kairos/status`

- **Defined:** `server.py:8263` `GET` handler=`get_kairos_status`
- **[fetch]** `www/trading/system.html:399`


### `/api/latency-stats`

- **Defined:** `dashboard_api.py:3638` `GET` handler=`api_latency_stats`
- **[fetch]** `www/trading/system.html:379`


### `/api/memory-extraction/stats`

- **Defined:** `dashboard_api.py:3387` `GET` handler=`api_memory_extraction_stats`
- **[fetch]** `www/trading/system.html:273`


### `/api/news`

- **Defined:** `server.py:8300` `GET` handler=`api_news`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/news/refresh-boursa`

- **Defined:** `server.py:8314` `POST` handler=`api_news_refresh_boursa`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/news/refresh-gemini`

- **Defined:** `server.py:8337` `POST` handler=`api_news_refresh_gemini`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/paper-trade/close`

- **Defined:** `dashboard_api.py:2400` `POST` handler=`api_paper_trade_close`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/paper-trade/open`

- **Defined:** `dashboard_api.py:2388` `POST` handler=`api_paper_trade_open`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/portfolio-alert-ack`

- **Defined:** `dashboard_api.py:3341` `POST` handler=`api_portfolio_alert_ack`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/portfolio-monitor`

- **Defined:** `dashboard_api.py:3328` `POST` handler=`api_portfolio_monitor`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/portfolio-status`

- **Defined:** `dashboard_api.py:3298` `GET` handler=`api_portfolio_status`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/portfolio/add-more`

- **Defined:** `server.py:8195` `POST` handler=`api_add_more`
- **[fetch]** `www/trading/positions.html:670`


### `/api/portfolio/partial-sell`

- **Defined:** `server.py:8174` `POST` handler=`api_partial_sell`
- **[fetch]** `www/trading/positions.html:640`


### `/api/portfolio/transactions/{trade_id}`

- **Defined:** `server.py:8216` `GET` handler=`api_trade_transactions`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/radar/progress`

- **Defined:** `dashboard_api.py:3632` `GET` handler=`api_radar_progress`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/refresh-analysis`

- **Defined:** `server.py:8163` `POST` handler=`api_refresh_analysis`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/review-now`

- **Defined:** `server.py:3673` `POST` handler=`manual_review`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/risk-config`

- **Defined:** `dashboard_api.py:3117` `GET` handler=`api_risk_config_get`
- **Defined:** `dashboard_api.py:3126` `POST` handler=`api_risk_config_update`
- **[fetch]** `www/trading/positions.html:682`
- **[fetch]** `www/trading/positions.html:714`


### `/api/service-health`

- **Defined:** `server.py:8090` `GET` handler=`get_service_health`
- **[fetch]** `www/trading/system.html:230`


### `/api/skills`

- **Defined:** `dashboard_api.py:3671` `GET` handler=`api_skills`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/stocks/profiles`

- **Defined:** `server.py:3659` `GET` handler=`get_all_stock_profiles`
- **[fetch]** `www/trading/personality.html:215`


### `/api/stocks/symbol/{symbol}`

- **Defined:** `server.py:3653` `GET` handler=`get_stock_personality`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/symbols`

- **Defined:** `dashboard_api.py:3358` `GET` handler=`api_symbols`
- **[fetch]** `www/trading/positions.html:584`


### `/api/tasks`

- **Defined:** `server.py:8228` `GET` handler=`get_tasks`
- **[fetch]** `www/trading/system.html:256`


### `/api/tools`

- **Defined:** `server.py:8284` `GET` handler=`get_tools`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/tools/{name}`

- **Defined:** `server.py:8290` `GET` handler=`get_tool_detail`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/api/trade/close`

- **Defined:** `dashboard_api.py:3046` `POST` handler=`api_trade_close`
- **[fetch]** `www/trading/positions.html:823`


### `/api/trade/open`

- **Defined:** `dashboard_api.py:3016` `POST` handler=`api_trade_open`
- **[fetch]** `www/trading/positions.html:792`


### `/api/trade/update`

- **Defined:** `dashboard_api.py:3063` `POST` handler=`api_trade_update`
- **[fetch]** `www/trading/positions.html:860`


### `/approvals/pending`

- **Defined:** `server.py:4340` `GET` handler=`list_pending_approvals`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/approve/{approval_id}`

- **Defined:** `server.py:4292` `POST` handler=`approve_action`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/ask`

- **Defined:** `server.py:4075` `POST` handler=`ask`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/audit`

- **Defined:** `server.py:4841` `GET` handler=`get_audit`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/brain/analytics`

- **Defined:** `server.py:3296` `GET` handler=`analytics_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/brain/diag`

- **Defined:** `server.py:3316` `GET` handler=`brain_diag_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/brain/expertise`

- **Defined:** `server.py:5163` `GET` handler=`brain_expertise`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/brain/feedback`

- **Defined:** `server.py:3308` `POST` handler=`feedback_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/brain/stats`

- **Defined:** `server.py:3251` `GET` handler=`brain_stats_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/brain/users`

- **Defined:** `server.py:3302` `GET` handler=`users_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/bridge/status`

- **Defined:** `server.py:3109` `GET` handler=`bridge_circuit_status`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/calendar/stats`

- **Defined:** `server.py:3513` `GET` handler=`calendar_stats_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/calendar/sync`

- **Defined:** `server.py:3523` `POST` handler=`calendar_sync_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/chat/clear`

- **Defined:** `server.py:8365` `POST` handler=`clear_chat_history`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/classify`

- **Defined:** `server.py:9250` `POST` handler=`classify_msg`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/claude`

- **Defined:** `server.py:4496` `GET` handler=`claude_context`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/corrections`

- **Defined:** `server.py:9214` `GET` handler=`get_corrections_stats`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/corrections/decay`

- **Defined:** `server.py:9223` `POST` handler=`decay_corrections_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/cost`

- **Defined:** `server.py:9297` `GET` handler=`cost_dashboard`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/daily-snapshot/refresh`

- **Defined:** `server.py:3127` `POST` handler=`refresh_daily_snapshot_manual`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard`

- **Defined:** `dashboard_api.py:151` `GET` handler=`ha_dashboard`
- **[fetch]** `www/trading/assistant.html:131`
- **[fetch]** `www/trading/calendar.html:123`
- **[fetch]** `www/trading/home-control.html:112`
- **[fetch]** `www/trading/home.html:272`
- **[fetch]** `www/trading/system.html:434`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:196` sensor=`master_ai_dashboard`


### `/dashboard/alerts`

- **Defined:** `dashboard_api.py:1336` `GET` handler=`ha_dashboard_alerts`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:376` sensor=`master_ai_alerts`


### `/dashboard/analysis`

- **Defined:** `dashboard_api.py:1487` `GET` handler=`ha_dashboard_analysis`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:336` sensor=`master_ai_analysis`


### `/dashboard/brain`

- **Defined:** `dashboard_api.py:2599` `GET` handler=`dashboard_brain`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/brain-insights`

- **Defined:** `dashboard_api.py:2920` `GET` handler=`dashboard_brain_insights`
- **[fetch]** `www/trading/brain.html:141`


### `/dashboard/bridge`

- **Defined:** `dashboard_api.py:1879` `GET` handler=`dashboard_bridge`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/bridge/{symbol}`

- **Defined:** `dashboard_api.py:1903` `GET` handler=`dashboard_bridge_symbol`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/cmd`

- **Defined:** `dashboard_api.py:399` `POST` handler=`dashboard_cmd`
- **[ha_rest_command]** `/var/lib/homeassistant/homeassistant/configuration.yaml:62`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:19`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:37`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:55`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:73`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:91`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:109`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:127`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:145`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:163`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:181`
- **[ha_script]** `/var/lib/homeassistant/homeassistant/scripts.yaml:199`


### `/dashboard/confluence`

- **Defined:** `dashboard_api.py:1423` `GET` handler=`ha_dashboard_confluence`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:399` sensor=`master_ai_confluence`


### `/dashboard/ema-active`

- **Defined:** `server.py:3798` `GET` handler=`dashboard_ema_active`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/ema-crosses`

- **Defined:** `server.py:3686` `GET` handler=`dashboard_ema_crosses`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/ema-live`

- **Defined:** `server.py:3880` `GET` handler=`dashboard_ema_live`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/ema-proximity`

- **Defined:** `server.py:3753` `GET` handler=`dashboard_ema_proximity`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/equity`

- **Defined:** `dashboard_api.py:2414` `GET` handler=`dashboard_equity`
- **[fetch]** `www/trading/journal.html:337`


### `/dashboard/extended`

- **Defined:** `dashboard_api.py:1646` `GET` handler=`ha_dashboard_extended`
- **[fetch]** `www/trading/email.html:121`
- **[fetch]** `www/trading/home.html:273`
- **[fetch]** `www/trading/news.html:107`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:247` sensor=`master_ai_extended`


### `/dashboard/jobs`

- **Defined:** `dashboard_api.py:431` `GET` handler=`dashboard_jobs_list`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/journal`

- **Defined:** `dashboard_api.py:1212` `GET` handler=`ha_dashboard_journal`
- **[fetch]** `www/trading/journal.html:329`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:355` sensor=`master_ai_journal`


### `/dashboard/paper-trading`

- **Defined:** `dashboard_api.py:2378` `GET` handler=`dashboard_paper_trading`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/portfolio`

- **Defined:** `dashboard_api.py:1004` `GET` handler=`ha_dashboard_portfolio`
- **[fetch]** `www/trading/personality.html:238`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:318` sensor=`master_ai_portfolio`


### `/dashboard/radar`

- **Defined:** `dashboard_api.py:441` `GET` handler=`ha_dashboard_radar`
- **[fetch]** `www/trading/personality.html:258`
- **[fetch]** `www/trading/personality.html:273`
- **[fetch]** `www/trading/signals.html:669`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:294` sensor=`master_ai_radar`


### `/dashboard/regime`

- **Defined:** `dashboard_api.py:2565` `GET` handler=`dashboard_regime`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/reviews`

- **Defined:** `server.py:3666` `GET` handler=`dashboard_reviews`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/risk-status`

- **Defined:** `dashboard_api.py:2424` `GET` handler=`dashboard_risk_status`
- **[fetch]** `www/trading/positions.html:1255`


### `/dashboard/scalper`

- **Defined:** `dashboard_api.py:2434` `GET` handler=`dashboard_scalper`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/signals`

- **Defined:** `dashboard_api.py:1965` `GET` handler=`dashboard_signals`
- **[fetch]** `www/trading/signals.html:668`
- **[ha_sensor]** `/var/lib/homeassistant/homeassistant/configuration.yaml:424` sensor=`master_ai_signals`


### `/dashboard/signals-30m`

- **Defined:** `dashboard_api.py:2119` `GET` handler=`dashboard_signals_30m`
- **[fetch]** `www/trading/personality.html:248`
- **[fetch]** `www/trading/personality.html:290`
- **[fetch]** `www/trading/signals.html:670`


### `/dashboard/signals-daily`

- **Defined:** `dashboard_api.py:1980` `GET` handler=`dashboard_signals_daily`
- **[fetch]** `www/trading/radar.html:738`


### `/dashboard/strategies`

- **Defined:** `dashboard_api.py:2940` `GET` handler=`dashboard_strategies`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dashboard/swing`

- **Defined:** `dashboard_api.py:2126` `GET` handler=`dashboard_swing`
- **[fetch]** `www/trading/home.html:274`
- **[fetch]** `www/trading/radar.html:744`


### `/debug/test_approval`

- **Defined:** `server.py:3346` `POST` handler=`debug_test_approval`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/decompose`

- **Defined:** `server.py:9255` `POST` handler=`decompose_msg`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/deploy`

- **Defined:** `server.py:4707` `POST` handler=`deploy_file`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dev/context`

- **Defined:** `server.py:5181` `GET` handler=`dev_context`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dream/run`

- **Defined:** `server.py:3280` `POST` handler=`dream_run_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/dream/status`

- **Defined:** `server.py:3271` `GET` handler=`dream_status_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/entity-map/arabize`

- **Defined:** `server.py:8498` `POST` handler=`entity_map_arabize`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/entity-map/health`

- **Defined:** `server.py:8485` `GET` handler=`entity_map_health`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/event`

- **Defined:** `server.py:4937` `POST` handler=`ingest_event`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/event_rules`

- **Defined:** `server.py:4985` `GET` handler=`get_event_rules`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/events`

- **Defined:** `server.py:4974` `GET` handler=`list_events_ep`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/events/{event_id}`

- **Defined:** `server.py:4978` `GET` handler=`get_event_ep`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/feedback/digest`

- **Defined:** `server.py:9274` `GET` handler=`feedback_digest_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/feedback/stats`

- **Defined:** `server.py:9266` `GET` handler=`feedback_stats_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/gmail/auth`

- **Defined:** `server.py:3362` `GET` handler=`gmail_auth_start`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/gmail/callback`

- **Defined:** `server.py:3397` `GET` handler=`gmail_auth_callback`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/google/auth`

- **Defined:** `server.py:3453` `GET` handler=`google_auth_start`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/google/auth/status`

- **Defined:** `server.py:3503` `GET` handler=`google_auth_status`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/google/callback`

- **Defined:** `server.py:3471` `GET` handler=`google_auth_callback`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/ha/service`

- **Defined:** `server.py:4256` `POST` handler=`ha_call_service_ep`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/ha/states`

- **Defined:** `server.py:4265` `GET` handler=`ha_get_states`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/ha/states/{entity_id:path}`

- **Defined:** `server.py:4270` `GET` handler=`ha_get_state`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/health`

- **Defined:** `server.py:3973` `GET` handler=`health`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/health/external`

- **Defined:** `server.py:8046` `GET` handler=`health_external`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/health/external/test`

- **Defined:** `server.py:8404` `POST` handler=`health_external_test`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/history/{entity_id:path}`

- **Defined:** `server.py:3993` `GET` handler=`entity_history_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/knowledge`

- **Defined:** `server.py:4603` `GET` handler=`list_knowledge`
- **Defined:** `server.py:4626` `POST` handler=`create_knowledge`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/knowledge/{kid}`

- **Defined:** `server.py:4617` `GET` handler=`get_knowledge`
- **Defined:** `server.py:4637` `PUT` handler=`update_knowledge`
- **Defined:** `server.py:4649` `DELETE` handler=`delete_knowledge`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/kpi`

- **Defined:** `server.py:9308` `GET` handler=`kpi_dashboard`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/memory`

- **Defined:** `server.py:4747` `POST` handler=`create_memory_ep`
- **Defined:** `server.py:4756` `GET` handler=`list_memories_ep`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/memory/message`

- **Defined:** `server.py:4798` `POST` handler=`save_msg`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/memory/recent`

- **Defined:** `server.py:4791` `GET` handler=`memory_recent`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/memory/stats`

- **Defined:** `server.py:4769` `GET` handler=`mem_stats`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/patterns`

- **Defined:** `server.py:4040` `GET` handler=`patterns_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/patterns/learn`

- **Defined:** `server.py:4067` `POST` handler=`patterns_learn_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/patterns/suggestions`

- **Defined:** `server.py:4051` `GET` handler=`patterns_suggestions_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/plugins`

- **Defined:** `server.py:4902` `GET` handler=`list_plugins`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/plugins/{name}/disable`

- **Defined:** `server.py:4922` `POST` handler=`disable_plugin`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/plugins/{name}/enable`

- **Defined:** `server.py:4915` `POST` handler=`enable_plugin`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/router/stats`

- **Defined:** `server.py:8446` `GET` handler=`router_stats_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/schema`

- **Defined:** `server.py:4867` `GET` handler=`schema_status`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/schema/ensure`

- **Defined:** `server.py:4887` `POST` handler=`schema_ensure`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/sessions`

- **Defined:** `server.py:4556` `POST` handler=`create_session`
- **Defined:** `server.py:4568` `GET` handler=`list_sessions`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/sessions/latest`

- **Defined:** `server.py:4578` `GET` handler=`latest_session`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/shift`

- **Defined:** `server.py:4469` `GET` handler=`shift_info`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/ssh/run`

- **Defined:** `server.py:4283` `POST` handler=`ssh_run`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/stability`

- **Defined:** `server.py:8422` `GET` handler=`stability_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/stats/capture`

- **Defined:** `server.py:4454` `POST` handler=`stats_capture`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/stats/daily`

- **Defined:** `server.py:4439` `GET` handler=`stats_daily`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/stocks/alerts`

- **Defined:** `server.py:4688` `GET` handler=`stock_alerts_history`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/stocks/portfolio`

- **Defined:** `server.py:4679` `GET` handler=`stock_portfolio`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory`

- **Defined:** `server.py:9142` `GET` handler=`smem_stats`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/context`

- **Defined:** `server.py:9147` `GET` handler=`smem_context`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/correction`

- **Defined:** `server.py:9174` `POST` handler=`smem_save_correction`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/decay`

- **Defined:** `server.py:9203` `POST` handler=`smem_decay`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/event`

- **Defined:** `server.py:9163` `POST` handler=`smem_save_event`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/fact`

- **Defined:** `server.py:9152` `POST` handler=`smem_save_fact`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/migrate`

- **Defined:** `server.py:9193` `POST` handler=`smem_migrate`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/search`

- **Defined:** `server.py:9184` `GET` handler=`smem_search`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/seed`

- **Defined:** `server.py:9198` `POST` handler=`smem_seed`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/structured-memory/{memory_id}`

- **Defined:** `server.py:9209` `DELETE` handler=`smem_delete`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/system/backup`

- **Defined:** `server.py:3265` `POST` handler=`backup_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/system/context`

- **Defined:** `server.py:5019` `GET` handler=`system_context`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/system/diag`

- **Defined:** `server.py:3258` `GET` handler=`system_diag_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/system/knowledge`

- **Defined:** `server.py:5142` `GET` handler=`system_knowledge_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/system/knowledge/summary`

- **Defined:** `server.py:5152` `GET` handler=`system_knowledge_summary`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/tasks`

- **Defined:** `server.py:4662` `GET` handler=`list_tasks_ep`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/tasks/{task_id}`

- **Defined:** `server.py:4667` `GET` handler=`get_task_ep`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/tg/stats`

- **Defined:** `server.py:8374` `GET` handler=`tg_stats`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/tips`

- **Defined:** `server.py:3289` `GET` handler=`tips_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/tool-stats`

- **Defined:** `server.py:3545` `GET` handler=`tool_stats_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/traces`

- **Defined:** `server.py:9242` `GET` handler=`traces_list`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/traces/stats`

- **Defined:** `server.py:9246` `GET` handler=`traces_stats`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/trading/analysis`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:22`


### `/trading/assistant`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:20`


### `/trading/brain`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:11`


### `/trading/calendar`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:17`


### `/trading/decisions`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:23`


### `/trading/email`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:19`


### `/trading/home`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:6`


### `/trading/home-control`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:21`


### `/trading/journal`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:16`


### `/trading/news`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:18`


### `/trading/positions`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:10`


### `/trading/radar`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:8`


### `/trading/signals`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:9`


### `/trading/swing`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:7`


### `/trading/system`

- **Defined:** _(not in scanned files)_
- **[nav_link]** `www/trading/nav.js:12`


### `/trading/{page}`

- **Defined:** `server.py:3156` `GET` handler=`serve_trading_page`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/tradingview/webhook`

- **Defined:** `server.py:3554` `POST` handler=`tradingview_webhook`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/users`

- **Defined:** `server.py:4812` `POST` handler=`create_user`
- **Defined:** `server.py:4827` `GET` handler=`list_users`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/webhook/event`

- **Defined:** `server.py:5004` `POST` handler=`webhook_event`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/webhook/event/{token}`

- **Defined:** `server.py:4992` `POST` handler=`webhook_event_legacy`
- **[ha_rest_command]** `/var/lib/homeassistant/homeassistant/configuration.yaml:49`
- **[ha_automation]** `/var/lib/homeassistant/homeassistant/automations.yaml:455`
- **[ha_automation]** `/var/lib/homeassistant/homeassistant/automations.yaml:480`
- **[ha_automation]** `/var/lib/homeassistant/homeassistant/automations.yaml:499`
- **[ha_automation]** `/var/lib/homeassistant/homeassistant/automations.yaml:694`


### `/win/jobs`

- **Defined:** `server.py:4421` `GET` handler=`win_jobs`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/win/poll`

- **Defined:** `server.py:4398` `GET` handler=`win_poll`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/win/register`

- **Defined:** `server.py:4390` `POST` handler=`win_register`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/win/report`

- **Defined:** `server.py:4409` `POST` handler=`win_report`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


### `/world-state`

- **Defined:** `server.py:3534` `GET` handler=`world_state_endpoint`
- **Consumers:** NONE — retire-safely candidate (verify dynamic callers)


## Dynamic requests (unresolvable URLs)

_fetch() calls whose URL is built at runtime — base path noted where detectable._

- `www/trading/analysis.html:253` — `'/api/analyze?symbol='+encodeURIComponent(symbol));`
- `www/trading/decisions.html:582` — `API + '?t=' + Date.now(), {cache:'no-store'});`
- `www/trading/decisions.html:596` — `REV + '?t=' + Date.now(), {cache:'no-store'});`
- `www/trading/personality.html:233` — `'/api/stocks/symbol/'+encodeURIComponent(sym));`
- `www/trading/positions.html:726` — `'/api/analyze?symbol='+encodeURIComponent(sym));`
- `www/trading/positions.html:1248` — `API_URL, {headers: authHeaders()});`
- `www/trading/radar.html:1036` — `'/api/stocks/symbol/'+sym);`
- `www/trading/reviews.html:232` — `url);if(!r.ok)throw new Error('HTTP '+r.status);`
- `www/trading/scalper.html:517` — ``${API_BASE}/dashboard/scalper`, { headers });`
- `www/trading/signals.html:1052` — `'/api/stocks/symbol/'+sym);`
- `www/trading/strategies.html:137` — `API + '/dashboard/strategies');`
- `www/trading/swing.html:542` — `API+'?t='+Date.now(), {cache:'no-store'});`
- `www/trading/system.html:429` — `'/api/flags/'+n+'/toggle',{method:'POST'});setTimeout(loadFlags,300)}catch(e){}};`


## SQL table reverse index


### `__future__`

- **READ** `indicators.py:24`
- **READ** `price_source.py:28`
- **READ** `yahoo_gate.py:17`


### `_tools`

- **READ** `_tools/backfill_daily_bars.py:14`
- **READ** `_tools/examples/test_patch.py:11`
- **READ** `_tools/patch_email_news.py:5`
- **READ** `_tools/patchers/apply_text_patch.py:9`
- **READ** `_tools/patchers/fix_confluence_bugs.py:10`
- **READ** `_tools/phase3_patch.py:8`


### `action`

- **READ** `brain_personality.py:47`


### `adhan_script_v3`

- **READ** `_tools/replace_adhan_v2.py:2`


### `adx`

- **READ** `stock_radar.py:350`


### `alert_history`

- **CREATE** `golden_engine.py:627`
- **READ** `golden_engine.py:648`


### `all`

- **READ** `brain.py:143`
- **READ** `tg_email.py:253`


### `anomaly_engine`

- **READ** `quick_query.py:467`
- **READ** `server.py:9293`
- **READ** `tg_alerts.py:15`


### `anomaly_log`

- **READ** `dashboard_api.py:1771`


### `anthropic`

- **READ** `server.py:48`


### `apply_text_patch`

- **READ** `_tools/patch_recommendations.py:5`
- **READ** `_tools/patchers/phase1_normalize_price.py:5`
- **READ** `_tools/patchers/phase1_wire_inbox_cache.py:5`
- **READ** `_tools/patchers/phase1_wire_pe_cache.py:5`
- **READ** `_tools/patchers/phase1b_fix_audit_route_type.py:5`
- **READ** `_tools/patchers/phase2_pe_email_action.py:5`
- **READ** `_tools/patchers/phase2_radar_confirm.py:5`
- **READ** `_tools/patchers/phase2_wire_router.py:5`
- **READ** `_tools/patchers/phase3_tv_journal.py:5`
- **READ** `_tools/patchers/phase3_tv_sync.py:5`
- **READ** `_tools/patchers/phase3_tv_sync_cmd.py:5`
- **READ** `_tools/patchers/phase4_fix_cost.py:5`
- **READ** `_tools/patchers/phase4_trade_confirm.py:5`
- **READ** `_tools/patchers/phase5_daily_summary.py:5`
- **READ** `_tools/patchers/phase5_version_bump.py:5`
- **READ** `_tools/patchers/phase5_version_bump_84.py:5`
- **READ** `_tools/patchers/phase6_version_85.py:5`
- **READ** `_tools/patchers/v12_patch1.py:5`
- **READ** `_tools/patchers/v12_patch_imports.py:5`
- **READ** `_tools/patchers/v12_patch_stocks.py:5`
- **READ** `_tools/patchers/v12_patch_stocks_import.py:5`
- **READ** `_tools/patchers/v12_patch_tasks_calls.py:5`


### `approval_queue`

- **CREATE** `server.py:1065`
- **WRITE** `server.py:1309`
- **WRITE** `server.py:1338`
- **WRITE** `server.py:2143`
- **WRITE** `server.py:3354`
- **WRITE** `server.py:4309`
- **WRITE** `server.py:4336`
- **WRITE** `tg_ops.py:63`
- **READ** `server.py:4300`
- **READ** `server.py:4350`
- **READ** `tg_ops.py:40`
- **READ** `tg_ops.py:54`


### `approval_ux`

- **READ** `chat_v7.py:45`


### `arabic`

- **READ** `_deprecated/brain_backup.py:534`
- **READ** `expenses_engine.py:79`
- **READ** `memory_db.py:214`
- **READ** `world_state_delta.py:112`


### `audit`

- **READ** `_tools/patchers/fix7_trading_issues.py:80`
- **READ** `structured_memory.py:20`


### `audit_log`

- **CREATE** `server.py:1032`
- **WRITE** `_tools/patchers/phase1b_backfill_route_type.py:14`
- **WRITE** `server.py:1141`
- **WRITE** `server.py:1578`
- **WRITE** `server.py:1579`
- **READ** `_tools/patchers/phase1b_backfill_route_type.py:10`
- **READ** `_tools/patchers/phase1b_backfill_route_type.py:17`
- **READ** `_tools/patchers/phase1b_backfill_route_type.py:21`
- **READ** `_tools/patchers/phase4_fix_cost.py:14`
- **READ** `_tools/patchers/phase4_fix_cost.py:16`
- **READ** `dashboard_api.py:1721`
- **READ** `dashboard_api.py:1723`
- **READ** `server.py:4516`
- **READ** `server.py:4518`
- **READ** `server.py:4851`
- **READ** `server.py:4853`
- **READ** `server.py:4856`
- **READ** `server.py:8457`
- **READ** `server.py:8459`
- **READ** `server.py:8468`


### `auto_memory_extractor`

- **READ** `_tools/_fix_extractor_client.py:9`
- **READ** `_tools/_fix_extractor_client.py:14`
- **READ** `_tools/_int5_tg.py:24`
- **READ** `server.py:7550`


### `backup`

- **READ** `_tools/patchers/apply_text_patch.py:63`
- **READ** `dropzone_watcher.py:174`


### `bar`

- **READ** `_tools/fractal_backtest_v3.py:239`


### `bars`

- **READ** `_tools/fractal_backtest_v2.py:57`


### `birthday`

- **READ** `family_assistant.py:22`


### `brain`

- **READ** `scripts/patch_v2.py:82`
- **READ** `server.py:53`
- **READ** `signal_engine.py:952`
- **READ** `signal_engine.py:1046`
- **READ** `signal_engine.py:1058`


### `brain_analytics`

- **READ** `brain.py:124`


### `brain_core`

- **READ** `_tools/_patch_dashboard_tier3.py:171`
- **READ** `auto_memory_extractor.py:98`
- **READ** `brain.py:14`
- **READ** `brain_core.py:675`
- **READ** `chat_v7.py:652`
- **READ** `dashboard_api.py:3544`
- **READ** `memory_recall.py:56`
- **READ** `server.py:367`
- **READ** `server.py:2453`
- **READ** `server.py:4130`
- **READ** `server.py:4207`
- **READ** `server.py:5160`
- **READ** `server.py:5171`
- **READ** `server.py:7632`
- **READ** `server.py:7999`


### `brain_learning`

- **READ** `brain.py:31`
- **READ** `brain_learning.py:7`
- **READ** `server.py:147`
- **READ** `server.py:148`
- **READ** `server.py:149`
- **READ** `server.py:150`
- **READ** `server.py:151`
- **READ** `server.py:158`
- **READ** `server.py:159`
- **READ** `tg_intent_router.py:317`
- **READ** `tg_intent_router.py:326`
- **READ** `tg_intent_router.py:335`
- **READ** `tg_intent_router.py:344`
- **READ** `tg_intent_router.py:1133`
- **READ** `tg_intent_router.py:1158`
- **READ** `tg_morning_report.py:158`


### `brain_multiuser`

- **READ** `brain.py:106`


### `brain_observability`

- **READ** `brain.py:85`


### `brain_personality`

- **READ** `brain.py:52`


### `brain_proactive`

- **READ** `brain.py:68`


### `brain_weekly_reports`

- **CREATE** `trading_brain.py:114`
- **WRITE** `trading_brain.py:801`
- **READ** `trading_brain.py:863`


### `bridge`

- **READ** `_tools/fractal_backtest.py:47`
- **READ** `_tools/fractal_backtest_v3.py:226`
- **READ** `brain_backfill.py:3`
- **READ** `brain_backfill.py:34`
- **READ** `data_integrity.py:119`
- **READ** `kse_data_collector.py:139`
- **READ** `server.py:3882`
- **READ** `signal_engine.py:1234`
- **READ** `sr_engine.py:137`
- **READ** `stock_radar.py:758`
- **READ** `stock_radar.py:1295`


### `bridge_client`

- **READ** `_tools/_debug_ema.py:20`
- **READ** `_tools/_debug_ema.py:75`
- **READ** `_tools/_patch_degraded_mode.py:302`
- **READ** `_tools/_patch_degraded_mode.py:303`
- **READ** `_tools/_patch_expand_tools_hooks.py:18`
- **READ** `_tools/_patch_expand_tools_hooks.py:48`
- **READ** `_tools/_patch_health.py:40`
- **READ** `_tools/_patch_phase6.py:55`
- **READ** `dashboard_api.py:1886`
- **READ** `dashboard_api.py:1899`
- **READ** `dashboard_api.py:1910`
- **READ** `data_integrity.py:121`
- **READ** `gemini_scanner.py:193`
- **READ** `kairos.py:207`
- **READ** `server.py:2912`
- **READ** `server.py:3037`
- **READ** `server.py:3120`
- **READ** `server.py:3140`
- **READ** `server.py:3890`
- **READ** `server.py:8099`
- **READ** `service_health.py:110`
- **READ** `signal_engine.py:1329`
- **READ** `signal_engine.py:1342`
- **READ** `signal_engine.py:1394`
- **READ** `signal_engine.py:1405`
- **READ** `signal_engine.py:1612`
- **READ** `trading_brain.py:374`


### `buy_now_shadow`

- **CREATE** `gemini_scanner.py:512`
- **WRITE** `gemini_scanner.py:527`


### `cache`

- **WRITE** `world_state.py:245`
- **READ** `_tools/import_test.py:10`
- **READ** `calendar_engine.py:268`
- **READ** `calendar_engine.py:276`
- **READ** `calendar_engine.py:284`
- **READ** `world_state.py:3`


### `calendar_conflicts`

- **CREATE** `calendar_db.py:104`
- **WRITE** `calendar_db.py:397`
- **READ** `calendar_db.py:275`
- **DELETE** `calendar_db.py:275`


### `calendar_db`

- **READ** `calendar_engine.py:18`
- **READ** `calendar_reminders.py:11`
- **READ** `server.py:3517`


### `calendar_engine`

- **READ** `chat_v7.py:614`
- **READ** `chat_v7.py:626`
- **READ** `chat_v7.py:630`
- **READ** `quick_query.py:297`
- **READ** `quick_query.py:320`
- **READ** `quick_query.py:328`
- **READ** `server.py:2712`
- **READ** `server.py:3527`
- **READ** `server.py:6135`
- **READ** `server.py:6793`
- **READ** `server.py:6824`
- **READ** `server.py:6853`
- **READ** `server.py:6862`
- **READ** `tg_morning_report.py:221`


### `calendar_events`

- **CREATE** `calendar_db.py:62`
- **WRITE** `calendar_db.py:172`
- **WRITE** `calendar_db.py:196`
- **WRITE** `calendar_db.py:233`
- **READ** `calendar_db.py:166`
- **READ** `calendar_db.py:246`
- **READ** `calendar_db.py:261`
- **READ** `calendar_db.py:273`
- **READ** `calendar_db.py:352`
- **READ** `calendar_db.py:432`
- **READ** `dashboard_api.py:248`
- **READ** `dashboard_api.py:249`
- **READ** `dashboard_api.py:1674`
- **READ** `domain_kpis.py:72`
- **READ** `domain_kpis.py:73`
- **READ** `priority_engine.py:50`
- **DELETE** `calendar_db.py:273`


### `calendar_parse_log`

- **CREATE** `calendar_db.py:116`
- **WRITE** `calendar_db.py:414`


### `calendar_reminders`

- **CREATE** `calendar_db.py:88`
- **WRITE** `calendar_db.py:368`
- **WRITE** `calendar_db.py:382`
- **READ** `calendar_db.py:274`
- **READ** `calendar_db.py:351`
- **READ** `calendar_db.py:435`
- **READ** `server.py:2713`
- **DELETE** `calendar_db.py:274`


### `calendar_reporting`

- **READ** `chat_v7.py:615`
- **READ** `quick_query.py:298`
- **READ** `quick_query.py:321`
- **READ** `quick_query.py:329`
- **READ** `server.py:6136`
- **READ** `server.py:6797`
- **READ** `server.py:6826`
- **READ** `server.py:6855`
- **READ** `server.py:6863`
- **READ** `tg_morning_report.py:222`


### `calendar_sources`

- **CREATE** `calendar_db.py:35`


### `calendar_sync_state`

- **CREATE** `calendar_db.py:48`
- **WRITE** `calendar_db.py:299`
- **READ** `calendar_db.py:312`


### `chat_v7`

- **READ** `server.py:108`
- **READ** `server.py:7626`
- **READ** `server.py:7649`
- **READ** `server.py:8373`
- **READ** `structured_memory.py:635`


### `chatgpt`

- **READ** `_deprecated/brain_backup.py:6`
- **READ** `_tools/fractal_backtest_v2.py:5`
- **READ** `proactive_suggestions.py:10`


### `circuit_breaker`

- **READ** `_tools/_patch_cron_routing.py:38`
- **READ** `news_engine.py:16`
- **READ** `server.py:5327`


### `claude`

- **READ** `circuit_breaker.py:2`
- **READ** `processing_cursor.py:2`


### `climate_log`

- **CREATE** `home_brain.py:30`
- **WRITE** `home_brain.py:79`
- **READ** `anomaly_engine.py:106`
- **READ** `cost_tracker.py:296`
- **READ** `ha_doctor.py:259`
- **READ** `habit_engine.py:35`
- **READ** `home_brain.py:146`
- **DELETE** `cost_tracker.py:296`
- **DELETE** `home_brain.py:146`


### `coalesced_executor`

- **READ** `_tools/_int1_clean.py:15`
- **READ** `_tools/_int1_radar.py:15`
- **READ** `auto_memory_extractor.py:20`
- **READ** `stock_radar.py:24`


### `collections`

- **READ** `_deprecated/ha_discovery.py:7`
- **READ** `_tools/inventory_field_names.py:33`
- **READ** `_tools/inventory_get_defaults.py:18`
- **READ** `_tools/inventory_human_paths.py:20`
- **READ** `anomaly_engine.py:20`
- **READ** `brain_analytics.py:8`
- **READ** `brain_learning.py:20`
- **READ** `brain_learning.py:962`
- **READ** `brain_learning.py:1144`
- **READ** `calendar_reporting.py:9`
- **READ** `chat_v7.py:6`
- **READ** `dashboard_api.py:12`
- **READ** `entity_map_generator.py:28`
- **READ** `ha_doctor.py:9`
- **READ** `ha_history.py:19`
- **READ** `ha_history.py:339`
- **READ** `habit_engine.py:7`
- **READ** `habit_tracker.py:10`
- **READ** `home_brain.py:7`
- **READ** `server.py:38`
- **READ** `signal_review.py:15`
- **READ** `stock_personality_engine.py:568`
- **READ** `trading_brain.py:520`
- **READ** `world_state.py:20`
- **READ** `world_state_delta.py:11`


### `complete`

- **READ** `indicators.py:425`


### `confidence_census`

- **CREATE** `golden_engine.py:1091`


### `confidence_engine`

- **READ** `chat_v7.py:39`


### `configuration`

- **READ** `_tools/depmap.py:353`


### `confluence_decisions`

- **CREATE** `confluence_engine.py:90`
- **WRITE** `confluence_engine.py:585`


### `confluence_engine`

- **READ** `dashboard_api.py:1432`
- **READ** `server.py:565`


### `confluence_signals`

- **CREATE** `confluence_engine.py:57`
- **WRITE** `_tools/patchers/fix_confluence_bugs.py:32`
- **WRITE** `_tools/patchers/fix_confluence_bugs.py:81`
- **WRITE** `_tools/patchers/fix_confluence_bugs.py:105`
- **WRITE** `confluence_engine.py:277`
- **WRITE** `confluence_engine.py:428`
- **WRITE** `confluence_engine.py:452`
- **READ** `_tools/cleanup_dupes.py:8`
- **READ** `_tools/cleanup_dupes.py:22`
- **READ** `_tools/patchers/fix_confluence_bugs.py:71`
- **READ** `_tools/verify_sunday.py:279`
- **READ** `confluence_engine.py:418`
- **READ** `confluence_engine.py:511`
- **READ** `confluence_engine.py:535`
- **READ** `confluence_engine.py:562`
- **DELETE** `_tools/cleanup_dupes.py:22`


### `contact`

- **WRITE** `relationships_engine.py:128`


### `contacts`

- **CREATE** `relationships_engine.py:28`
- **WRITE** `relationships_engine.py:114`
- **WRITE** `relationships_engine.py:140`
- **READ** `relationships_engine.py:147`
- **READ** `relationships_engine.py:155`
- **READ** `relationships_engine.py:158`
- **READ** `relationships_engine.py:174`
- **READ** `relationships_engine.py:232`
- **READ** `relationships_engine.py:249`
- **READ** `relationships_engine.py:283`


### `context`

- **READ** `chat_v7.py:168`


### `context_cache`

- **CREATE** `context_compactor.py:87`
- **READ** `context_compactor.py:165`
- **READ** `context_compactor.py:189`
- **DELETE** `context_compactor.py:189`


### `context_compactor`

- **READ** `_tools/_patch_phase5.py:61`
- **READ** `tg_session.py:136`


### `context_manager`

- **READ** `_tools/_int4_chat.py:26`
- **READ** `chat_v7.py:11`


### `contextlib`

- **READ** `server.py:36`


### `contract`

- **READ** `gemini_scanner.py:199`
- **READ** `gemini_scanner.py:314`


### `conversations`

- **CREATE** `memory_db.py:11`
- **WRITE** `brain_core.py:789`
- **WRITE** `brain_core.py:899`
- **WRITE** `memory_db.py:69`
- **READ** `auto_memory_extractor.py:2`
- **READ** `memory_db.py:76`
- **READ** `memory_db.py:81`
- **READ** `memory_db.py:128`
- **DELETE** `memory_db.py:81`


### `corrections`

- **CREATE** `corrections_loop.py:73`
- **WRITE** `corrections_loop.py:214`
- **WRITE** `corrections_loop.py:223`
- **WRITE** `corrections_loop.py:292`
- **WRITE** `corrections_loop.py:337`
- **READ** `corrections_loop.py:206`
- **READ** `corrections_loop.py:264`
- **READ** `corrections_loop.py:305`
- **READ** `corrections_loop.py:330`
- **READ** `corrections_loop.py:350`
- **READ** `corrections_loop.py:351`
- **READ** `corrections_loop.py:353`
- **READ** `corrections_loop.py:356`
- **READ** `server.py:6959`
- **READ** `server.py:6966`
- **DELETE** `server.py:6959`
- **DELETE** `server.py:6966`


### `corrections_loop`

- **READ** `chat_v7.py:32`
- **READ** `server.py:6932`
- **READ** `server.py:6953`
- **READ** `server.py:8851`
- **READ** `server.py:9221`
- **READ** `server.py:9230`


### `correlated`

- **READ** `brain_learning.py:1108`


### `cost_log`

- **CREATE** `cost_tracker.py:36`
- **WRITE** `cost_tracker.py:84`
- **WRITE** `cost_tracker.py:114`
- **READ** `cost_tracker.py:144`
- **READ** `cost_tracker.py:162`
- **READ** `cost_tracker.py:178`
- **READ** `cost_tracker.py:197`
- **READ** `cost_tracker.py:215`
- **READ** `cost_tracker.py:229`
- **READ** `cost_tracker.py:255`
- **READ** `cost_tracker.py:259`
- **READ** `cost_tracker.py:263`
- **READ** `cost_tracker.py:286`
- **DELETE** `cost_tracker.py:286`


### `cost_tracker`

- **READ** `_tools/patchers/phase4_fix_cost.py:22`
- **READ** `_tools/patchers/phase4_fix_cost.py:24`
- **READ** `chat_v7.py:73`
- **READ** `dashboard_api.py:1730`
- **READ** `quick_query.py:483`
- **READ** `server.py:5449`
- **READ** `server.py:6112`
- **READ** `server.py:6883`
- **READ** `server.py:9305`
- **READ** `server.py:9361`


### `cron`

- **READ** `_tools/run_witness.py:52`


### `csv`

- **READ** `stock_analyzer.py:145`


### `current`

- **WRITE** `_tools/_patch_dashboard_tier3.py:211`
- **WRITE** `dashboard_api.py:3584`


### `cursor`

- **WRITE** `processing_cursor.py:11`
- **WRITE** `processing_cursor.py:75`
- **WRITE** `processing_cursor.py:88`


### `daily_bars`

- **CREATE** `kse_data_collector.py:45`
- **READ** `_tools/backfill_daily_bars.py:117`
- **READ** `dashboard_api.py:1995`
- **READ** `dashboard_api.py:1996`
- **READ** `kse_data_collector.py:371`
- **READ** `kse_data_collector.py:376`
- **READ** `kse_data_collector.py:381`
- **READ** `kse_data_collector.py:386`
- **READ** `price_source.py:190`
- **READ** `signal_engine.py:222`
- **READ** `signal_engine.py:237`
- **READ** `signal_engine.py:727`
- **READ** `signal_engine.py:923`
- **READ** `signal_engine.py:928`
- **READ** `signal_review.py:151`
- **READ** `signal_review.py:164`
- **READ** `signal_review.py:191`
- **READ** `signal_review.py:475`
- **READ** `stock_analyzer.py:281`
- **READ** `stock_analyzer.py:290`


### `daily_digest`

- **CREATE** `home_brain.py:26`


### `daily_summary`

- **CREATE** `brain_learning.py:59`
- **READ** `brain_learning.py:470`
- **READ** `brain_learning.py:704`
- **READ** `brain_learning.py:732`
- **READ** `brain_learning.py:747`
- **READ** `brain_learning.py:1048`


### `dashboard`

- **WRITE** `_tools/patch_confluence_v2.py:2`


### `dashboard_api`

- **READ** `_tools/patchers/phase2_extract_dashboard.py:2`
- **READ** `_tools/patchers/phase2_extract_dashboard.py:51`
- **READ** `_tools/patchers/phase2_wire_router.py:23`
- **READ** `server.py:2611`
- **READ** `server.py:3170`


### `data`

- **READ** `dashboard_api.py:870`
- **READ** `stock_radar.py:242`


### `data_fetch_runs`

- **CREATE** `kse_data_collector.py:63`
- **WRITE** `_tools/prove_guards.py:143`
- **WRITE** `_tools/prove_guards.py:168`
- **WRITE** `_tools/prove_guards.py:171`
- **WRITE** `_tools/run_witness.py:199`
- **WRITE** `kse_data_collector.py:230`
- **WRITE** `yahoo_gate.py:286`
- **READ** `_tools/prove_guards.py:157`
- **READ** `_tools/prove_guards.py:256`
- **READ** `_tools/prove_guards.py:259`
- **READ** `_tools/quick_check.py:288`
- **READ** `_tools/quick_check.py:343`
- **READ** `_tools/run_witness.py:212`
- **READ** `_tools/run_witness.py:232`
- **READ** `_tools/run_witness.py:267`
- **READ** `_tools/run_witness.py:272`
- **READ** `_tools/run_witness.py:281`
- **READ** `_tools/verify_sunday.py:120`
- **READ** `health_watchdog.py:99`
- **READ** `kse_data_collector.py:366`
- **DELETE** `_tools/prove_guards.py:157`


### `data_integrity`

- **READ** `golden_engine.py:743`


### `dataclasses`

- **READ** `intent_state_machine.py:24`
- **READ** `master_ai_tool.py:19`
- **READ** `parallel_coordinator.py:18`
- **READ** `skill_loader.py:15`
- **READ** `task_manager.py:20`
- **READ** `tips_engine.py:18`


### `datetime`

- **READ** `_deprecated/brain_backup.py:22`
- **READ** `_deprecated/ruijie_integration.py:6`
- **READ** `_deprecated/telegram_bot.py:10`
- **READ** `_tools/_add_ema_active.py:2`
- **READ** `_tools/_add_ema_active.py:17`
- **READ** `_tools/_add_ema_active_v2.py:24`
- **READ** `_tools/_add_ema_active_v3.py:91`
- **READ** `_tools/_int1_clean.py:9`
- **READ** `_tools/_int1_clean.py:10`
- **READ** `_tools/_int1_radar.py:9`
- **READ** `_tools/_int1_radar.py:10`
- **READ** `_tools/_patch_api_tasks.py:3`
- **READ** `_tools/_patch_degraded_mode.py:220`
- **READ** `_tools/_patch_degraded_mode.py:224`
- **READ** `_tools/_patch_layer24.py:162`
- **READ** `_tools/backfill_daily_bars.py:29`
- **READ** `_tools/bar_completeness_probe.py:23`
- **READ** `_tools/check_stable.py:23`
- **READ** `_tools/depmap.py:27`
- **READ** `_tools/fractal_backtest.py:9`
- **READ** `_tools/fractal_backtest_v2.py:17`
- **READ** `_tools/fractal_backtest_v3.py:22`
- **READ** `_tools/fractal_backtest_v4.py:26`
- **READ** `_tools/intraday_refresh.py:36`
- **READ** `_tools/migrate_direction_check.py:60`
- **READ** `_tools/nas_backup.py:26`
- **READ** `_tools/patchers/phase5_daily_summary.py:16`
- **READ** `_tools/patchers/phase5_daily_summary.py:59`
- **READ** `_tools/prove_guards.py:52`
- **READ** `_tools/quick_check.py:113`
- **READ** `_tools/quick_check.py:283`
- **READ** `_tools/quick_check.py:339`
- **READ** `_tools/radar_diag.py:2`
- **READ** `_tools/run_witness.py:16`
- **READ** `_tools/verify_sunday.py:34`
- **READ** `anomaly_engine.py:19`
- **READ** `approval_ux.py:6`
- **READ** `brain_analytics.py:7`
- **READ** `brain_backfill.py:14`
- **READ** `brain_core.py:13`
- **READ** `brain_core.py:919`
- **READ** `brain_learning.py:19`
- **READ** `brain_learning.py:995`
- **READ** `brain_multiuser.py:7`
- **READ** `brain_observability.py:6`
- **READ** `brain_personality.py:8`
- **READ** `brain_proactive.py:12`
- **READ** `calendar_db.py:12`
- **READ** `calendar_engine.py:16`
- **READ** `calendar_engine.py:93`
- **READ** `calendar_reminders.py:9`
- **READ** `calendar_reporting.py:8`
- **READ** `chat_v7.py:568`
- **READ** `chat_v7.py:649`
- **READ** `confluence_engine.py:9`
- **READ** `context_compactor.py:13`
- **READ** `corrections_loop.py:22`
- **READ** `cost_tracker.py:13`
- **READ** `dashboard_api.py:11`
- **READ** `dashboard_api.py:205`
- **READ** `dashboard_api.py:451`
- **READ** `dashboard_api.py:1444`
- **READ** `dashboard_api.py:1566`
- **READ** `dashboard_api.py:1650`
- **READ** `dashboard_api.py:1751`
- **READ** `dashboard_api.py:2033`
- **READ** `dashboard_api.py:2133`
- **READ** `dashboard_api.py:2440`
- **READ** `dashboard_api.py:3101`
- **READ** `dashboard_api.py:3195`
- **READ** `data_integrity.py:13`
- **READ** `db_backup.py:10`
- **READ** `degraded_mode.py:10`
- **READ** `discovery.py:7`
- **READ** `domain_kpis.py:8`
- **READ** `dream_consolidator.py:18`
- **READ** `dropzone_watcher.py:22`
- **READ** `entity_map_generator.py:27`
- **READ** `equity_tracker.py:7`
- **READ** `expenses_engine.py:11`
- **READ** `family_assistant.py:8`
- **READ** `feedback_learner.py:24`
- **READ** `gemini_scanner.py:15`
- **READ** `gemini_scanner.py:509`
- **READ** `golden_engine.py:13`
- **READ** `golden_engine.py:1089`
- **READ** `ha_doctor.py:8`
- **READ** `ha_history.py:18`
- **READ** `habit_engine.py:6`
- **READ** `habit_tracker.py:9`
- **READ** `health_engine.py:14`
- **READ** `health_engine.py:249`
- **READ** `health_watchdog.py:19`
- **READ** `home_brain.py:6`
- **READ** `hooks.py:13`
- **READ** `inbox_engine.py:2`
- **READ** `inbox_engine.py:221`
- **READ** `journal_engine.py:8`
- **READ** `kairos.py:12`
- **READ** `kse_data_collector.py:18`
- **READ** `life_expenses.py:9`
- **READ** `life_health.py:9`
- **READ** `life_stocks.py:10`
- **READ** `life_work.py:6`
- **READ** `memory_db.py:4`
- **READ** `mini_planner.py:7`
- **READ** `news_engine.py:13`
- **READ** `paper_trading.py:7`
- **READ** `plan_engine.py:10`
- **READ** `position_engine.py:17`
- **READ** `price_source.py:39`
- **READ** `price_source.py:201`
- **READ** `price_source.py:214`
- **READ** `priority_engine.py:7`
- **READ** `priority_engine.py:39`
- **READ** `priority_engine.py:85`
- **READ** `priority_engine.py:699`
- **READ** `proactive_engine.py:7`
- **READ** `proactive_suggestions.py:17`
- **READ** `quick_query.py:22`
- **READ** `quick_query.py:359`
- **READ** `relationships_engine.py:16`
- **READ** `risk_engine.py:12`
- **READ** `risk_engine.py:221`
- **READ** `self_check.py:6`
- **READ** `server.py:35`
- **READ** `server.py:2813`
- **READ** `server.py:2980`
- **READ** `server.py:3085`
- **READ** `server.py:3690`
- **READ** `server.py:3864`
- **READ** `server.py:3884`
- **READ** `server.py:6132`
- **READ** `server.py:6831`
- **READ** `server.py:6839`
- **READ** `service_health.py:8`
- **READ** `service_health.py:162`
- **READ** `signal_engine.py:16`
- **READ** `signal_engine.py:317`
- **READ** `signal_engine.py:606`
- **READ** `signal_review.py:13`
- **READ** `smart_tools.py:12`
- **READ** `sr_engine.py:10`
- **READ** `stock_alerts.py:8`
- **READ** `stock_personality_engine.py:18`
- **READ** `stock_radar.py:19`
- **READ** `structured_memory.py:28`
- **READ** `system_guardian.py:7`
- **READ** `task_engine.py:2`
- **READ** `tasks_db.py:9`
- **READ** `tg_alerts.py:9`
- **READ** `tg_email.py:3`
- **READ** `tg_logbook.py:3`
- **READ** `tg_morning_report.py:3`
- **READ** `tg_news.py:8`
- **READ** `tg_news.py:107`
- **READ** `tg_reminders.py:7`
- **READ** `tg_session.py:3`
- **READ** `tg_stocks.py:9`
- **READ** `tg_tasks.py:2`
- **READ** `tools/generate_project_state.py:4`
- **READ** `trading_brain.py:11`
- **READ** `trading_engine.py:14`
- **READ** `trading_engine.py:349`
- **READ** `tradingview_bridge.py:14`
- **READ** `tradingview_bridge.py:799`
- **READ** `tv_data.py:10`
- **READ** `world_state.py:21`
- **READ** `world_state_delta.py:10`
- **READ** `yahoo_gate.py:27`


### `db_backup`

- **READ** `server.py:205`


### `decision_audit`

- **CREATE** `kse_data_collector.py:76`
- **WRITE** `kse_data_collector.py:321`
- **WRITE** `signal_review.py:432`
- **READ** `dashboard_api.py:2803`
- **READ** `dashboard_api.py:2809`
- **READ** `dashboard_api.py:2824`
- **READ** `dashboard_api.py:2839`
- **READ** `dashboard_api.py:2850`
- **READ** `dashboard_api.py:2861`
- **READ** `dashboard_api.py:2908`
- **READ** `dashboard_api.py:2909`
- **READ** `kse_data_collector.py:314`
- **READ** `kse_data_collector.py:416`
- **READ** `signal_review.py:3`
- **READ** `signal_review.py:139`
- **READ** `signal_review.py:606`


### `degraded_mode`

- **READ** `server.py:197`


### `deployments`

- **CREATE** `dropzone_watcher.py:95`
- **WRITE** `dropzone_watcher.py:114`


### `device_patterns`

- **CREATE** `brain_learning.py:48`
- **READ** `brain_learning.py:311`
- **READ** `brain_learning.py:315`
- **READ** `brain_learning.py:335`
- **READ** `brain_learning.py:353`
- **READ** `brain_learning.py:371`
- **READ** `brain_learning.py:439`
- **READ** `brain_learning.py:440`
- **READ** `brain_learning.py:461`
- **READ** `brain_learning.py:462`
- **READ** `brain_learning.py:465`
- **READ** `brain_learning.py:466`
- **READ** `brain_learning.py:467`
- **READ** `brain_learning.py:478`
- **READ** `brain_learning.py:671`
- **READ** `brain_learning.py:691`
- **READ** `brain_learning.py:764`
- **READ** `brain_learning.py:924`
- **READ** `brain_learning.py:1119`


### `discovered`

- **READ** `brain_learning.py:1228`
- **READ** `discovery.py:333`


### `discovery`

- **READ** `discovery.py:152`
- **READ** `discovery.py:302`
- **READ** `scripts/patch_smart.py:10`
- **READ** `scripts/patch_smart.py:11`
- **READ** `server.py:166`


### `disk`

- **READ** `server.py:299`


### `domain_kpis`

- **READ** `server.py:6650`


### `dotenv`

- **READ** `_deprecated/telegram_bot.py:11`
- **READ** `benchmark_runner.py:5`
- **READ** `server.py:41`


### `dream_consolidator`

- **READ** `server.py:2941`
- **READ** `server.py:3275`
- **READ** `server.py:3284`
- **READ** `server.py:5458`
- **READ** `server.py:5467`


### `email`

- **READ** `tg_email.py:5`


### `entity`

- **READ** `_deprecated/brain_backup.py:368`


### `entity_health`

- **READ** `server.py:8495`
- **READ** `server.py:8508`
- **READ** `server.py:8622`


### `entity_id`

- **READ** `_deprecated/ha_discovery.py:60`
- **READ** `discovery.py:131`


### `entity_map`

- **READ** `_deprecated/brain_backup.py:57`
- **READ** `brain_core.py:294`
- **READ** `brain_learning.py:569`
- **READ** `entity_health.py:39`
- **READ** `server.py:7526`
- **READ** `tg_intent_router.py:137`
- **READ** `world_state.py:56`


### `entry`

- **READ** `dashboard_api.py:2269`


### `entry_idx`

- **READ** `_tools/kse_exit_strategy_backtest.py:60`


### `enum`

- **READ** `intent_state_machine.py:23`
- **READ** `master_ai_tool.py:21`
- **READ** `server.py:39`
- **READ** `task_manager.py:19`


### `equity_snapshots`

- **READ** `equity_tracker.py:58`
- **READ** `equity_tracker.py:93`
- **READ** `equity_tracker.py:97`


### `equity_tracker`

- **READ** `dashboard_api.py:2418`


### `errors`

- **READ** `structured_memory.py:310`


### `events`

- **CREATE** `habit_tracker.py:20`
- **CREATE** `server.py:1095`
- **WRITE** `habit_tracker.py:61`
- **WRITE** `server.py:1575`
- **WRITE** `server.py:1576`
- **WRITE** `server.py:1577`
- **WRITE** `server.py:2329`
- **WRITE** `server.py:2355`
- **READ** `habit_tracker.py:78`
- **READ** `habit_tracker.py:150`
- **READ** `habit_tracker.py:152`
- **READ** `health_watchdog.py:161`
- **READ** `server.py:2261`
- **READ** `server.py:2363`
- **READ** `server.py:2370`
- **READ** `server.py:2377`
- **READ** `server.py:2384`
- **READ** `server.py:2385`
- **READ** `server.py:2387`


### `exec_policy`

- **READ** `chat_v7.py:80`
- **READ** `server.py:3549`


### `existing`

- **WRITE** `_tools/patch_dashboard_v9.py:2`
- **READ** `_tools/_patch_health.py:37`
- **READ** `server.py:8096`
- **READ** `service_health.py:3`


### `expense_entries`

- **CREATE** `expenses_engine.py:39`
- **WRITE** `expenses_engine.py:129`
- **READ** `dashboard_api.py:258`
- **READ** `domain_kpis.py:98`
- **READ** `domain_kpis.py:99`
- **READ** `expenses_engine.py:141`
- **READ** `expenses_engine.py:160`
- **READ** `expenses_engine.py:178`
- **READ** `expenses_engine.py:183`
- **READ** `expenses_engine.py:256`
- **DELETE** `expenses_engine.py:160`


### `expenses_engine`

- **READ** `chat_v7.py:412`
- **READ** `chat_v7.py:415`
- **READ** `chat_v7.py:418`
- **READ** `quick_query.py:167`
- **READ** `quick_query.py:174`
- **READ** `quick_query.py:181`
- **READ** `quick_query.py:188`
- **READ** `server.py:519`
- **READ** `tg_morning_report.py:274`


### `failed`

- **WRITE** `_deprecated/ruijie_integration.py:77`


### `family_assistant`

- **READ** `quick_query.py:430`
- **READ** `relationships_engine.py:447`
- **READ** `server.py:6766`


### `fastapi`

- **READ** `dashboard_api.py:13`
- **READ** `dashboard_api.py:14`
- **READ** `dashboard_api.py:3014`
- **READ** `modules/panel.py:3`
- **READ** `modules/panel.py:4`
- **READ** `server.py:42`
- **READ** `server.py:43`
- **READ** `server.py:44`
- **READ** `server.py:45`
- **READ** `server.py:3104`
- **READ** `server.py:3391`
- **READ** `server.py:3465`
- **READ** `server.py:5187`


### `feature_flags`

- **CREATE** `feature_flags.py:65`
- **WRITE** `feature_flags.py:109`
- **WRITE** `feature_flags.py:147`
- **WRITE** `feature_flags.py:154`
- **READ** `_tools/_patch_health.py:13`
- **READ** `_tools/_patch_health.py:14`
- **READ** `_tools/_patch_layer24.py:18`
- **READ** `_tools/_patch_layer24.py:43`
- **READ** `_tools/_patch_phase5.py:48`
- **READ** `_tools/verify_sunday.py:112`
- **READ** `feature_flags.py:84`
- **READ** `feature_flags.py:122`
- **READ** `google_auth_ext.py:61`
- **READ** `kse_data_collector.py:500`
- **READ** `server.py:628`
- **READ** `stock_radar.py:911`
- **READ** `stock_radar.py:926`
- **READ** `tg_session.py:123`


### `feedback`

- **CREATE** `brain_analytics.py:25`
- **WRITE** `brain_analytics.py:64`
- **READ** `brain_analytics.py:128`


### `feedback_learner`

- **READ** `confidence_engine.py:8`
- **READ** `server.py:181`
- **READ** `server.py:6903`
- **READ** `server.py:6922`
- **READ** `server.py:7114`
- **READ** `server.py:8964`
- **READ** `server.py:9273`
- **READ** `server.py:9281`


### `fixed`

- **READ** `_tools/fix_adhan_v5.py:113`


### `fresher`

- **READ** `risk_engine.py:165`


### `gate_state`

- **CREATE** `yahoo_gate.py:86`
- **WRITE** `yahoo_gate.py:117`
- **READ** `yahoo_gate.py:111`


### `gdrive`

- **READ** `dropzone_watcher.py:182`


### `gemini`

- **READ** `gemini_scanner.py:942`


### `gemini_alert_log`

- **CREATE** `gemini_scanner.py:86`
- **WRITE** `gemini_scanner.py:669`
- **READ** `gemini_scanner.py:664`


### `gemini_decisions`

- **CREATE** `gemini_scanner.py:42`
- **WRITE** `gemini_scanner.py:824`
- **READ** `gemini_scanner.py:880`
- **READ** `gemini_scanner.py:935`


### `gemini_scan_runs`

- **CREATE** `gemini_scanner.py:27`
- **WRITE** `gemini_scanner.py:712`
- **WRITE** `gemini_scanner.py:754`
- **WRITE** `gemini_scanner.py:860`
- **READ** `gemini_scanner.py:873`
- **READ** `gemini_scanner.py:920`


### `get_multi_analysis_30m`

- **READ** `_tools/_debug_ema.py:75`


### `gmail`

- **READ** `chat_v7.py:347`
- **READ** `tg_logbook.py:80`


### `gmail_credentials`

- **READ** `google_auth_ext.py:33`


### `golden_engine`

- **READ** `_tools/daily_signal_review.py:44`
- **READ** `gemini_scanner.py:313`
- **READ** `server.py:3618`
- **READ** `server.py:6420`
- **READ** `trading_decision_engine.py:39`


### `google`

- **READ** `calendar_engine.py:346`
- **READ** `chat_v7.py:159`
- **READ** `google_auth_ext.py:89`
- **READ** `google_auth_ext.py:90`
- **READ** `google_auth_ext.py:218`
- **READ** `server.py:3426`
- **READ** `tg_email.py:42`
- **READ** `tg_email.py:43`
- **READ** `tg_logbook.py:28`
- **READ** `tg_logbook.py:29`
- **READ** `tg_stocks.py:35`


### `google_auth_ext`

- **READ** `calendar_engine.py:108`
- **READ** `server.py:3458`
- **READ** `server.py:3479`
- **READ** `server.py:3507`
- **READ** `tg_email.py:33`


### `googleapiclient`

- **READ** `google_auth_ext.py:150`
- **READ** `google_auth_ext.py:171`
- **READ** `server.py:3440`
- **READ** `tg_email.py:44`
- **READ** `tg_logbook.py:30`


### `ha_doctor`

- **READ** `server.py:145`


### `ha_history`

- **READ** `ha_history.py:6`
- **READ** `server.py:146`
- **READ** `tg_intent_router.py:972`


### `habit_engine`

- **READ** `proactive_engine.py:80`
- **READ** `quick_query.py:459`
- **READ** `server.py:6876`


### `health`

- **READ** `_tools/_patch_degraded_mode.py:212`


### `health_alert_state`

- **CREATE** `health_watchdog.py:198`
- **WRITE** `health_watchdog.py:242`
- **READ** `health_watchdog.py:211`
- **READ** `health_watchdog.py:238`


### `health_engine`

- **READ** `chat_v7.py:433`
- **READ** `chat_v7.py:436`
- **READ** `server.py:578`
- **READ** `tg_morning_report.py:301`


### `health_logs`

- **CREATE** `health_engine.py:21`
- **WRITE** `health_engine.py:57`
- **READ** `domain_kpis.py:40`
- **READ** `domain_kpis.py:41`
- **READ** `domain_kpis.py:42`
- **READ** `domain_kpis.py:43`
- **READ** `health_engine.py:76`
- **READ** `health_engine.py:137`
- **READ** `health_engine.py:252`


### `health_status`

- **CREATE** `health_watchdog.py:190`
- **WRITE** `health_watchdog.py:232`


### `here`

- **READ** `_tools/nas_backup.py:64`
- **READ** `brain.py:4`


### `hijridate`

- **READ** `brain_core.py:918`
- **READ** `quick_query.py:621`
- **READ** `quick_query.py:647`
- **READ** `quick_query.py:669`


### `historical`

- **READ** `trading_brain.py:664`


### `home`

- **WRITE** `_tools/patchers/phase5_home_update.py:2`


### `home_brain`

- **READ** `server.py:128`


### `hook_log`

- **CREATE** `hooks.py:54`
- **WRITE** `hooks.py:127`
- **READ** `hooks.py:140`
- **READ** `hooks.py:145`
- **READ** `hooks.py:166`
- **DELETE** `hooks.py:166`


### `hooks`

- **READ** `_tools/_patch_phase6.py:10`
- **READ** `server.py:631`


### `https`

- **READ** `tools/generate_project_state.py:135`


### `inbox_engine`

- **READ** `_tools/patch_email_news.py:16`
- **READ** `chat_v7.py:376`
- **READ** `dashboard_api.py:338`
- **READ** `dashboard_api.py:1778`
- **READ** `proactive_suggestions.py:188`
- **READ** `quick_query.py:408`
- **READ** `server.py:6060`
- **READ** `server.py:6123`
- **READ** `server.py:6137`
- **READ** `server.py:6193`
- **READ** `server.py:6224`
- **READ** `server.py:8861`
- **READ** `server.py:8974`
- **READ** `tg_morning_report.py:255`
- **READ** `tg_morning_report.py:292`


### `indicator`

- **WRITE** `trading_brain.py:510`


### `indicator_performance`

- **CREATE** `trading_brain.py:89`
- **WRITE** `trading_brain.py:459`
- **WRITE** `trading_brain.py:495`
- **READ** `trading_brain.py:479`
- **READ** `trading_brain.py:659`
- **READ** `trading_brain.py:773`
- **READ** `trading_brain.py:856`


### `indicator_regime_stats`

- **CREATE** `trading_brain.py:103`
- **READ** `trading_brain.py:556`
- **READ** `trading_brain.py:900`


### `indicators`

- **READ** `_tools/backfill_daily_bars.py:287`
- **READ** `_tools/bar_completeness_probe.py:27`


### `instead`

- **READ** `scripts/fix_brain_diag.py:2`


### `intent_audit`

- **CREATE** `intent_state_machine.py:119`
- **WRITE** `intent_state_machine.py:150`
- **READ** `_tools/_patch_dashboard_tier3.py:77`
- **READ** `_tools/_patch_dashboard_tier3.py:82`
- **READ** `_tools/_patch_dashboard_tier3.py:87`
- **READ** `_tools/_patch_dashboard_tier3.py:93`
- **READ** `_tools/_patch_dashboard_tier3.py:100`
- **READ** `_tools/_patch_dashboard_tier3.py:109`
- **READ** `_tools/_patch_dashboard_tier3.py:274`
- **READ** `dashboard_api.py:3450`
- **READ** `dashboard_api.py:3455`
- **READ** `dashboard_api.py:3460`
- **READ** `dashboard_api.py:3466`
- **READ** `dashboard_api.py:3473`
- **READ** `dashboard_api.py:3482`
- **READ** `dashboard_api.py:3647`


### `intent_state_machine`

- **READ** `_tools/_int3_intent.py:14`
- **READ** `tg_intent_router.py:17`


### `interaction_feedback`

- **CREATE** `feedback_learner.py:33`
- **WRITE** `feedback_learner.py:101`
- **READ** `feedback_learner.py:125`
- **READ** `feedback_learner.py:129`
- **READ** `feedback_learner.py:133`
- **READ** `feedback_learner.py:137`
- **READ** `feedback_learner.py:172`


### `itertools`

- **READ** `stock_personality_engine.py:19`


### `its`

- **READ** `corrections_loop.py:184`
- **READ** `stock_personality_engine.py:251`


### `journal_engine`

- **READ** `_tools/_fix_tool_reg.py:10`
- **READ** `_tools/_patch_expand_tools_hooks.py:70`
- **READ** `_tools/intraday_refresh.py:60`
- **READ** `dashboard_api.py:714`
- **READ** `dashboard_api.py:726`
- **READ** `dashboard_api.py:1015`
- **READ** `dashboard_api.py:1150`
- **READ** `dashboard_api.py:1169`
- **READ** `dashboard_api.py:1177`
- **READ** `dashboard_api.py:1217`
- **READ** `dashboard_api.py:2508`
- **READ** `dashboard_api.py:3020`
- **READ** `dashboard_api.py:3050`
- **READ** `golden_engine.py:944`
- **READ** `position_engine.py:96`
- **READ** `position_engine.py:282`
- **READ** `position_engine.py:441`
- **READ** `risk_engine.py:60`
- **READ** `server.py:551`
- **READ** `server.py:8188`
- **READ** `server.py:8209`
- **READ** `server.py:8224`
- **READ** `server.py:9008`
- **READ** `signal_engine.py:536`
- **READ** `signal_engine.py:1301`
- **READ** `tg_stocks.py:73`
- **READ** `tg_stocks.py:75`
- **READ** `tg_stocks.py:154`


### `kairos`

- **READ** `_tools/_patch_phase34.py:12`
- **READ** `_tools/_patch_phase6.py:12`
- **READ** `_tools/_patch_phase6.py:13`
- **READ** `server.py:630`


### `kairos_alerts`

- **CREATE** `kairos.py:118`
- **WRITE** `kairos.py:164`
- **WRITE** `kairos.py:173`
- **READ** `kairos.py:150`


### `kairos_log`

- **CREATE** `kairos.py:124`
- **WRITE** `kairos.py:138`
- **READ** `kairos.py:339`
- **READ** `kairos.py:363`
- **DELETE** `kairos.py:339`


### `keyword`

- **READ** `auto_memory_extractor.py:191`


### `knowledge`

- **CREATE** `server.py:4611`
- **CREATE** `server.py:4633`
- **WRITE** `server.py:4634`
- **WRITE** `server.py:4645`
- **WRITE** `server.py:4647`
- **WRITE** `tasks_db.py:207`
- **WRITE** `tasks_db.py:263`
- **READ** `_deprecated/brain_backup.py:73`
- **READ** `brain_core.py:311`
- **READ** `brain_multiuser.py:18`
- **READ** `server.py:4613`
- **READ** `server.py:4616`
- **READ** `server.py:4625`
- **READ** `server.py:4656`
- **READ** `tasks_db.py:217`
- **READ** `tasks_db.py:241`
- **READ** `tasks_db.py:248`
- **READ** `tasks_db.py:269`
- **READ** `tasks_db.py:272`
- **DELETE** `server.py:4656`
- **DELETE** `tasks_db.py:272`


### `kse_data_collector`

- **READ** `_tools/debug_collector.py:6`
- **READ** `dashboard_api.py:3157`
- **READ** `dashboard_api.py:3270`
- **READ** `golden_engine.py:996`
- **READ** `server.py:2649`
- **READ** `server.py:2655`


### `kwse`

- **READ** `signal_engine.py:221`


### `last`

- **READ** `signal_engine.py:717`
- **READ** `world_state_delta.py:16`


### `last_monitored`

- **WRITE** `position_engine.py:161`


### `learned`

- **READ** `server.py:4053`


### `learning_runs`

- **CREATE** `brain_learning.py:71`
- **WRITE** `brain_learning.py:288`
- **READ** `brain_learning.py:438`
- **READ** `brain_learning.py:441`
- **READ** `brain_learning.py:460`
- **READ** `brain_learning.py:473`


### `life_data`

- **WRITE** `life_expenses.py:45`
- **WRITE** `life_health.py:25`
- **WRITE** `life_health.py:46`
- **WRITE** `life_health.py:59`
- **WRITE** `life_work.py:72`
- **WRITE** `life_work.py:89`
- **READ** `life_expenses.py:58`
- **READ** `life_expenses.py:69`
- **READ** `life_health.py:30`
- **READ** `life_health.py:71`
- **READ** `life_health.py:77`
- **READ** `life_health.py:82`
- **READ** `life_work.py:81`
- **READ** `life_work.py:98`


### `life_expenses`

- **READ** `server.py:233`
- **READ** `server.py:6695`
- **READ** `tg_report.py:79`


### `life_health`

- **READ** `server.py:240`
- **READ** `server.py:6707`


### `life_router`

- **READ** `server.py:219`


### `life_stocks`

- **READ** `server.py:226`
- **READ** `tg_morning_report.py:142`
- **READ** `tg_stocks.py:99`


### `life_work`

- **READ** `calendar_reporting.py:43`
- **READ** `chat_v7.py:567`
- **READ** `dashboard_api.py:204`
- **READ** `dashboard_api.py:1750`
- **READ** `proactive_engine.py:92`
- **READ** `quick_query.py:299`
- **READ** `quick_query.py:358`
- **READ** `server.py:247`
- **READ** `server.py:6058`
- **READ** `server.py:6133`
- **READ** `server.py:6675`
- **READ** `server.py:6802`
- **READ** `server.py:6830`
- **READ** `server.py:7970`
- **READ** `server.py:8542`
- **READ** `server.py:8596`
- **READ** `server.py:8798`
- **READ** `tg_report.py:23`


### `live`

- **READ** `_deprecated/ha_discovery.py:138`
- **READ** `_tools/depmap.py:50`
- **READ** `golden_engine.py:515`


### `llm`

- **READ** `server.py:1218`


### `local`

- **WRITE** `calendar_engine.py:346`
- **READ** `calendar_db.py:270`
- **READ** `calendar_engine.py:7`
- **DELETE** `calendar_db.py:270`


### `logging`

- **READ** `server.py:709`


### `master_ai`

- **READ** `_tools/examples/test_patch.py:4`


### `master_ai_tool`

- **READ** `master_ai_tool.py:10`


### `memories`

- **CREATE** `structured_memory.py:70`
- **WRITE** `structured_memory.py:162`
- **WRITE** `structured_memory.py:174`
- **WRITE** `structured_memory.py:231`
- **WRITE** `structured_memory.py:241`
- **WRITE** `structured_memory.py:269`
- **WRITE** `structured_memory.py:278`
- **WRITE** `structured_memory.py:286`
- **READ** `dashboard_api.py:1741`
- **READ** `dashboard_api.py:1742`
- **READ** `structured_memory.py:155`
- **READ** `structured_memory.py:210`
- **READ** `structured_memory.py:222`
- **READ** `structured_memory.py:250`
- **READ** `structured_memory.py:319`
- **READ** `structured_memory.py:330`
- **READ** `structured_memory.py:341`
- **READ** `structured_memory.py:367`
- **READ** `structured_memory.py:379`
- **READ** `structured_memory.py:414`
- **READ** `structured_memory.py:418`
- **READ** `structured_memory.py:423`
- **READ** `structured_memory.py:428`
- **READ** `structured_memory.py:432`
- **DELETE** `structured_memory.py:250`


### `memory`

- **CREATE** `_deprecated/brain_backup.py:547`
- **CREATE** `brain_core.py:338`
- **CREATE** `memory_db.py:10`
- **WRITE** `_deprecated/brain_backup.py:212`
- **WRITE** `_deprecated/brain_backup.py:215`
- **WRITE** `_deprecated/brain_backup.py:567`
- **WRITE** `brain_core.py:762`
- **WRITE** `dream_consolidator.py:112`
- **WRITE** `memory_db.py:23`
- **WRITE** `memory_db.py:26`
- **WRITE** `memory_db.py:45`
- **WRITE** `memory_db.py:55`
- **WRITE** `memory_db.py:62`
- **READ** `_deprecated/brain_backup.py:154`
- **READ** `_deprecated/brain_backup.py:182`
- **READ** `_deprecated/brain_backup.py:225`
- **READ** `_tools/_patch_dashboard_tier3.py:22`
- **READ** `_tools/_patch_dashboard_tier3.py:26`
- **READ** `_tools/_patch_dashboard_tier3.py:33`
- **READ** `_tools/_patch_dashboard_tier3.py:40`
- **READ** `_tools/_patch_dashboard_tier3.py:46`
- **READ** `_tools/_patch_dashboard_tier3.py:134`
- **READ** `_tools/_patch_dashboard_tier3.py:138`
- **READ** `_tools/_patch_dashboard_tier3.py:145`
- **READ** `_tools/_patch_dashboard_tier3.py:155`
- **READ** `_tools/_patch_dashboard_tier3.py:159`
- **READ** `_tools/_patch_dashboard_tier3.py:166`
- **READ** `_tools/_patch_manifest.py:45`
- **READ** `_tools/_patch_manifest.py:53`
- **READ** `_tools/_patch_manifest.py:96`
- **READ** `_tools/_patch_scope.py:26`
- **READ** `_tools/_patch_scope.py:34`
- **READ** `_tools/_patch_scope.py:56`
- **READ** `brain_core.py:419`
- **READ** `brain_core.py:446`
- **READ** `brain_core.py:726`
- **READ** `brain_core.py:824`
- **READ** `brain_core.py:868`
- **READ** `brain_multiuser.py:93`
- **READ** `brain_multiuser.py:98`
- **READ** `brain_multiuser.py:134`
- **READ** `dashboard_api.py:3395`
- **READ** `dashboard_api.py:3399`
- **READ** `dashboard_api.py:3406`
- **READ** `dashboard_api.py:3413`
- **READ** `dashboard_api.py:3419`
- **READ** `dashboard_api.py:3507`
- **READ** `dashboard_api.py:3511`
- **READ** `dashboard_api.py:3518`
- **READ** `dashboard_api.py:3528`
- **READ** `dashboard_api.py:3532`
- **READ** `dashboard_api.py:3539`
- **READ** `dream_consolidator.py:75`
- **READ** `dream_consolidator.py:88`
- **READ** `dream_consolidator.py:106`
- **READ** `dream_consolidator.py:109`
- **READ** `dream_consolidator.py:124`
- **READ** `dream_consolidator.py:133`
- **READ** `dream_consolidator.py:148`
- **READ** `dream_consolidator.py:151`
- **READ** `dream_consolidator.py:156`
- **READ** `dream_consolidator.py:160`
- **READ** `dream_consolidator.py:175`
- **READ** `dream_consolidator.py:178`
- **READ** `dream_consolidator.py:184`
- **READ** `dream_consolidator.py:206`
- **READ** `dream_consolidator.py:208`
- **READ** `dream_consolidator.py:213`
- **READ** `dream_consolidator.py:217`
- **READ** `dream_consolidator.py:224`
- **READ** `memory_db.py:19`
- **READ** `memory_db.py:33`
- **READ** `memory_db.py:124`
- **READ** `memory_db.py:125`
- **READ** `memory_db.py:126`
- **READ** `memory_db.py:184`
- **READ** `scripts/apply_patches.py:35`
- **READ** `server.py:3329`
- **READ** `structured_memory.py:466`
- **DELETE** `dream_consolidator.py:109`
- **DELETE** `dream_consolidator.py:151`
- **DELETE** `dream_consolidator.py:178`


### `memory_archive`

- **CREATE** `dream_consolidator.py:38`
- **WRITE** `dream_consolidator.py:99`
- **WRITE** `dream_consolidator.py:141`
- **WRITE** `dream_consolidator.py:168`
- **READ** `dream_consolidator.py:232`


### `memory_db`

- **READ** `chat_v7.py:542`
- **READ** `chat_v7.py:551`
- **READ** `chat_v7.py:711`
- **READ** `chat_v7.py:801`
- **READ** `chat_v7.py:856`
- **READ** `chat_v7.py:1008`
- **READ** `exec_policy.py:57`
- **READ** `server.py:928`
- **READ** `server.py:5102`


### `memory_recall`

- **READ** `memory_prefetch.py:36`


### `migration_log`

- **CREATE** `structured_memory.py:94`
- **WRITE** `structured_memory.py:503`


### `mined_strategies`

- **READ** `dashboard_api.py:2649`
- **READ** `dashboard_api.py:2662`
- **READ** `dashboard_api.py:2759`
- **READ** `dashboard_api.py:2773`
- **READ** `dashboard_api.py:2786`
- **READ** `dashboard_api.py:2905`
- **READ** `dashboard_api.py:2910`
- **READ** `dashboard_api.py:2951`
- **READ** `dashboard_api.py:2965`
- **READ** `dashboard_api.py:2992`
- **READ** `golden_engine.py:548`
- **READ** `signal_review.py:174`
- **READ** `signal_review.py:178`


### `mini_planner`

- **READ** `chat_v7.py:52`
- **READ** `server.py:9240`


### `module`

- **READ** `service_health.py:119`


### `modules`

- **READ** `server.py:3229`


### `multiple`

- **READ** `life_stocks.py:336`


### `news_digests`

- **CREATE** `news_engine.py:89`
- **WRITE** `news_engine.py:267`
- **READ** `_tools/_patch_news_api.py:49`
- **READ** `_tools/_patch_news_api.py:54`
- **READ** `_tools/_patch_news_api.py:69`
- **READ** `_tools/_patch_news_api.py:84`
- **READ** `_tools/_patch_news_api.py:98`
- **READ** `domain_kpis.py:109`
- **READ** `domain_kpis.py:110`
- **READ** `news_engine.py:291`
- **READ** `news_engine.py:293`
- **READ** `news_engine.py:301`
- **READ** `news_engine.py:404`
- **READ** `news_engine.py:409`
- **READ** `news_engine.py:424`
- **READ** `news_engine.py:441`
- **READ** `news_engine.py:455`
- **DELETE** `_tools/_patch_news_api.py:98`
- **DELETE** `news_engine.py:455`


### `news_engine`

- **READ** `_tools/_patch_health.py:47`
- **READ** `_tools/patch_email_news.py:51`
- **READ** `chat_v7.py:422`
- **READ** `chat_v7.py:425`
- **READ** `dashboard_api.py:1819`
- **READ** `kairos.py:214`
- **READ** `quick_query.py:150`
- **READ** `server.py:532`
- **READ** `server.py:8106`
- **READ** `server.py:8312`
- **READ** `tg_morning_report.py:283`


### `nightly`

- **READ** `tradingview_bridge.py:786`


### `nobody`

- **READ** `health_watchdog.py:134`


### `notes`

- **WRITE** `journal_engine.py:287`


### `occasions`

- **CREATE** `relationships_engine.py:43`
- **WRITE** `relationships_engine.py:205`
- **READ** `domain_kpis.py:89`
- **READ** `relationships_engine.py:219`
- **READ** `relationships_engine.py:231`
- **READ** `relationships_engine.py:248`
- **READ** `relationships_engine.py:282`


### `ohlc`

- **READ** `sr_engine.py:38`
- **READ** `sr_engine.py:99`


### `ohlcv`

- **READ** `_tools/kse_accumulation_distribution.py:6`
- **READ** `indicators.py:1`


### `old`

- **READ** `server.py:9199`
- **READ** `structured_memory.py:18`


### `open`

- **READ** `quick_query.py:837`


### `openai`

- **READ** `chat_v7.py:92`
- **READ** `cost_tracker.py:101`
- **READ** `server.py:47`


### `our`

- **READ** `_tools/intraday_refresh.py:20`


### `paper_trades`

- **WRITE** `paper_trading.py:49`
- **WRITE** `paper_trading.py:91`
- **READ** `equity_tracker.py:31`
- **READ** `equity_tracker.py:34`
- **READ** `equity_tracker.py:35`
- **READ** `equity_tracker.py:36`
- **READ** `equity_tracker.py:42`
- **READ** `equity_tracker.py:108`
- **READ** `paper_trading.py:75`
- **READ** `paper_trading.py:114`
- **READ** `paper_trading.py:145`
- **READ** `paper_trading.py:147`


### `paper_trading`

- **READ** `dashboard_api.py:2382`
- **READ** `dashboard_api.py:2394`
- **READ** `dashboard_api.py:2406`


### `parallel_coordinator`

- **READ** `stock_analyzer.py:213`


### `past`

- **READ** `chat_v7.py:216`


### `pathlib`

- **READ** `_deprecated/brain_backup.py:21`
- **READ** `_deprecated/ruijie_integration.py:7`
- **READ** `_tools/_int1_clean.py:11`
- **READ** `_tools/_int1_radar.py:11`
- **READ** `_tools/add_confluence_nav.py:3`
- **READ** `_tools/add_confluence_page.py:3`
- **READ** `_tools/add_confluence_sensor.py:3`
- **READ** `_tools/add_sensors_v9.py:3`
- **READ** `_tools/build_new_pages.py:6`
- **READ** `_tools/depmap.py:28`
- **READ** `_tools/fix_assistant_page.py:3`
- **READ** `_tools/fix_config_yaml.py:3`
- **READ** `_tools/fractal_backtest.py:10`
- **READ** `_tools/fractal_backtest_v2.py:18`
- **READ** `_tools/fractal_backtest_v3.py:23`
- **READ** `_tools/fractal_backtest_v4.py:27`
- **READ** `_tools/kse_accumulation_distribution.py:10`
- **READ** `_tools/kse_exit_strategy_backtest.py:16`
- **READ** `_tools/kse_indicator_analysis.py:10`
- **READ** `_tools/kse_indicator_analysis_v2.py:7`
- **READ** `_tools/kse_indicator_analysis_v3.py:7`
- **READ** `_tools/kse_reversal_analysis.py:13`
- **READ** `_tools/patch_confluence_v2.py:3`
- **READ** `_tools/patch_dashboard_v9.py:6`
- **READ** `_tools/patch_nav_v9.py:3`
- **READ** `_tools/patch_sr_yaml.py:3`
- **READ** `_tools/test_fractal_quick.py:5`
- **READ** `brain_analytics.py:6`
- **READ** `brain_core.py:12`
- **READ** `brain_multiuser.py:6`
- **READ** `brain_observability.py:7`
- **READ** `brain_proactive.py:13`
- **READ** `corrections_loop.py:23`
- **READ** `cost_tracker.py:12`
- **READ** `db_backup.py:11`
- **READ** `domain_kpis.py:9`
- **READ** `dropzone_watcher.py:23`
- **READ** `entity_health.py:6`
- **READ** `entity_map_generator.py:26`
- **READ** `feedback_learner.py:26`
- **READ** `google_auth_ext.py:14`
- **READ** `inbox_engine.py:3`
- **READ** `mini_planner.py:6`
- **READ** `price_source.py:40`
- **READ** `relationships_engine.py:17`
- **READ** `scripts/patch_chat_prompt.py:9`
- **READ** `scripts/patch_v2.py:4`
- **READ** `stock_radar.py:20`
- **READ** `structured_memory.py:27`
- **READ** `task_engine.py:3`
- **READ** `tg_email.py:4`
- **READ** `tg_logbook.py:4`
- **READ** `tg_morning_report.py:4`
- **READ** `tmp/kse_equipment_backtest.py:11`
- **READ** `tv_data.py:9`
- **READ** `yahoo_gate.py:28`


### `patterns`

- **CREATE** `habit_tracker.py:30`
- **WRITE** `habit_tracker.py:88`
- **WRITE** `habit_tracker.py:128`
- **WRITE** `habit_tracker.py:139`
- **READ** `habit_tracker.py:111`
- **READ** `habit_tracker.py:155`


### `payload`

- **READ** `tradingview_bridge.py:155`
- **READ** `tradingview_bridge.py:644`


### `peak`

- **READ** `_tools/kse_exit_strategy_backtest.py:12`
- **READ** `_tools/kse_exit_strategy_backtest.py:108`
- **READ** `_tools/kse_exit_strategy_backtest.py:200`
- **READ** `_tools/kse_exit_strategy_backtest.py:201`
- **READ** `_tools/kse_exit_strategy_backtest.py:202`
- **READ** `_tools/kse_exit_strategy_backtest.py:203`


### `period`

- **READ** `indicators.py:167`


### `plan_engine`

- **READ** `server.py:189`


### `plans`

- **CREATE** `plan_engine.py:24`
- **WRITE** `plan_engine.py:52`
- **WRITE** `plan_engine.py:78`
- **WRITE** `plan_engine.py:86`
- **WRITE** `plan_engine.py:94`
- **WRITE** `plan_engine.py:121`
- **READ** `plan_engine.py:45`
- **READ** `plan_engine.py:64`
- **READ** `plan_engine.py:72`
- **READ** `plan_engine.py:101`
- **READ** `plan_engine.py:108`
- **READ** `plan_engine.py:160`
- **READ** `plan_engine.py:214`
- **READ** `plan_engine.py:215`
- **READ** `plan_engine.py:216`
- **READ** `plan_engine.py:217`
- **DELETE** `plan_engine.py:101`


### `plugin`

- **READ** `brain_personality.py:59`


### `portfolio`

- **WRITE** `life_stocks.py:107`
- **WRITE** `life_stocks.py:126`
- **WRITE** `life_stocks.py:152`
- **WRITE** `life_stocks.py:155`
- **WRITE** `life_stocks.py:226`
- **WRITE** `life_stocks.py:236`
- **READ** `dashboard_api.py:1917`
- **READ** `life_stocks.py:132`
- **READ** `life_stocks.py:170`
- **READ** `life_stocks.py:204`
- **READ** `life_stocks.py:387`
- **READ** `life_stocks.py:552`


### `position_alerts`

- **CREATE** `position_engine.py:45`
- **WRITE** `position_engine.py:109`
- **WRITE** `position_engine.py:547`
- **READ** `position_engine.py:121`
- **READ** `position_engine.py:536`


### `position_engine`

- **READ** `dashboard_api.py:3302`
- **READ** `dashboard_api.py:3333`
- **READ** `dashboard_api.py:3350`
- **READ** `journal_engine.py:102`
- **READ** `journal_engine.py:217`
- **READ** `journal_engine.py:427`
- **READ** `kse_data_collector.py:570`


### `pragma`

- **READ** `_tools/migrate_direction_check.py:87`


### `price`

- **READ** `signal_engine.py:762`


### `price_source`

- **READ** `_tools/backfill_daily_bars.py:32`
- **READ** `_tools/bar_completeness_probe.py:26`
- **READ** `_tools/intraday_refresh.py:43`
- **READ** `_tools/prove_guards.py:808`
- **READ** `_tools/quick_check.py:284`
- **READ** `_tools/run_witness.py:249`
- **READ** `_tools/run_witness.py:294`
- **READ** `_tools/run_witness.py:302`
- **READ** `dashboard_api.py:806`
- **READ** `dashboard_api.py:882`
- **READ** `dashboard_api.py:926`
- **READ** `dashboard_api.py:959`
- **READ** `dashboard_api.py:2307`
- **READ** `dashboard_api.py:2329`
- **READ** `journal_engine.py:329`
- **READ** `risk_engine.py:171`
- **READ** `stock_analyzer.py:699`


### `priority_engine`

- **READ** `_tools/patchers/phase1_extract_pe.py:2`
- **READ** `_tools/patchers/phase1_extract_pe.py:39`
- **READ** `_tools/patchers/phase1_wire_inbox_cache.py:13`
- **READ** `_tools/patchers/phase1_wire_inbox_cache.py:19`
- **READ** `dashboard_api.py:16`
- **READ** `server.py:9395`


### `proactive_alerts`

- **CREATE** `brain_proactive.py:40`
- **WRITE** `brain_proactive.py:67`
- **READ** `brain_proactive.py:83`
- **READ** `brain_proactive.py:97`
- **READ** `brain_proactive.py:110`
- **READ** `brain_proactive.py:306`
- **READ** `brain_proactive.py:328`
- **READ** `brain_proactive.py:343`
- **READ** `brain_proactive.py:345`
- **READ** `brain_proactive.py:349`
- **READ** `brain_proactive.py:353`


### `proactive_suggestions`

- **READ** `server.py:456`


### `processing_cursor`

- **READ** `_tools/_int1_clean.py:20`
- **READ** `_tools/_int1_radar.py:20`
- **READ** `auto_memory_extractor.py:19`
- **READ** `news_engine.py:22`
- **READ** `stock_radar.py:29`


### `processing_cursors`

- **CREATE** `processing_cursor.py:32`
- **WRITE** `processing_cursor.py:79`
- **READ** `processing_cursor.py:58`


### `profile`

- **READ** `stock_personality_engine.py:451`


### `progress`

- **WRITE** `_tools/_patch_dashboard_tier3.py:255`
- **WRITE** `dashboard_api.py:3628`


### `project`

- **READ** `_tools/depmap.py:63`


### `pydantic`

- **READ** `server.py:46`


### `python`

- **READ** `_tools/depmap.py:538`
- **READ** `_tools/depmap.py:610`
- **READ** `_tools/patchers/apply_text_patch.py:8`


### `queue`

- **READ** `_deprecated/brain_backup.py:462`


### `quick_check_runs`

- **CREATE** `_tools/quick_check.py:117`
- **WRITE** `_tools/quick_check.py:135`
- **READ** `_tools/prove_guards.py:632`
- **READ** `_tools/quick_check.py:145`
- **DELETE** `_tools/quick_check.py:145`


### `quick_query`

- **READ** `server.py:114`
- **READ** `server.py:5508`
- **READ** `server.py:5524`
- **READ** `server.py:5534`
- **READ** `server.py:5544`
- **READ** `tg_report.py:31`
- **READ** `tg_report.py:41`


### `radar`

- **READ** `signal_engine.py:359`
- **READ** `trading_brain.py:357`
- **READ** `tradingview_bridge.py:468`
- **READ** `tradingview_bridge.py:500`


### `radar_config`

- **READ** `_tools/check_radar.py:18`


### `radar_events`

- **READ** `_tools/check_radar.py:6`
- **READ** `_tools/check_radar.py:9`
- **READ** `_tools/check_radar.py:12`


### `raw`

- **READ** `golden_engine.py:199`


### `recent`

- **READ** `stock_radar.py:1198`


### `relationship_notes`

- **CREATE** `relationships_engine.py:60`
- **WRITE** `relationships_engine.py:300`
- **READ** `relationships_engine.py:310`


### `relationships_engine`

- **READ** `chat_v7.py:389`
- **READ** `chat_v7.py:394`
- **READ** `chat_v7.py:408`
- **READ** `quick_query.py:272`
- **READ** `quick_query.py:289`
- **READ** `server.py:505`
- **READ** `tg_morning_report.py:265`


### `request_log`

- **CREATE** `brain_analytics.py:36`
- **WRITE** `brain_analytics.py:84`
- **READ** `brain_analytics.py:111`
- **READ** `brain_analytics.py:141`
- **READ** `brain_analytics.py:151`
- **READ** `brain_analytics.py:158`


### `response`

- **READ** `_tools/smoke_test.py:77`


### `rest`

- **READ** `tg_intent_router.py:779`


### `risk`

- **WRITE** `dashboard_api.py:3128`


### `risk_config`

- **CREATE** `dashboard_api.py:3133`
- **READ** `risk_engine.py:295`


### `risk_engine`

- **READ** `_tools/intraday_refresh.py:74`
- **READ** `dashboard_api.py:2077`
- **READ** `dashboard_api.py:2428`
- **READ** `dashboard_api.py:3121`
- **READ** `equity_tracker.py:22`
- **READ** `equity_tracker.py:84`
- **READ** `golden_engine.py:943`
- **READ** `paper_trading.py:36`
- **READ** `paper_trading.py:164`
- **READ** `signal_engine.py:125`
- **READ** `signal_engine.py:187`


### `rpi`

- **READ** `_tools/debug_collector.py:2`


### `run_witness`

- **READ** `kse_data_collector.py:448`
- **READ** `signal_review.py:644`
- **READ** `signal_review.py:693`


### `saved`

- **READ** `tradingview_bridge.py:374`


### `scan_opportunities`

- **READ** `risk_engine.py:59`


### `scanner_universe`

- **READ** `gemini_scanner.py:13`


### `schema_migrations`

- **WRITE** `server.py:1601`
- **READ** `server.py:1713`


### `scratch`

- **READ** `_tools/build_new_pages.py:2`
- **READ** `_tools/fix_adhan_script.py:35`


### `sector_map`

- **READ** `golden_engine.py:952`
- **READ** `risk_engine.py:62`


### `self_check`

- **READ** `chat_v7.py:25`


### `server`

- **READ** `_deprecated/brain_backup.py:3`
- **READ** `dashboard_api.py:3`
- **READ** `gemini_scanner.py:180`
- **READ** `kse_data_collector.py:512`
- **READ** `memory_recall.py:47`
- **READ** `priority_engine.py:3`
- **READ** `service_health.py:99`
- **READ** `tg_alerts.py:209`
- **READ** `tools/generate_project_state.py:2`


### `service_health`

- **READ** `_tools/_fix_dashboard_helper.py:13`
- **READ** `_tools/_fix_dashboard_helper.py:32`
- **READ** `_tools/_patch_degraded_mode.py:181`
- **READ** `_tools/_patch_degraded_mode.py:263`
- **READ** `_tools/_patch_degraded_mode.py:293`
- **READ** `_tools/_patch_health.py:15`
- **READ** `_tools/_patch_layer24.py:68`
- **READ** `_tools/_patch_layer24.py:94`
- **READ** `_tools/_patch_layer24.py:126`
- **READ** `_tools/_patch_phase34.py:14`
- **READ** `_tools/_patch_phase34.py:15`
- **READ** `server.py:629`
- **READ** `server.py:641`
- **READ** `stock_radar.py:950`
- **READ** `stock_radar.py:989`
- **READ** `stock_radar.py:1017`
- **READ** `stock_radar.py:1578`


### `session_log`

- **WRITE** `tasks_db.py:285`
- **READ** `tasks_db.py:295`
- **READ** `tasks_db.py:302`


### `session_memory`

- **READ** `_tools/_int5_tg.py:19`
- **READ** `server.py:7545`


### `session_summaries`

- **CREATE** `session_memory.py:32`
- **WRITE** `session_memory.py:91`


### `sessions`

- **CREATE** `server.py:4564`
- **CREATE** `server.py:4576`
- **CREATE** `server.py:4586`
- **WRITE** `server.py:4565`
- **READ** `server.py:4577`
- **READ** `server.py:4587`


### `signal`

- **READ** `dashboard_api.py:2390`


### `signal_engine`

- **READ** `dashboard_api.py:1088`
- **READ** `dashboard_api.py:1974`
- **READ** `dashboard_api.py:1985`
- **READ** `dashboard_api.py:2122`
- **READ** `dashboard_api.py:2134`
- **READ** `dashboard_api.py:2192`
- **READ** `dashboard_api.py:2247`
- **READ** `dashboard_api.py:2441`
- **READ** `server.py:2919`
- **READ** `server.py:3621`
- **READ** `server.py:3628`
- **READ** `server.py:6424`
- **READ** `server.py:6431`
- **READ** `trading_brain.py:161`
- **READ** `trading_brain.py:164`
- **READ** `trading_brain.py:648`


### `signal_outcomes`

- **READ** `dashboard_api.py:2679`
- **READ** `dashboard_api.py:2704`
- **READ** `dashboard_api.py:2717`
- **READ** `dashboard_api.py:2734`
- **READ** `dashboard_api.py:2883`
- **READ** `dashboard_api.py:2895`
- **READ** `dashboard_api.py:2906`
- **READ** `dashboard_api.py:2907`


### `signal_review`

- **READ** `_tools/daily_signal_review.py:29`
- **READ** `server.py:254`
- **READ** `server.py:3680`
- **READ** `server.py:6469`


### `signal_reviews`

- **CREATE** `signal_review.py:50`
- **READ** `signal_review.py:472`
- **READ** `signal_review.py:484`
- **READ** `signal_review.py:488`
- **READ** `signal_review.py:493`
- **READ** `signal_review.py:497`
- **READ** `signal_review.py:519`
- **READ** `signal_review.py:531`
- **READ** `signal_review.py:542`


### `signal_snapshots`

- **CREATE** `trading_brain.py:43`
- **WRITE** `brain_backfill.py:257`
- **WRITE** `brain_backfill.py:395`
- **WRITE** `trading_brain.py:210`
- **WRITE** `trading_brain.py:333`
- **READ** `_tools/verify_sunday.py:223`
- **READ** `_tools/verify_sunday.py:250`
- **READ** `brain_backfill.py:237`
- **READ** `dashboard_api.py:2635`
- **READ** `stock_personality_engine.py:558`
- **READ** `trading_brain.py:191`
- **READ** `trading_brain.py:285`
- **READ** `trading_brain.py:417`
- **READ** `trading_brain.py:513`
- **READ** `trading_brain.py:678`
- **READ** `trading_brain.py:688`
- **READ** `trading_brain.py:754`
- **READ** `trading_brain.py:851`
- **READ** `trading_brain.py:852`
- **READ** `trading_brain.py:853`
- **READ** `trading_brain.py:854`
- **READ** `trading_brain.py:859`
- **READ** `trading_brain.py:934`


### `skill_loader`

- **READ** `_tools/full_audit.py:203`
- **READ** `dashboard_api.py:3675`


### `skills`

- **READ** `dashboard_api.py:3673`
- **READ** `skill_loader.py:4`


### `smart_router`

- **READ** `server.py:99`


### `smart_tools`

- **READ** `chat_v7.py:59`


### `sqlite_master`

- **READ** `_tools/check_radar2.py:8`
- **READ** `_tools/db_sanity.py:89`
- **READ** `_tools/full_audit.py:168`
- **READ** `_tools/full_audit.py:188`
- **READ** `_tools/prove_guards.py:565`
- **READ** `_tools/prove_guards.py:640`
- **READ** `server.py:1493`
- **READ** `server.py:5058`
- **READ** `structured_memory.py:460`


### `sr_engine`

- **READ** `dashboard_api.py:1064`
- **READ** `stock_radar.py:1571`


### `stale`

- **READ** `data_integrity.py:6`


### `starlette`

- **READ** `server.py:3181`
- **READ** `server.py:5139`


### `start`

- **READ** `_tools/inventory_human_paths.py:66`


### `state_changes`

- **CREATE** `home_brain.py:20`
- **WRITE** `home_brain.py:64`
- **READ** `anomaly_engine.py:68`
- **READ** `anomaly_engine.py:79`
- **READ** `anomaly_engine.py:132`
- **READ** `anomaly_engine.py:137`
- **READ** `anomaly_engine.py:168`
- **READ** `anomaly_engine.py:174`
- **READ** `anomaly_engine.py:202`
- **READ** `anomaly_engine.py:205`
- **READ** `cost_tracker.py:295`
- **READ** `ha_doctor.py:126`
- **READ** `ha_doctor.py:152`
- **READ** `ha_doctor.py:156`
- **READ** `ha_doctor.py:159`
- **READ** `habit_engine.py:21`
- **READ** `habit_engine.py:47`
- **READ** `habit_engine.py:59`
- **READ** `habit_engine.py:72`
- **READ** `home_brain.py:89`
- **READ** `home_brain.py:90`
- **READ** `home_brain.py:91`
- **READ** `home_brain.py:92`
- **READ** `home_brain.py:101`
- **READ** `home_brain.py:129`
- **READ** `home_brain.py:130`
- **READ** `home_brain.py:131`
- **READ** `home_brain.py:143`
- **READ** `world_state_delta.py:133`
- **READ** `world_state_delta.py:152`
- **READ** `world_state_delta.py:171`
- **READ** `world_state_delta.py:189`
- **DELETE** `cost_tracker.py:295`
- **DELETE** `home_brain.py:143`


### `stock_alerts`

- **READ** `server.py:4686`
- **READ** `server.py:4695`


### `stock_analysis_cache`

- **CREATE** `stock_analyzer.py:55`
- **READ** `stock_analyzer.py:102`
- **READ** `stock_analyzer.py:123`
- **READ** `stock_analyzer.py:126`


### `stock_analyzer`

- **READ** `_tools/_patch_api_analyze.py:28`
- **READ** `dashboard_api.py:2022`
- **READ** `gemini_scanner.py:462`
- **READ** `server.py:2688`
- **READ** `server.py:8128`


### `stock_personality_engine`

- **READ** `server.py:3656`
- **READ** `server.py:3662`


### `stock_profiles`

- **CREATE** `stock_personality_engine.py:32`
- **WRITE** `sr_engine.py:152`
- **WRITE** `sr_engine.py:164`
- **READ** `golden_engine.py:724`
- **READ** `stock_personality_engine.py:594`
- **READ** `stock_personality_engine.py:680`
- **READ** `stock_personality_engine.py:710`
- **DELETE** `stock_personality_engine.py:594`


### `stock_radar`

- **READ** `_tools/_patch_expand_tools_hooks.py:24`
- **READ** `_tools/_patch_expand_tools_hooks.py:54`
- **READ** `_tools/_patch_phase6.py:61`
- **READ** `_tools/fractal_backtest.py:24`
- **READ** `_tools/fractal_backtest_v2.py:34`
- **READ** `_tools/fractal_backtest_v4.py:42`
- **READ** `_tools/radar_diag.py:18`
- **READ** `_tools/run_daily_refresh.py:64`
- **READ** `_tools/run_refresh_check.py:5`
- **READ** `_tools/test_radar.py:9`
- **READ** `_tools/test_radar_task.py:13`
- **READ** `_tools/test_radar_venv.py:42`
- **READ** `_tools/trigger_refresh.py:7`
- **READ** `_tools/verify_sunday.py:135`
- **READ** `_tools/verify_sunday.py:146`
- **READ** `brain_backfill.py:291`
- **READ** `brain_backfill.py:426`
- **READ** `dashboard_api.py:213`
- **READ** `dashboard_api.py:457`
- **READ** `dashboard_api.py:1341`
- **READ** `dashboard_api.py:1933`
- **READ** `dashboard_api.py:2568`
- **READ** `dashboard_api.py:3373`
- **READ** `gemini_scanner.py:194`
- **READ** `kse_data_collector.py:115`
- **READ** `kse_data_collector.py:274`
- **READ** `priority_engine.py:83`
- **READ** `server.py:493`
- **READ** `server.py:3043`
- **READ** `server.py:3146`
- **READ** `server.py:3891`
- **READ** `signal_engine.py:1349`
- **READ** `signal_engine.py:1412`
- **READ** `signal_engine.py:1602`
- **READ** `trading_brain.py:360`
- **READ** `tradingview_bridge.py:398`


### `stock_radar_daily`

- **CREATE** `stock_radar.py:116`
- **WRITE** `_tools/backfill_daily_bars.py:351`
- **WRITE** `_tools/backfill_daily_bars.py:366`
- **WRITE** `_tools/intraday_refresh.py:176`
- **WRITE** `_tools/prove_guards.py:380`
- **WRITE** `_tools/prove_guards.py:382`
- **WRITE** `_tools/prove_guards.py:384`
- **READ** `_tools/_check_db.py:6`
- **READ** `_tools/_check_db.py:12`
- **READ** `_tools/backfill_daily_bars.py:334`
- **READ** `_tools/backfill_daily_bars.py:342`
- **READ** `_tools/bar_completeness_probe.py:49`
- **READ** `_tools/check_daily.py:4`
- **READ** `_tools/check_radar.py:24`
- **READ** `_tools/check_radar.py:27`
- **READ** `_tools/daily_signal_review.py:42`
- **READ** `_tools/fractal_backtest.py:36`
- **READ** `_tools/fractal_backtest_v2.py:41`
- **READ** `_tools/fractal_backtest_v4.py:49`
- **READ** `_tools/intraday_refresh.py:77`
- **READ** `_tools/patchers/fix_tv_alert_price.py:2`
- **READ** `_tools/patchers/fix_tv_alert_price.py:18`
- **READ** `_tools/patchers/fix_tv_alert_price.py:25`
- **READ** `_tools/patchers/phase5_daily_summary.py:107`
- **READ** `_tools/prove_guards.py:376`
- **READ** `_tools/run_daily_refresh.py:82`
- **READ** `_tools/run_refresh_check.py:13`
- **READ** `_tools/verify_sunday.py:153`
- **READ** `_tools/verify_sunday.py:203`
- **READ** `_tools/verify_sunday.py:206`
- **READ** `confluence_engine.py:282`
- **READ** `dashboard_api.py:808`
- **READ** `dashboard_api.py:937`
- **READ** `dashboard_api.py:2310`
- **READ** `dashboard_api.py:3174`
- **READ** `dashboard_api.py:3185`
- **READ** `dashboard_api.py:3191`
- **READ** `dashboard_api.py:3366`
- **READ** `data_integrity.py:139`
- **READ** `data_integrity.py:143`
- **READ** `data_integrity.py:253`
- **READ** `equity_tracker.py:43`
- **READ** `health_watchdog.py:170`
- **READ** `kse_data_collector.py:123`
- **READ** `kse_data_collector.py:394`
- **READ** `paper_trading.py:121`
- **READ** `price_source.py:413`
- **READ** `risk_engine.py:180`
- **READ** `server.py:2861`
- **READ** `server.py:3644`
- **READ** `server.py:6445`
- **READ** `service_health.py:156`
- **READ** `signal_engine.py:192`
- **READ** `signal_engine.py:249`
- **READ** `signal_engine.py:281`
- **READ** `signal_engine.py:586`
- **READ** `signal_engine.py:601`
- **READ** `signal_engine.py:745`
- **READ** `sr_engine.py:138`
- **READ** `sr_engine.py:160`
- **READ** `stock_radar.py:1596`
- **READ** `stock_radar.py:1626`
- **READ** `tg_stocks.py:112`
- **READ** `trading_brain.py:363`
- **READ** `tradingview_bridge.py:288`
- **DELETE** `_tools/prove_guards.py:376`


### `stock_radar_events`

- **CREATE** `stock_radar.py:100`
- **WRITE** `_tools/patchers/fix7_trading_issues.py:47`
- **WRITE** `stock_radar.py:572`
- **READ** `_tools/_add_ema_active.py:35`
- **READ** `_tools/_add_ema_active.py:38`
- **READ** `_tools/_add_ema_active_v2.py:41`
- **READ** `_tools/_add_ema_active_v2.py:44`
- **READ** `_tools/_add_ema_active_v3.py:45`
- **READ** `_tools/_add_ema_active_v3.py:48`
- **READ** `_tools/_verify_scalper.py:6`
- **READ** `_tools/_verify_scalper.py:7`
- **READ** `_tools/_verify_scalper.py:8`
- **READ** `_tools/_verify_scalper.py:12`
- **READ** `_tools/_verify_scalper.py:16`
- **READ** `_tools/_verify_scalper.py:23`
- **READ** `_tools/_verify_scalper.py:38`
- **READ** `_tools/patchers/fix7_trading_issues.py:39`
- **READ** `_tools/patchers/phase5_daily_summary.py:76`
- **READ** `_tools/prove_guards.py:375`
- **READ** `_tools/radar_diag.py:28`
- **READ** `dashboard_api.py:1188`
- **READ** `dashboard_api.py:1521`
- **READ** `dashboard_api.py:1547`
- **READ** `dashboard_api.py:1549`
- **READ** `dashboard_api.py:1552`
- **READ** `dashboard_api.py:1554`
- **READ** `dashboard_api.py:1569`
- **READ** `dashboard_api.py:1572`
- **READ** `dashboard_api.py:1576`
- **READ** `journal_engine.py:596`
- **READ** `journal_engine.py:610`
- **READ** `server.py:2830`
- **READ** `server.py:3710`
- **READ** `server.py:3818`
- **READ** `server.py:3821`
- **READ** `stock_radar.py:290`
- **READ** `stock_radar.py:1141`
- **READ** `stock_radar.py:1145`
- **READ** `stock_radar.py:1177`
- **READ** `stock_radar.py:1178`
- **READ** `stock_radar.py:1207`
- **DELETE** `_tools/prove_guards.py:375`


### `stock_radar_state`

- **CREATE** `stock_radar.py:88`
- **READ** `_tools/_add_ema_active.py:26`
- **READ** `_tools/_add_ema_active_v2.py:33`
- **READ** `_tools/_add_ema_active_v3.py:37`
- **READ** `_tools/_check_state.py:8`
- **READ** `_tools/_check_state.py:23`
- **READ** `_tools/_check_state.py:24`
- **READ** `_tools/_check_state.py:25`
- **READ** `_tools/_verify_scalper.py:33`
- **READ** `_tools/prove_guards.py:378`
- **READ** `_tools/radar_diag.py:32`
- **READ** `server.py:3762`
- **READ** `server.py:3810`
- **READ** `stock_radar.py:533`
- **READ** `stock_radar.py:738`
- **DELETE** `_tools/prove_guards.py:378`


### `stock_radar_watchlist`

- **CREATE** `stock_radar.py:77`
- **WRITE** `stock_radar.py:261`
- **READ** `_tools/prove_guards.py:377`
- **READ** `stock_radar.py:228`
- **READ** `stock_radar.py:255`
- **READ** `stock_radar.py:271`
- **READ** `stock_radar.py:281`
- **READ** `tradingview_bridge.py:474`
- **DELETE** `_tools/prove_guards.py:377`
- **DELETE** `stock_radar.py:228`


### `stop`

- **WRITE** `journal_engine.py:296`


### `sub`

- **READ** `brain.py:3`


### `suggestions`

- **CREATE** `habit_tracker.py:43`


### `swing`

- **READ** `sr_engine.py:3`


### `symbol_notes`

- **CREATE** `stock_personality_engine.py:107`
- **READ** `stock_personality_engine.py:596`
- **READ** `stock_personality_engine.py:693`
- **DELETE** `stock_personality_engine.py:596`


### `symbol_patterns`

- **CREATE** `stock_personality_engine.py:85`
- **READ** `golden_engine.py:730`
- **READ** `stock_personality_engine.py:595`
- **READ** `stock_personality_engine.py:687`
- **DELETE** `stock_personality_engine.py:595`


### `sync`

- **WRITE** `calendar_db.py:284`
- **READ** `hooks.py:109`


### `system_guardian`

- **READ** `quick_query.py:438`
- **READ** `server.py:6773`
- **READ** `tg_alerts.py:223`


### `system_settings`

- **CREATE** `server.py:1115`
- **WRITE** `server.py:1594`
- **READ** `dashboard_api.py:174`
- **READ** `server.py:1121`
- **READ** `server.py:1618`
- **READ** `server.py:1699`
- **READ** `server.py:2302`


### `target`

- **WRITE** `life_stocks.py:200`


### `task`

- **WRITE** `chat_v7.py:164`


### `task_categories`

- **CREATE** `task_engine.py:14`


### `task_engine`

- **READ** `inbox_engine.py:183`
- **READ** `inbox_engine.py:210`
- **READ** `proactive_suggestions.py:174`
- **READ** `quick_query.py:300`
- **READ** `quick_query.py:337`
- **READ** `quick_query.py:344`
- **READ** `quick_query.py:351`
- **READ** `quick_query.py:375`
- **READ** `quick_query.py:394`
- **READ** `server.py:5440`
- **READ** `server.py:6059`
- **READ** `server.py:6134`
- **READ** `server.py:6192`
- **READ** `server.py:6809`
- **READ** `server.py:6838`
- **READ** `server.py:8860`
- **READ** `server.py:8973`
- **READ** `tg_morning_report.py:246`
- **READ** `tg_tasks.py:3`


### `task_log`

- **CREATE** `tasks_db.py:33`
- **WRITE** `tasks_db.py:56`
- **WRITE** `tasks_db.py:130`
- **WRITE** `tasks_db.py:147`
- **READ** `tasks_db.py:90`
- **READ** `tasks_db.py:158`
- **DELETE** `tasks_db.py:158`


### `task_manager`

- **READ** `_tools/_int7_tasks.py:22`
- **READ** `_tools/_int7_tasks.py:56`
- **READ** `_tools/_patch_api_tasks.py:23`
- **READ** `server.py:8236`
- **READ** `server.py:8325`
- **READ** `server.py:8347`


### `tasks`

- **CREATE** `server.py:1048`
- **CREATE** `task_engine.py:21`
- **WRITE** `server.py:2511`
- **WRITE** `server.py:2542`
- **WRITE** `task_engine.py:57`
- **WRITE** `task_engine.py:85`
- **READ** `dashboard_api.py:240`
- **READ** `dashboard_api.py:241`
- **READ** `dashboard_api.py:1661`
- **READ** `dashboard_api.py:1663`
- **READ** `domain_kpis.py:80`
- **READ** `domain_kpis.py:81`
- **READ** `domain_kpis.py:82`
- **READ** `memory_db.py:5`
- **READ** `priority_engine.py:46`
- **READ** `server.py:2522`
- **READ** `server.py:2578`
- **READ** `server.py:2582`
- **READ** `task_engine.py:65`
- **READ** `task_engine.py:93`
- **READ** `task_engine.py:109`
- **READ** `task_engine.py:119`
- **READ** `task_engine.py:127`
- **READ** `task_engine.py:129`
- **READ** `task_engine.py:132`
- **READ** `task_engine.py:134`
- **READ** `tasks_db.py:178`
- **DELETE** `task_engine.py:93`


### `tasks_db`

- **READ** `memory_db.py:105`


### `telegram`

- **READ** `_deprecated/telegram_bot.py:12`
- **READ** `_deprecated/telegram_bot.py:13`
- **READ** `auto_memory_extractor.py:57`


### `telegram_queue`

- **CREATE** `kairos.py:41`
- **WRITE** `kairos.py:55`
- **WRITE** `kairos.py:76`
- **READ** `kairos.py:63`
- **READ** `kairos.py:68`
- **READ** `kairos.py:85`
- **DELETE** `kairos.py:85`


### `telegram_sends`

- **CREATE** `_tools/run_witness.py:102`
- **WRITE** `_tools/run_witness.py:114`
- **READ** `_tools/prove_guards.py:589`
- **READ** `_tools/run_witness.py:122`
- **DELETE** `_tools/run_witness.py:122`


### `template`

- **READ** `_tools/patch_recommendations.py:89`


### `text`

- **READ** `tg_intent_router.py:943`
- **READ** `tg_news.py:25`
- **READ** `tg_session.py:203`


### `tg_alerts`

- **READ** `_tools/patchers/v12_patch_stocks_import.py:2`
- **READ** `server.py:455`


### `tg_email`

- **READ** `inbox_engine.py:48`
- **READ** `priority_engine.py:67`
- **READ** `server.py:152`
- **READ** `tg_intent_router.py:307`
- **READ** `tg_morning_report.py:237`


### `tg_home`

- **READ** `server.py:66`


### `tg_intent_router`

- **READ** `server.py:82`


### `tg_morning_report`

- **READ** `server.py:212`


### `tg_news`

- **READ** `server.py:470`


### `tg_ops`

- **READ** `server.py:59`


### `tg_reminders`

- **READ** `server.py:463`


### `tg_report`

- **READ** `server.py:121`


### `tg_session`

- **READ** `_tools/_patch_phase5.py:93`
- **READ** `_tools/_patch_phase5.py:94`
- **READ** `server.py:73`
- **READ** `server.py:7138`
- **READ** `server.py:7152`


### `tg_session_resolver`

- **READ** `server.py:74`


### `tg_sessions`

- **CREATE** `tg_session.py:13`
- **WRITE** `tg_session.py:74`
- **WRITE** `tg_session.py:98`
- **READ** `tg_session.py:49`
- **READ** `tg_session.py:151`
- **DELETE** `tg_session.py:151`


### `tg_stocks`

- **READ** `_tools/patchers/v12_patch_imports.py:11`
- **READ** `_tools/patchers/v12_patch_imports.py:28`
- **READ** `_tools/patchers/v12_patch_stocks_import.py:2`
- **READ** `_tools/patchers/v12_patch_stocks_import.py:9`
- **READ** `_tools/patchers/v12_patch_stocks_import.py:10`
- **READ** `server.py:487`


### `tg_suggestions`

- **READ** `server.py:173`


### `tg_tasks`

- **READ** `_tools/patchers/v12_patch_imports.py:10`
- **READ** `_tools/patchers/v12_patch_imports.py:20`
- **READ** `chat_v7.py:379`
- **READ** `chat_v7.py:382`
- **READ** `chat_v7.py:385`
- **READ** `quick_query.py:395`
- **READ** `server.py:479`
- **READ** `server.py:7033`


### `the`

- **WRITE** `_tools/backfill_daily_bars.py:8`
- **WRITE** `_tools/quick_check.py:373`
- **WRITE** `_tools/quick_check.py:386`
- **WRITE** `position_engine.py:170`
- **READ** `_tools/_patch_manifest.py:86`
- **READ** `_tools/backfill_daily_bars.py:10`
- **READ** `_tools/backfill_daily_bars.py:173`
- **READ** `_tools/bar_completeness_probe.py:31`
- **READ** `_tools/bar_completeness_probe.py:36`
- **READ** `_tools/daily_signal_review.py:35`
- **READ** `_tools/intraday_refresh.py:20`
- **READ** `_tools/inventory_human_paths.py:7`
- **READ** `_tools/prove_guards.py:549`
- **READ** `_tools/run_witness.py:79`
- **READ** `_tools/test_exact_templates.py:2`
- **READ** `_tools/verify_sunday.py:194`
- **READ** `brain_core.py:858`
- **READ** `dashboard_api.py:1961`
- **READ** `entity_map_generator.py:6`
- **READ** `health_watchdog.py:110`
- **READ** `memory_recall.py:5`
- **READ** `price_source.py:437`
- **READ** `risk_engine.py:31`
- **READ** `risk_engine.py:161`
- **READ** `server.py:3114`
- **READ** `signal_engine.py:171`
- **READ** `signal_engine.py:1267`
- **READ** `stock_analyzer.py:348`
- **READ** `stock_analyzer.py:696`
- **READ** `stock_analyzer.py:696`
- **READ** `structured_memory.py:444`


### `this`

- **READ** `_tools/depmap.py:963`
- **READ** `_tools/depmap.py:970`
- **READ** `dashboard_api.py:984`
- **READ** `price_source.py:236`


### `those`

- **READ** `_tools/inventory_get_defaults.py:74`


### `tier1`

- **READ** `_tools/_fix_radar_indent.py:1`


### `time`

- **WRITE** `indicators.py:61`


### `tips_engine`

- **READ** `server.py:90`


### `today`

- **READ** `_tools/verify_sunday.py:92`
- **READ** `news_engine.py:298`
- **READ** `world_state_delta.py:148`


### `tool_cache`

- **READ** `chat_v7.py:66`


### `tool_registry`

- **READ** `server.py:632`


### `tool_summary`

- **READ** `server.py:7684`


### `top`

- **READ** `priority_engine.py:473`


### `traces`

- **CREATE** `mini_planner.py:99`
- **WRITE** `mini_planner.py:126`
- **READ** `cost_tracker.py:285`
- **READ** `mini_planner.py:159`
- **READ** `mini_planner.py:171`
- **READ** `mini_planner.py:173`
- **READ** `mini_planner.py:175`
- **READ** `mini_planner.py:177`
- **READ** `mini_planner.py:180`
- **READ** `server.py:9321`
- **READ** `server.py:9322`
- **READ** `server.py:9336`
- **DELETE** `cost_tracker.py:285`


### `trade`

- **WRITE** `dashboard_api.py:3065`


### `trade_journal`

- **CREATE** `trading_engine.py:21`
- **WRITE** `trading_engine.py:68`
- **WRITE** `trading_engine.py:116`
- **READ** `_tools/patchers/fix7_trading_issues.py:61`
- **READ** `_tools/patchers/fix7_trading_issues.py:64`
- **READ** `_tools/patchers/fix7_trading_issues.py:66`
- **READ** `domain_kpis.py:54`
- **READ** `domain_kpis.py:55`
- **READ** `trading_engine.py:86`
- **READ** `trading_engine.py:101`
- **READ** `trading_engine.py:127`
- **READ** `trading_engine.py:293`
- **READ** `trading_engine.py:302`
- **READ** `trading_engine.py:352`
- **READ** `trading_engine.py:353`
- **DELETE** `_tools/patchers/fix7_trading_issues.py:64`


### `trade_transactions`

- **CREATE** `journal_engine.py:82`
- **WRITE** `journal_engine.py:466`
- **WRITE** `journal_engine.py:524`
- **READ** `dashboard_api.py:2101`
- **READ** `journal_engine.py:550`


### `trades`

- **CREATE** `journal_engine.py:19`
- **WRITE** `_tools/migrate_direction_check.py:171`
- **WRITE** `_tools/migrate_direction_check.py:174`
- **WRITE** `_tools/migrate_direction_check.py:177`
- **WRITE** `_tools/migrate_direction_check.py:191`
- **WRITE** `_tools/patchers/fix6_standardize_tickers.py:26`
- **WRITE** `_tools/patchers/fix7_trading_issues.py:25`
- **WRITE** `_tools/prove_guards.py:391`
- **WRITE** `_tools/prove_guards.py:395`
- **WRITE** `_tools/prove_guards.py:446`
- **WRITE** `_tools/prove_guards.py:450`
- **WRITE** `_tools/prove_guards.py:487`
- **WRITE** `_tools/prove_guards.py:506`
- **WRITE** `_tools/prove_guards.py:518`
- **WRITE** `dashboard_api.py:3105`
- **WRITE** `journal_engine.py:183`
- **WRITE** `journal_engine.py:232`
- **WRITE** `journal_engine.py:256`
- **WRITE** `journal_engine.py:290`
- **WRITE** `journal_engine.py:315`
- **WRITE** `journal_engine.py:450`
- **WRITE** `journal_engine.py:458`
- **WRITE** `journal_engine.py:515`
- **WRITE** `life_stocks.py:139`
- **WRITE** `life_stocks.py:517`
- **WRITE** `position_engine.py:135`
- **WRITE** `position_engine.py:145`
- **WRITE** `position_engine.py:155`
- **WRITE** `position_engine.py:165`
- **WRITE** `position_engine.py:213`
- **READ** `_tools/db_sanity.py:178`
- **READ** `_tools/db_sanity.py:193`
- **READ** `_tools/migrate_direction_check.py:79`
- **READ** `_tools/migrate_direction_check.py:114`
- **READ** `_tools/migrate_direction_check.py:141`
- **READ** `_tools/migrate_direction_check.py:145`
- **READ** `_tools/patchers/fix6_standardize_tickers.py:20`
- **READ** `_tools/patchers/fix7_trading_issues.py:22`
- **READ** `_tools/patchers/fix7_trading_issues.py:27`
- **READ** `_tools/patchers/fix7_trading_issues.py:75`
- **READ** `_tools/patchers/fix7_trading_issues.py:78`
- **READ** `_tools/prove_guards.py:490`
- **READ** `_tools/prove_guards.py:497`
- **READ** `_tools/prove_guards.py:512`
- **READ** `_tools/prove_guards.py:524`
- **READ** `_tools/prove_guards.py:537`
- **READ** `dashboard_api.py:1193`
- **READ** `dashboard_api.py:1303`
- **READ** `dashboard_api.py:1582`
- **READ** `dashboard_api.py:3077`
- **READ** `journal_engine.py:201`
- **READ** `journal_engine.py:253`
- **READ** `journal_engine.py:264`
- **READ** `journal_engine.py:273`
- **READ** `journal_engine.py:282`
- **READ** `journal_engine.py:299`
- **READ** `journal_engine.py:347`
- **READ** `journal_engine.py:411`
- **READ** `journal_engine.py:498`
- **READ** `journal_engine.py:565`
- **READ** `life_stocks.py:311`
- **READ** `life_stocks.py:316`
- **READ** `position_engine.py:174`
- **READ** `position_engine.py:556`
- **READ** `risk_engine.py:326`
- **DELETE** `_tools/migrate_direction_check.py:36`
- **DELETE** `_tools/migrate_direction_check.py:147`
- **DELETE** `_tools/patchers/fix7_trading_issues.py:78`


### `trades_new`

- **CREATE** `_tools/migrate_direction_check.py:143`
- **WRITE** `_tools/migrate_direction_check.py:145`


### `trading_brain`

- **READ** `brain_backfill.py:314`
- **READ** `brain_backfill.py:444`
- **READ** `dashboard_api.py:2603`
- **READ** `gemini_scanner.py:299`
- **READ** `server.py:2963`
- **READ** `server.py:2979`
- **READ** `signal_engine.py:86`
- **READ** `signal_engine.py:1272`
- **READ** `stock_radar.py:363`
- **READ** `stock_radar.py:664`


### `trading_decision_engine`

- **READ** `golden_engine.py:717`


### `trading_engine`

- **READ** `chat_v7.py:440`
- **READ** `chat_v7.py:443`
- **READ** `server.py:590`
- **READ** `tg_morning_report.py:308`


### `tradingview`

- **READ** `_tools/_debug_ema.py:50`
- **READ** `chat_v7.py:364`
- **READ** `stock_alerts.py:84`


### `tradingview_bridge`

- **READ** `chat_v7.py:448`
- **READ** `chat_v7.py:451`
- **READ** `chat_v7.py:454`
- **READ** `chat_v7.py:457`
- **READ** `server.py:602`
- **READ** `tg_morning_report.py:315`


### `trailing`

- **WRITE** `position_engine.py:151`


### `tv_advisor`

- **READ** `chat_v7.py:477`


### `tv_alert_events`

- **CREATE** `tradingview_bridge.py:38`
- **WRITE** `_tools/patchers/fix_tv_alert_price.py:67`
- **WRITE** `_tools/patchers/fix_tv_alert_price.py:78`
- **WRITE** `tradingview_bridge.py:322`
- **WRITE** `tradingview_bridge.py:669`
- **READ** `_tools/patchers/fix_tv_alert_price.py:62`
- **READ** `_tools/patchers/fix_tv_alert_price.py:73`
- **READ** `dashboard_api.py:1502`
- **READ** `domain_kpis.py:62`
- **READ** `domain_kpis.py:63`
- **READ** `domain_kpis.py:64`
- **READ** `tradingview_bridge.py:536`
- **READ** `tradingview_bridge.py:553`
- **READ** `tradingview_bridge.py:586`
- **READ** `tradingview_bridge.py:589`
- **READ** `tradingview_bridge.py:594`
- **READ** `tradingview_bridge.py:598`
- **READ** `tradingview_bridge.py:601`
- **READ** `tradingview_bridge.py:789`
- **READ** `tradingview_bridge.py:802`
- **READ** `tradingview_bridge.py:803`
- **DELETE** `tradingview_bridge.py:789`


### `tv_analysis`

- **READ** `_tools/patch_daily_indicators.py:130`
- **READ** `chat_v7.py:467`
- **READ** `chat_v7.py:476`
- **READ** `quick_query.py:251`
- **READ** `tv_advisor.py:62`


### `tv_config`

- **CREATE** `tradingview_bridge.py:74`
- **READ** `tradingview_bridge.py:115`


### `tv_data`

- **READ** `_tools/_add_ema_active.py:44`
- **READ** `_tools/_add_ema_active_v2.py:49`
- **READ** `_tools/_add_ema_active_v3.py:53`
- **READ** `_tools/patchers/fix_tv_alert_price.py:13`
- **READ** `_tools/patchers/fix_tv_alert_price.py:41`
- **READ** `_tools/patchers/phase1_normalize_price.py:12`
- **READ** `_tools/patchers/phase5_daily_summary.py:103`
- **READ** `_tools/radar_diag.py:11`
- **READ** `_tools/radar_diag.py:40`
- **READ** `_tools/test_radar.py:25`
- **READ** `_tools/verify_sunday.py:134`
- **READ** `_tools/verify_sunday.py:145`
- **READ** `_tools/verify_sunday.py:200`
- **READ** `chat_v7.py:462`
- **READ** `chat_v7.py:466`
- **READ** `chat_v7.py:475`
- **READ** `chat_v7.py:498`
- **READ** `dashboard_api.py:214`
- **READ** `dashboard_api.py:458`
- **READ** `dashboard_api.py:719`
- **READ** `dashboard_api.py:1218`
- **READ** `dashboard_api.py:1342`
- **READ** `priority_engine.py:84`
- **READ** `quick_query.py:198`
- **READ** `quick_query.py:250`
- **READ** `server.py:2857`
- **READ** `server.py:3571`
- **READ** `server.py:3717`
- **READ** `server.py:3767`
- **READ** `server.py:3826`
- **READ** `server.py:3892`
- **READ** `signal_engine.py:352`
- **READ** `signal_engine.py:1290`
- **READ** `stock_radar.py:208`
- **READ** `stock_radar.py:225`
- **READ** `stock_radar.py:252`
- **READ** `stock_radar.py:585`
- **READ** `stock_radar.py:794`
- **READ** `stock_radar.py:811`
- **READ** `stock_radar.py:939`
- **READ** `stock_radar.py:962`
- **READ** `stock_radar.py:1058`
- **READ** `stock_radar.py:1091`
- **READ** `stock_radar.py:1134`
- **READ** `stock_radar.py:1174`
- **READ** `stock_radar.py:1190`
- **READ** `stock_radar.py:1242`
- **READ** `stock_radar.py:1279`
- **READ** `stock_radar.py:1600`
- **READ** `tg_stocks.py:109`
- **READ** `tradingview_bridge.py:304`


### `tv_signal_stats`

- **CREATE** `tradingview_bridge.py:63`
- **WRITE** `tradingview_bridge.py:358`
- **WRITE** `tradingview_bridge.py:363`
- **READ** `dashboard_api.py:1535`
- **READ** `tradingview_bridge.py:352`


### `tv_watchlists`

- **CREATE** `tradingview_bridge.py:24`
- **WRITE** `tradingview_bridge.py:446`
- **WRITE** `tradingview_bridge.py:458`
- **WRITE** `tradingview_bridge.py:484`
- **WRITE** `tradingview_bridge.py:493`
- **WRITE** `tradingview_bridge.py:498`
- **READ** `domain_kpis.py:65`
- **READ** `tradingview_bridge.py:217`
- **READ** `tradingview_bridge.py:440`
- **READ** `tradingview_bridge.py:489`
- **READ** `tradingview_bridge.py:510`
- **READ** `tradingview_bridge.py:604`


### `tvdatafeed`

- **READ** `_tools/radar_diag.py:41`
- **READ** `_tools/run_daily_refresh.py:33`
- **READ** `_tools/test_radar_venv.py:18`
- **READ** `tv_data.py:197`
- **READ** `tv_data.py:243`
- **READ** `tv_data.py:289`


### `typing`

- **READ** `auto_memory_extractor.py:17`
- **READ** `bridge_client.py:9`
- **READ** `coalesced_executor.py:16`
- **READ** `context_manager.py:15`
- **READ** `feedback_learner.py:25`
- **READ** `hooks.py:14`
- **READ** `inbox_engine.py:4`
- **READ** `intent_state_machine.py:25`
- **READ** `life_expenses.py:10`
- **READ** `life_stocks.py:11`
- **READ** `master_ai_tool.py:20`
- **READ** `memory_prefetch.py:18`
- **READ** `memory_recall.py:16`
- **READ** `parallel_coordinator.py:17`
- **READ** `server.py:37`
- **READ** `session_memory.py:14`
- **READ** `signal_review.py:14`
- **READ** `skill_loader.py:16`
- **READ** `structured_memory.py:29`
- **READ** `task_manager.py:21`
- **READ** `tips_engine.py:19`
- **READ** `tool_registry.py:14`


### `universe`

- **READ** `stock_radar.py:268`


### `unknown`

- **READ** `smart_router.py:2`


### `urllib`

- **READ** `_tools/depmap.py:29`
- **READ** `chat_v7.py:528`
- **READ** `google_auth_ext.py:177`
- **READ** `server.py:3367`


### `user`

- **READ** `corrections_loop.py:4`


### `user_profiles`

- **CREATE** `memory_db.py:12`
- **WRITE** `memory_db.py:91`
- **WRITE** `memory_db.py:94`
- **READ** `memory_db.py:88`
- **READ** `memory_db.py:101`
- **READ** `memory_db.py:127`


### `user_tasks`

- **CREATE** `tasks_db.py:17`
- **WRITE** `tasks_db.py:50`
- **WRITE** `tasks_db.py:128`
- **WRITE** `tasks_db.py:145`
- **READ** `tasks_db.py:65`
- **READ** `tasks_db.py:85`
- **READ** `tasks_db.py:101`
- **READ** `tasks_db.py:139`
- **READ** `tasks_db.py:155`
- **READ** `tasks_db.py:159`
- **READ** `tasks_db.py:166`
- **READ** `tasks_db.py:170`
- **READ** `tasks_db.py:174`
- **READ** `tasks_db.py:182`
- **READ** `tasks_db.py:186`
- **DELETE** `tasks_db.py:159`


### `users`

- **CREATE** `server.py:4819`
- **CREATE** `server.py:4835`
- **WRITE** `server.py:4821`
- **READ** `server.py:4836`


### `watchlist`

- **WRITE** `life_stocks.py:256`
- **WRITE** `life_stocks.py:262`
- **READ** `_tools/fractal_backtest.py:27`
- **READ** `_tools/fractal_backtest_v2.py:36`
- **READ** `life_stocks.py:278`
- **READ** `life_stocks.py:285`
- **DELETE** `life_stocks.py:278`


### `whatever`

- **READ** `indicators.py:231`


### `win_jobs`

- **CREATE** `server.py:1078`
- **WRITE** `server.py:1316`
- **WRITE** `server.py:4316`
- **WRITE** `server.py:4337`
- **WRITE** `server.py:4416`
- **WRITE** `tg_ops.py:70`
- **WRITE** `tg_ops.py:72`
- **READ** `server.py:4014`
- **READ** `server.py:4406`
- **READ** `server.py:4429`
- **READ** `server.py:4433`


### `windows`

- **READ** `bridge_client.py:3`


### `world_state`

- **READ** `chat_v7.py:662`
- **READ** `server.py:136`
- **READ** `world_state.py:7`


### `world_state_delta`

- **READ** `chat_v7.py:664`
- **READ** `quick_query.py:446`
- **READ** `server.py:6780`
- **READ** `world_state.py:266`


### `xml`

- **READ** `news_engine.py:14`
- **READ** `tg_news.py:9`


### `yahoo`

- **READ** `_tools/backfill_daily_bars.py:2`
- **READ** `_tools/daily_signal_review.py:5`


### `yahoo_bar_cache`

- **CREATE** `yahoo_gate.py:379`
- **READ** `yahoo_gate.py:396`


### `yahoo_gate`

- **READ** `_tools/quick_check.py:403`
- **READ** `dashboard_api.py:134`
- **READ** `dashboard_api.py:887`


### `yesterday`

- **READ** `signal_engine.py:850`
- **READ** `world_state_delta.py:167`


### `zero`

- **READ** `_tools/bar_completeness_probe.py:167`
- **READ** `bridge_client.py:97`


## Python symbol reverse index

_Symbols explicitly imported with `from X import Y` across file boundaries._

Note: symbols called via `module.func()` after `import module` are tracked in the module import list above, not here.


### `_tools.patchers.apply_text_patch.apply_patch`

- **Defined in:** `_tools/__init__.py`
- **Imported by:** `_tools/examples/test_patch.py:11`
- **Imported by:** `_tools/patch_email_news.py:5`
- **Imported by:** `_tools/patchers/fix_confluence_bugs.py:10`
- **Imported by:** `_tools/phase3_patch.py:8`


### `_tools.patchers.apply_text_patch.apply_patches`

- **Defined in:** `_tools/__init__.py`
- **Imported by:** `_tools/examples/test_patch.py:11`
- **Imported by:** `_tools/phase3_patch.py:8`


### `anomaly_engine.get_anomaly_summary`

- **Defined in:** `anomaly_engine.py`
- **Imported by:** `quick_query.py:467`
- **Imported by:** `server.py:9289`


### `anomaly_engine.run_anomaly_checks`

- **Defined in:** `anomaly_engine.py`
- **Imported by:** `tg_alerts.py:15`


### `approval_ux.format_approval_message`

- **Defined in:** `approval_ux.py`
- **Imported by:** `chat_v7.py:45`


### `auto_memory_extractor.AutoMemoryExtractor`

- **Defined in:** `auto_memory_extractor.py`
- **Imported by:** `server.py:7546`


### `brain.backup_loop`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.build_response_prompt`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.build_system_prompt`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.detect_user`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.get_analytics`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.get_brain_stats`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.get_multiuser_stats`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.get_quick_response`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.get_system_diag`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.learn_from_result`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.log_request`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.proactive_loop`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.record_error`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.record_feedback`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.reload`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain.run_backup`

- **Defined in:** `brain.py`
- **Imported by:** `server.py:53`


### `brain_analytics.get_analytics`

- **Defined in:** `brain_analytics.py`
- **Imported by:** `brain.py:124`


### `brain_analytics.log_request`

- **Defined in:** `brain_analytics.py`
- **Imported by:** `brain.py:124`


### `brain_analytics.record_feedback`

- **Defined in:** `brain_analytics.py`
- **Imported by:** `brain.py:124`


### `brain_core._expert_knowledge`

- **Defined in:** `brain_core.py`
- **Imported by:** `server.py:5167`


### `brain_core.build_room_index`

- **Defined in:** `brain_core.py`
- **Imported by:** `brain.py:14`


### `brain_core.build_system_prompt`

- **Defined in:** `brain_core.py`
- **Imported by:** `brain.py:14`


### `brain_core.build_system_prompt_v7`

- **Defined in:** `brain_core.py`
- **Imported by:** `server.py:2453`
- **Imported by:** `server.py:4127`
- **Imported by:** `server.py:4204`
- **Imported by:** `server.py:7628`
- **Imported by:** `server.py:7995`


### `brain_core.format_observation_manifest`

- **Defined in:** `brain_core.py`
- **Imported by:** `auto_memory_extractor.py:98`
- **Imported by:** `memory_recall.py:56`


### `brain_core.get_brain_stats`

- **Defined in:** `brain_core.py`
- **Imported by:** `brain.py:14`


### `brain_core.get_full_observations`

- **Defined in:** `brain_core.py`
- **Imported by:** `memory_recall.py:56`


### `brain_core.get_islamic_dates_context`

- **Defined in:** `brain_core.py`
- **Imported by:** `chat_v7.py:652`


### `brain_core.get_observation_manifest`

- **Defined in:** `brain_core.py`
- **Imported by:** `auto_memory_extractor.py:98`
- **Imported by:** `memory_recall.py:56`


### `brain_core.get_owner_context`

- **Defined in:** `brain_core.py`
- **Imported by:** `server.py:367`


### `brain_core.get_relevant_memories`

- **Defined in:** `brain_core.py`
- **Imported by:** `server.py:367`


### `brain_core.get_system_awareness`

- **Defined in:** `brain_core.py`
- **Imported by:** `server.py:5156`


### `brain_core.lookup_expertise`

- **Defined in:** `brain_core.py`
- **Imported by:** `server.py:5167`


### `brain_core.memory_age_days`

- **Defined in:** `brain_core.py`
- **Imported by:** `dashboard_api.py:3544`


### `brain_core.reload`

- **Defined in:** `brain_core.py`
- **Imported by:** `brain.py:14`


### `brain_core.resolve_aliases`

- **Defined in:** `brain_core.py`
- **Imported by:** `brain.py:14`


### `brain_learning.build_daily_summary_report`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:151`
- **Imported by:** `tg_intent_router.py:326`


### `brain_learning.create_ha_automation`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:150`


### `brain_learning.create_ha_scene`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:158`


### `brain_learning.detect_anomalies`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:149`
- **Imported by:** `tg_morning_report.py:158`


### `brain_learning.discover_scenes`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:158`


### `brain_learning.filter_existing_automations`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:159`


### `brain_learning.format_anomaly_report`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:149`
- **Imported by:** `tg_intent_router.py:335`


### `brain_learning.format_maturity_report`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:148`
- **Imported by:** `tg_intent_router.py:344`


### `brain_learning.format_patterns_report`

- **Defined in:** `brain_learning.py`
- **Imported by:** `brain.py:31`
- **Imported by:** `server.py:147`
- **Imported by:** `tg_intent_router.py:1133`


### `brain_learning.format_scenes_report`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:158`
- **Imported by:** `tg_intent_router.py:317`


### `brain_learning.get_learning_stats`

- **Defined in:** `brain_learning.py`
- **Imported by:** `brain.py:31`
- **Imported by:** `server.py:147`
- **Imported by:** `tg_intent_router.py:1158`


### `brain_learning.get_maturity_report`

- **Defined in:** `brain_learning.py`
- **Imported by:** `tg_morning_report.py:158`


### `brain_learning.get_patterns`

- **Defined in:** `brain_learning.py`
- **Imported by:** `brain.py:31`
- **Imported by:** `server.py:147`


### `brain_learning.get_top_suggestions`

- **Defined in:** `brain_learning.py`
- **Imported by:** `server.py:150`
- **Imported by:** `tg_morning_report.py:158`


### `brain_learning.learn_patterns`

- **Defined in:** `brain_learning.py`
- **Imported by:** `brain.py:31`
- **Imported by:** `server.py:147`


### `brain_learning.suggest_automations`

- **Defined in:** `brain_learning.py`
- **Imported by:** `brain.py:31`
- **Imported by:** `server.py:147`
- **Imported by:** `tg_intent_router.py:1133`


### `brain_multiuser.detect_user`

- **Defined in:** `brain_multiuser.py`
- **Imported by:** `brain.py:106`


### `brain_multiuser.get_multiuser_stats`

- **Defined in:** `brain_multiuser.py`
- **Imported by:** `brain.py:106`


### `brain_multiuser.get_user_patterns`

- **Defined in:** `brain_multiuser.py`
- **Imported by:** `brain.py:106`


### `brain_multiuser.get_user_response_style`

- **Defined in:** `brain_multiuser.py`
- **Imported by:** `brain.py:106`


### `brain_observability.backup_loop`

- **Defined in:** `brain_observability.py`
- **Imported by:** `brain.py:85`


### `brain_observability.errors_last_hour`

- **Defined in:** `brain_observability.py`
- **Imported by:** `brain.py:85`


### `brain_observability.get_system_diag`

- **Defined in:** `brain_observability.py`
- **Imported by:** `brain.py:85`


### `brain_observability.record_error`

- **Defined in:** `brain_observability.py`
- **Imported by:** `brain.py:85`


### `brain_observability.run_backup`

- **Defined in:** `brain_observability.py`
- **Imported by:** `brain.py:85`


### `brain_personality.build_response_prompt`

- **Defined in:** `brain_personality.py`
- **Imported by:** `brain.py:52`


### `brain_personality.get_quick_response`

- **Defined in:** `brain_personality.py`
- **Imported by:** `brain.py:52`


### `brain_proactive._ensure_alerts_table`

- **Defined in:** `brain_proactive.py`
- **Imported by:** `brain.py:68`


### `brain_proactive.get_proactive_stats`

- **Defined in:** `brain_proactive.py`
- **Imported by:** `brain.py:68`


### `brain_proactive.proactive_loop`

- **Defined in:** `brain_proactive.py`
- **Imported by:** `brain.py:68`


### `bridge_client.BRIDGE_BASE_URL`

- **Defined in:** `bridge_client.py`
- **Imported by:** `_tools/_debug_ema.py:20`
- **Imported by:** `kairos.py:207`
- **Imported by:** `server.py:3890`
- **Imported by:** `server.py:3037`
- **Imported by:** `server.py:8095`
- **Imported by:** `signal_engine.py:1342`
- **Imported by:** `signal_engine.py:1405`


### `bridge_client.BridgeClient`

- **Defined in:** `bridge_client.py`
- **Imported by:** `_tools/_debug_ema.py:20`
- **Imported by:** `kairos.py:207`
- **Imported by:** `server.py:3890`
- **Imported by:** `server.py:3037`
- **Imported by:** `server.py:8095`
- **Imported by:** `signal_engine.py:1342`
- **Imported by:** `signal_engine.py:1405`


### `bridge_client.circuit_stats`

- **Defined in:** `bridge_client.py`
- **Imported by:** `dashboard_api.py:1899`
- **Imported by:** `server.py:3120`
- **Imported by:** `signal_engine.py:1329`
- **Imported by:** `signal_engine.py:1394`


### `bridge_client.get_bridge_client`

- **Defined in:** `bridge_client.py`
- **Imported by:** `dashboard_api.py:1886`
- **Imported by:** `dashboard_api.py:1910`
- **Imported by:** `data_integrity.py:121`
- **Imported by:** `gemini_scanner.py:193`
- **Imported by:** `signal_engine.py:1612`
- **Imported by:** `trading_brain.py:374`


### `bridge_client.init_bridge_client`

- **Defined in:** `bridge_client.py`
- **Imported by:** `server.py:2912`


### `bridge_client.reset_circuit`

- **Defined in:** `bridge_client.py`
- **Imported by:** `server.py:3140`


### `calendar_db.cancel_event_reminders`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.clear_sync_state`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.delete_event_local`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.get_calendar_stats`

- **Defined in:** `calendar_db.py`
- **Imported by:** `server.py:3517`


### `calendar_db.get_db`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.get_due_reminders`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_reminders.py:11`


### `calendar_db.get_event_by_google_id`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.get_events_range`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.init_life_db`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.insert_reminder`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.load_sync_state`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.mark_deleted`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.mark_reminder_sent`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_reminders.py:11`


### `calendar_db.save_sync_state`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_db.upsert_event`

- **Defined in:** `calendar_db.py`
- **Imported by:** `calendar_engine.py:18`


### `calendar_engine.calendar_sync_loop`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `server.py:2712`


### `calendar_engine.create_event`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `chat_v7.py:626`


### `calendar_engine.delete_event`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `chat_v7.py:630`


### `calendar_engine.ensure_fresh_cache`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `server.py:6789`


### `calendar_engine.get_events_range`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `chat_v7.py:614`


### `calendar_engine.get_today_events`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `chat_v7.py:614`
- **Imported by:** `quick_query.py:297`
- **Imported by:** `server.py:6131`
- **Imported by:** `server.py:6789`
- **Imported by:** `server.py:6858`
- **Imported by:** `tg_morning_report.py:221`


### `calendar_engine.get_tomorrow_events`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `chat_v7.py:614`
- **Imported by:** `quick_query.py:320`
- **Imported by:** `server.py:6820`
- **Imported by:** `server.py:6858`


### `calendar_engine.get_week_events`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `chat_v7.py:614`
- **Imported by:** `chat_v7.py:630`
- **Imported by:** `quick_query.py:328`
- **Imported by:** `server.py:6849`


### `calendar_engine.sync_full`

- **Defined in:** `calendar_engine.py`
- **Imported by:** `server.py:3527`


### `calendar_reminders.run_reminder_loop`

- **Defined in:** `calendar_reminders.py`
- **Imported by:** `server.py:2713`


### `calendar_reporting.render_morning_calendar_section`

- **Defined in:** `calendar_reporting.py`
- **Imported by:** `server.py:6132`
- **Imported by:** `tg_morning_report.py:222`


### `calendar_reporting.render_today`

- **Defined in:** `calendar_reporting.py`
- **Imported by:** `chat_v7.py:615`
- **Imported by:** `quick_query.py:298`
- **Imported by:** `server.py:6793`
- **Imported by:** `server.py:6859`


### `calendar_reporting.render_tomorrow`

- **Defined in:** `calendar_reporting.py`
- **Imported by:** `chat_v7.py:615`
- **Imported by:** `quick_query.py:321`
- **Imported by:** `server.py:6822`
- **Imported by:** `server.py:6859`


### `calendar_reporting.render_week`

- **Defined in:** `calendar_reporting.py`
- **Imported by:** `chat_v7.py:615`
- **Imported by:** `quick_query.py:329`
- **Imported by:** `server.py:6851`


### `chat_v7.choose_model`

- **Defined in:** `chat_v7.py`
- **Imported by:** `server.py:7622`
- **Imported by:** `server.py:7645`


### `chat_v7.clear_chat_v7_history`

- **Defined in:** `chat_v7.py`
- **Imported by:** `server.py:8369`


### `chat_v7.handle_chat_v7`

- **Defined in:** `chat_v7.py`
- **Imported by:** `server.py:108`


### `chat_v7.handle_chat_v7_stream`

- **Defined in:** `chat_v7.py`
- **Imported by:** `server.py:108`


### `circuit_breaker.CircuitBreaker`

- **Defined in:** `circuit_breaker.py`
- **Imported by:** `news_engine.py:16`
- **Imported by:** `server.py:5323`


### `coalesced_executor.CoalescedExecutor`

- **Defined in:** `coalesced_executor.py`
- **Imported by:** `auto_memory_extractor.py:20`
- **Imported by:** `stock_radar.py:24`


### `confidence_engine.choose_response_layer`

- **Defined in:** `confidence_engine.py`
- **Imported by:** `chat_v7.py:39`


### `confidence_engine.score_tool_call`

- **Defined in:** `confidence_engine.py`
- **Imported by:** `chat_v7.py:39`


### `confluence_engine._dedup_items_keep_latest`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `dashboard_api.py:1432`


### `confluence_engine.build_tg_alert`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `server.py:565`


### `confluence_engine.get_actionable_signals`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `dashboard_api.py:1432`
- **Imported by:** `server.py:565`


### `confluence_engine.get_confluence_stats`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `dashboard_api.py:1432`
- **Imported by:** `server.py:565`


### `confluence_engine.get_watchlist_signals`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `dashboard_api.py:1432`
- **Imported by:** `server.py:565`


### `confluence_engine.init_schema`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `server.py:565`


### `confluence_engine.record_decision`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `server.py:565`


### `confluence_engine.run_confluence_scan`

- **Defined in:** `confluence_engine.py`
- **Imported by:** `server.py:565`


### `context_compactor.ContextCompactor`

- **Defined in:** `context_compactor.py`
- **Imported by:** `tg_session.py:136`


### `context_manager.manage_context`

- **Defined in:** `context_manager.py`
- **Imported by:** `chat_v7.py:11`


### `contract.expect`

- **Defined in:** `contract.py`
- **Imported by:** `gemini_scanner.py:199`
- **Imported by:** `gemini_scanner.py:314`


### `corrections_loop.apply_corrections_to_text`

- **Defined in:** `corrections_loop.py`
- **Imported by:** `chat_v7.py:32`


### `corrections_loop.get_correction_context`

- **Defined in:** `corrections_loop.py`
- **Imported by:** `chat_v7.py:32`


### `corrections_loop.get_corrections_loop`

- **Defined in:** `corrections_loop.py`
- **Imported by:** `server.py:6928`
- **Imported by:** `server.py:6949`
- **Imported by:** `server.py:9217`
- **Imported by:** `server.py:9226`
- **Imported by:** `server.py:8847`


### `corrections_loop.process_correction`

- **Defined in:** `corrections_loop.py`
- **Imported by:** `chat_v7.py:32`


### `cost_tracker.get_cost_for_kpi`

- **Defined in:** `cost_tracker.py`
- **Imported by:** `dashboard_api.py:1730`
- **Imported by:** `quick_query.py:483`
- **Imported by:** `server.py:9357`
- **Imported by:** `server.py:5445`
- **Imported by:** `server.py:6879`
- **Imported by:** `server.py:6108`


### `cost_tracker.get_cost_summary`

- **Defined in:** `cost_tracker.py`
- **Imported by:** `server.py:9301`


### `cost_tracker.track_cost`

- **Defined in:** `cost_tracker.py`
- **Imported by:** `chat_v7.py:73`


### `cost_tracker.track_cost_openai`

- **Defined in:** `cost_tracker.py`
- **Imported by:** `chat_v7.py:73`


### `dashboard_api._require_api_key`

- **Defined in:** `dashboard_api.py`
- **Imported by:** `server.py:3170`


### `dashboard_api.ha_dashboard_extended`

- **Defined in:** `dashboard_api.py`
- **Imported by:** `server.py:2611`


### `dashboard_api.init_dashboard_context`

- **Defined in:** `dashboard_api.py`
- **Imported by:** `server.py:2611`


### `dashboard_api.router`

- **Defined in:** `dashboard_api.py`
- **Imported by:** `server.py:3170`


### `data_integrity.DataIntegrityGate`

- **Defined in:** `data_integrity.py`
- **Imported by:** `golden_engine.py:743`


### `db_backup.format_status`

- **Defined in:** `db_backup.py`
- **Imported by:** `server.py:205`


### `db_backup.get_status`

- **Defined in:** `db_backup.py`
- **Imported by:** `server.py:205`


### `db_backup.init`

- **Defined in:** `db_backup.py`
- **Imported by:** `server.py:205`


### `db_backup.run_daily`

- **Defined in:** `db_backup.py`
- **Imported by:** `server.py:205`


### `degraded_mode.format_status`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `degraded_mode.get_mode`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `degraded_mode.init`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `degraded_mode.is_degraded`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `degraded_mode.is_ok`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `degraded_mode.mark_fail`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `degraded_mode.mark_ok`

- **Defined in:** `degraded_mode.py`
- **Imported by:** `server.py:197`


### `discovery.get_discovery_stats`

- **Defined in:** `discovery.py`
- **Imported by:** `server.py:166`


### `discovery.get_home_summary`

- **Defined in:** `discovery.py`
- **Imported by:** `server.py:166`


### `discovery.sync_entities`

- **Defined in:** `discovery.py`
- **Imported by:** `server.py:166`


### `domain_kpis.handle_kpi`

- **Defined in:** `domain_kpis.py`
- **Imported by:** `server.py:6646`


### `dream_consolidator.format_dream_status`

- **Defined in:** `dream_consolidator.py`
- **Imported by:** `server.py:5454`


### `dream_consolidator.get_dream_status`

- **Defined in:** `dream_consolidator.py`
- **Imported by:** `server.py:3275`
- **Imported by:** `server.py:5454`


### `dream_consolidator.run_dream_consolidation`

- **Defined in:** `dream_consolidator.py`
- **Imported by:** `server.py:3284`
- **Imported by:** `server.py:5463`
- **Imported by:** `server.py:2941`


### `entity_health.ENTITY_MAP_PATH`

- **Defined in:** `entity_health.py`
- **Imported by:** `server.py:8504`


### `entity_health.arabize_entity_map`

- **Defined in:** `entity_health.py`
- **Imported by:** `server.py:8504`


### `entity_health.load_entity_map`

- **Defined in:** `entity_health.py`
- **Imported by:** `server.py:8504`


### `entity_health.validate_entity_map`

- **Defined in:** `entity_health.py`
- **Imported by:** `server.py:8491`
- **Imported by:** `server.py:8618`


### `equity_tracker.get_equity_dashboard`

- **Defined in:** `equity_tracker.py`
- **Imported by:** `dashboard_api.py:2418`


### `exec_policy.check_policy`

- **Defined in:** `exec_policy.py`
- **Imported by:** `chat_v7.py:80`


### `exec_policy.get_tool_stats`

- **Defined in:** `exec_policy.py`
- **Imported by:** `chat_v7.py:80`
- **Imported by:** `server.py:3549`


### `exec_policy.record_outcome`

- **Defined in:** `exec_policy.py`
- **Imported by:** `chat_v7.py:80`


### `exec_policy.track_session`

- **Defined in:** `exec_policy.py`
- **Imported by:** `chat_v7.py:80`


### `expenses_engine.add_expense`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `chat_v7.py:412`
- **Imported by:** `server.py:519`


### `expenses_engine.delete_expense`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `server.py:519`


### `expenses_engine.format_add_confirmation`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `chat_v7.py:412`
- **Imported by:** `server.py:519`


### `expenses_engine.format_recent_tg`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `chat_v7.py:418`
- **Imported by:** `server.py:519`


### `expenses_engine.format_summary_tg`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `chat_v7.py:415`
- **Imported by:** `server.py:519`


### `expenses_engine.get_morning_expense_text`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `server.py:519`
- **Imported by:** `tg_morning_report.py:274`


### `expenses_engine.get_summary`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `chat_v7.py:415`
- **Imported by:** `server.py:519`


### `expenses_engine.handle_recent_expenses`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `quick_query.py:188`
- **Imported by:** `server.py:519`


### `expenses_engine.handle_spent_month`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `quick_query.py:181`
- **Imported by:** `server.py:519`


### `expenses_engine.handle_spent_today`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `quick_query.py:167`
- **Imported by:** `server.py:519`


### `expenses_engine.handle_spent_week`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `quick_query.py:174`
- **Imported by:** `server.py:519`


### `expenses_engine.init_schema`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `server.py:519`


### `expenses_engine.list_expenses`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `chat_v7.py:418`
- **Imported by:** `server.py:519`


### `expenses_engine.parse_expense`

- **Defined in:** `expenses_engine.py`
- **Imported by:** `server.py:519`


### `family_assistant.get_family_info`

- **Defined in:** `family_assistant.py`
- **Imported by:** `quick_query.py:430`
- **Imported by:** `server.py:6762`


### `feature_flags.FeatureFlags`

- **Defined in:** `feature_flags.py`
- **Imported by:** `_tools/verify_sunday.py:112`
- **Imported by:** `google_auth_ext.py:61`
- **Imported by:** `kse_data_collector.py:500`
- **Imported by:** `server.py:628`
- **Imported by:** `stock_radar.py:911`
- **Imported by:** `stock_radar.py:926`
- **Imported by:** `tg_session.py:123`


### `feedback_learner.apply_learning`

- **Defined in:** `feedback_learner.py`
- **Imported by:** `server.py:181`


### `feedback_learner.generate_digest`

- **Defined in:** `feedback_learner.py`
- **Imported by:** `server.py:9277`
- **Imported by:** `server.py:6918`
- **Imported by:** `server.py:8960`


### `feedback_learner.get_confidence_adjustment`

- **Defined in:** `feedback_learner.py`
- **Imported by:** `confidence_engine.py:8`
- **Imported by:** `server.py:181`


### `feedback_learner.get_stats`

- **Defined in:** `feedback_learner.py`
- **Imported by:** `server.py:9269`
- **Imported by:** `server.py:6899`


### `feedback_learner.init`

- **Defined in:** `feedback_learner.py`
- **Imported by:** `server.py:181`


### `feedback_learner.record_feedback`

- **Defined in:** `feedback_learner.py`
- **Imported by:** `server.py:7110`


### `golden_engine.scan_opportunities`

- **Defined in:** `golden_engine.py`
- **Imported by:** `_tools/daily_signal_review.py:44`
- **Imported by:** `gemini_scanner.py:313`
- **Imported by:** `server.py:3618`
- **Imported by:** `server.py:6416`


### `google_auth_ext._google_integrations_enabled`

- **Defined in:** `google_auth_ext.py`
- **Imported by:** `tg_email.py:33`


### `google_auth_ext.build_auth_url`

- **Defined in:** `google_auth_ext.py`
- **Imported by:** `server.py:3458`


### `google_auth_ext.build_calendar_service`

- **Defined in:** `google_auth_ext.py`
- **Imported by:** `calendar_engine.py:108`
- **Imported by:** `server.py:3479`


### `google_auth_ext.build_gmail_service`

- **Defined in:** `google_auth_ext.py`
- **Imported by:** `tg_email.py:33`


### `google_auth_ext.exchange_code`

- **Defined in:** `google_auth_ext.py`
- **Imported by:** `server.py:3479`


### `google_auth_ext.get_auth_status`

- **Defined in:** `google_auth_ext.py`
- **Imported by:** `server.py:3479`
- **Imported by:** `server.py:3507`


### `ha_doctor.check_ac_performance`

- **Defined in:** `ha_doctor.py`
- **Imported by:** `server.py:145`


### `ha_doctor.detect_anomalies`

- **Defined in:** `ha_doctor.py`
- **Imported by:** `server.py:145`


### `ha_doctor.format_health_report`

- **Defined in:** `ha_doctor.py`
- **Imported by:** `server.py:145`


### `ha_doctor.get_unavailable_entities`

- **Defined in:** `ha_doctor.py`
- **Imported by:** `server.py:145`


### `ha_doctor.suggest_fixes`

- **Defined in:** `ha_doctor.py`
- **Imported by:** `server.py:145`


### `ha_history.analyze_entity`

- **Defined in:** `ha_history.py`
- **Imported by:** `server.py:146`


### `ha_history.format_history_report`

- **Defined in:** `ha_history.py`
- **Imported by:** `server.py:146`
- **Imported by:** `tg_intent_router.py:972`


### `ha_history.get_entity_history`

- **Defined in:** `ha_history.py`
- **Imported by:** `server.py:146`


### `habit_engine.format_habit_report`

- **Defined in:** `habit_engine.py`
- **Imported by:** `quick_query.py:459`
- **Imported by:** `server.py:6872`


### `habit_engine.learn_morning_routine`

- **Defined in:** `habit_engine.py`
- **Imported by:** `proactive_engine.py:80`


### `health_engine.get_morning_health_text`

- **Defined in:** `health_engine.py`
- **Imported by:** `tg_morning_report.py:301`


### `health_engine.handle_health_log`

- **Defined in:** `health_engine.py`
- **Imported by:** `server.py:578`


### `health_engine.handle_health_streak`

- **Defined in:** `health_engine.py`
- **Imported by:** `server.py:578`


### `health_engine.handle_health_summary`

- **Defined in:** `health_engine.py`
- **Imported by:** `server.py:578`


### `health_engine.init_schema`

- **Defined in:** `health_engine.py`
- **Imported by:** `server.py:578`


### `health_engine.llm_tool_health_log`

- **Defined in:** `health_engine.py`
- **Imported by:** `chat_v7.py:433`


### `health_engine.llm_tool_health_summary`

- **Defined in:** `health_engine.py`
- **Imported by:** `chat_v7.py:436`


### `health_engine.quick_health_summary`

- **Defined in:** `health_engine.py`
- **Imported by:** `server.py:578`


### `health_engine.quick_health_today`

- **Defined in:** `health_engine.py`
- **Imported by:** `server.py:578`


### `home_brain.build_digest_prompt`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.cleanup_old_data`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.detect_patterns`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.format_insights_ar`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.get_brain_stats`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.get_daily_summary`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.get_db_size`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `home_brain.take_snapshot`

- **Defined in:** `home_brain.py`
- **Imported by:** `server.py:128`


### `hooks.HookRegistry`

- **Defined in:** `hooks.py`
- **Imported by:** `server.py:631`


### `inbox_engine.P_CRITICAL`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `proactive_suggestions.py:188`
- **Imported by:** `server.py:6056`
- **Imported by:** `server.py:6133`


### `inbox_engine.P_HIGH`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `server.py:6056`
- **Imported by:** `server.py:6133`


### `inbox_engine.fetch_unified_inbox`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `dashboard_api.py:1778`
- **Imported by:** `dashboard_api.py:338`
- **Imported by:** `proactive_suggestions.py:188`
- **Imported by:** `server.py:6056`
- **Imported by:** `server.py:6133`
- **Imported by:** `server.py:6220`


### `inbox_engine.format_email_task_suggestions`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `quick_query.py:408`
- **Imported by:** `server.py:6119`
- **Imported by:** `tg_morning_report.py:292`


### `inbox_engine.format_inbox_tg`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `server.py:6220`


### `inbox_engine.inbox_digest`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `server.py:8857`
- **Imported by:** `tg_morning_report.py:255`


### `inbox_engine.inbox_weekly_digest`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `server.py:6189`
- **Imported by:** `server.py:6220`
- **Imported by:** `server.py:8970`


### `inbox_engine.llm_tool_inbox_summary`

- **Defined in:** `inbox_engine.py`
- **Imported by:** `chat_v7.py:376`


### `indicators.KSE_CLOSE_UTC_H`

- **Defined in:** `indicators.py`
- **Imported by:** `_tools/bar_completeness_probe.py:27`


### `indicators.KSE_OPEN_UTC_H`

- **Defined in:** `indicators.py`
- **Imported by:** `_tools/bar_completeness_probe.py:27`


### `indicators.KSE_TRADING_WEEKDAYS`

- **Defined in:** `indicators.py`
- **Imported by:** `_tools/bar_completeness_probe.py:27`


### `indicators.compute_all`

- **Defined in:** `indicators.py`
- **Imported by:** `_tools/backfill_daily_bars.py:287`


### `indicators.is_bar_complete`

- **Defined in:** `indicators.py`
- **Imported by:** `_tools/bar_completeness_probe.py:27`


### `intent_state_machine.IntentContext`

- **Defined in:** `intent_state_machine.py`
- **Imported by:** `tg_intent_router.py:17`


### `intent_state_machine.IntentState`

- **Defined in:** `intent_state_machine.py`
- **Imported by:** `tg_intent_router.py:17`


### `intent_state_machine.log_intent_audit`

- **Defined in:** `intent_state_machine.py`
- **Imported by:** `tg_intent_router.py:17`


### `journal_engine.add_more_trade`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:8205`


### `journal_engine.calculate_real_pnl`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:1217`
- **Imported by:** `dashboard_api.py:1015`
- **Imported by:** `dashboard_api.py:714`
- **Imported by:** `position_engine.py:441`


### `journal_engine.cancel_trade`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:551`


### `journal_engine.close_trade`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:3050`
- **Imported by:** `server.py:551`


### `journal_engine.format_weekly_report_tg`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:9004`


### `journal_engine.generate_weekly_report`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:9004`


### `journal_engine.get_fresh_price`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:1217`
- **Imported by:** `dashboard_api.py:1015`
- **Imported by:** `dashboard_api.py:726`
- **Imported by:** `position_engine.py:96`
- **Imported by:** `signal_engine.py:536`


### `journal_engine.get_open_trades`

- **Defined in:** `journal_engine.py`
- **Imported by:** `_tools/intraday_refresh.py:60`
- **Imported by:** `dashboard_api.py:1217`
- **Imported by:** `dashboard_api.py:2508`
- **Imported by:** `dashboard_api.py:1015`
- **Imported by:** `golden_engine.py:944`
- **Imported by:** `position_engine.py:282`
- **Imported by:** `position_engine.py:441`
- **Imported by:** `server.py:551`
- **Imported by:** `signal_engine.py:1301`
- **Imported by:** `tg_stocks.py:75`


### `journal_engine.get_recent_trades`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:1169`
- **Imported by:** `dashboard_api.py:1217`
- **Imported by:** `dashboard_api.py:1015`
- **Imported by:** `server.py:551`


### `journal_engine.get_trade`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:551`


### `journal_engine.get_trade_stats`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:1177`
- **Imported by:** `dashboard_api.py:1217`
- **Imported by:** `dashboard_api.py:1015`
- **Imported by:** `server.py:551`
- **Imported by:** `tg_stocks.py:75`


### `journal_engine.get_trade_transactions`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:8220`


### `journal_engine.init_schema`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:551`


### `journal_engine.open_trade`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:3020`
- **Imported by:** `server.py:551`


### `journal_engine.partial_sell_trade`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:8184`


### `journal_engine.suggest_trailing_stop`

- **Defined in:** `journal_engine.py`
- **Imported by:** `dashboard_api.py:1150`


### `journal_engine.update_trade_notes`

- **Defined in:** `journal_engine.py`
- **Imported by:** `server.py:551`


### `kairos.KairosAgent`

- **Defined in:** `kairos.py`
- **Imported by:** `server.py:630`


### `kse_data_collector.BRIDGE_URL`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `_tools/debug_collector.py:6`


### `kse_data_collector._fetch_bridge_bars`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `_tools/debug_collector.py:6`


### `kse_data_collector._get_watchlist_symbols`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `_tools/debug_collector.py:6`


### `kse_data_collector.collect_and_refresh`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `dashboard_api.py:3270`


### `kse_data_collector.daily_collection_scheduler`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `server.py:2649`


### `kse_data_collector.get_data_health`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `dashboard_api.py:3157`


### `kse_data_collector.is_collecting`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `dashboard_api.py:3270`


### `kse_data_collector.log_decision`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `golden_engine.py:996`


### `kse_data_collector.market_hours_scanner`

- **Defined in:** `kse_data_collector.py`
- **Imported by:** `server.py:2655`


### `life_expenses.get_expenses`

- **Defined in:** `life_expenses.py`
- **Imported by:** `server.py:6691`
- **Imported by:** `tg_report.py:79`


### `life_expenses.handle_expense_command`

- **Defined in:** `life_expenses.py`
- **Imported by:** `server.py:233`


### `life_health.handle_health_command`

- **Defined in:** `life_health.py`
- **Imported by:** `server.py:240`


### `life_health.health_summary`

- **Defined in:** `life_health.py`
- **Imported by:** `server.py:6703`


### `life_router.detect_life_domain`

- **Defined in:** `life_router.py`
- **Imported by:** `server.py:219`


### `life_stocks.KNOWN_TICKERS`

- **Defined in:** `life_stocks.py`
- **Imported by:** `tg_stocks.py:99`


### `life_stocks.handle_stock_command`

- **Defined in:** `life_stocks.py`
- **Imported by:** `server.py:226`


### `life_stocks.portfolio_summary`

- **Defined in:** `life_stocks.py`
- **Imported by:** `server.py:226`
- **Imported by:** `tg_morning_report.py:142`


### `life_work.SHIFT_EMOJI`

- **Defined in:** `life_work.py`
- **Imported by:** `server.py:8538`
- **Imported by:** `server.py:8794`


### `life_work.get_shift`

- **Defined in:** `life_work.py`
- **Imported by:** `calendar_reporting.py:43`
- **Imported by:** `chat_v7.py:567`
- **Imported by:** `dashboard_api.py:204`
- **Imported by:** `dashboard_api.py:1750`
- **Imported by:** `quick_query.py:299`
- **Imported by:** `quick_query.py:358`
- **Imported by:** `server.py:8538`
- **Imported by:** `server.py:6054`
- **Imported by:** `server.py:6129`
- **Imported by:** `server.py:6798`
- **Imported by:** `server.py:6826`
- **Imported by:** `server.py:7966`
- **Imported by:** `server.py:8592`
- **Imported by:** `server.py:8794`
- **Imported by:** `tg_report.py:23`


### `life_work.get_shift_display`

- **Defined in:** `life_work.py`
- **Imported by:** `chat_v7.py:567`
- **Imported by:** `proactive_engine.py:92`
- **Imported by:** `server.py:247`


### `life_work.get_week_schedule`

- **Defined in:** `life_work.py`
- **Imported by:** `quick_query.py:358`
- **Imported by:** `server.py:6671`


### `life_work.handle_work_command`

- **Defined in:** `life_work.py`
- **Imported by:** `server.py:247`


### `memory_db.add_memory`

- **Defined in:** `memory_db.py`
- **Imported by:** `server.py:928`


### `memory_db.build_context`

- **Defined in:** `memory_db.py`
- **Imported by:** `server.py:928`


### `memory_db.get_memories`

- **Defined in:** `memory_db.py`
- **Imported by:** `chat_v7.py:542`
- **Imported by:** `server.py:928`


### `memory_db.get_memory_stats`

- **Defined in:** `memory_db.py`
- **Imported by:** `server.py:928`
- **Imported by:** `server.py:5098`


### `memory_db.init_memory_db`

- **Defined in:** `memory_db.py`
- **Imported by:** `server.py:928`


### `memory_db.save_memory_with_facts`

- **Defined in:** `memory_db.py`
- **Imported by:** `chat_v7.py:1008`
- **Imported by:** `chat_v7.py:856`
- **Imported by:** `chat_v7.py:551`
- **Imported by:** `chat_v7.py:801`


### `memory_db.save_message`

- **Defined in:** `memory_db.py`
- **Imported by:** `server.py:928`


### `memory_db.search_memory_smart`

- **Defined in:** `memory_db.py`
- **Imported by:** `chat_v7.py:711`


### `memory_db.store_memory`

- **Defined in:** `memory_db.py`
- **Imported by:** `exec_policy.py:57`


### `memory_recall.find_relevant_memories`

- **Defined in:** `memory_recall.py`
- **Imported by:** `memory_prefetch.py:36`


### `mini_planner.classify_intent`

- **Defined in:** `mini_planner.py`
- **Imported by:** `chat_v7.py:52`
- **Imported by:** `server.py:9236`


### `mini_planner.decompose_compound`

- **Defined in:** `mini_planner.py`
- **Imported by:** `chat_v7.py:52`
- **Imported by:** `server.py:9236`


### `mini_planner.get_trace_stats`

- **Defined in:** `mini_planner.py`
- **Imported by:** `chat_v7.py:52`
- **Imported by:** `server.py:9236`


### `mini_planner.get_traces`

- **Defined in:** `mini_planner.py`
- **Imported by:** `server.py:9236`


### `mini_planner.save_trace`

- **Defined in:** `mini_planner.py`
- **Imported by:** `chat_v7.py:52`


### `modules.panel.register_panel_routes`

- **Defined in:** `modules/__init__.py`
- **Imported by:** `server.py:3229`


### `news_engine.CATEGORIES`

- **Defined in:** `news_engine.py`
- **Imported by:** `dashboard_api.py:1819`


### `news_engine.cleanup_old`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.format_digest_tg`

- **Defined in:** `news_engine.py`
- **Imported by:** `chat_v7.py:422`
- **Imported by:** `chat_v7.py:425`
- **Imported by:** `server.py:532`


### `news_engine.format_sources_tg`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.generate_digest`

- **Defined in:** `news_engine.py`
- **Imported by:** `chat_v7.py:425`
- **Imported by:** `server.py:532`


### `news_engine.get_counts`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.get_latest_digest`

- **Defined in:** `news_engine.py`
- **Imported by:** `chat_v7.py:422`
- **Imported by:** `chat_v7.py:425`
- **Imported by:** `dashboard_api.py:1819`
- **Imported by:** `server.py:532`


### `news_engine.get_morning_news_text`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`
- **Imported by:** `tg_morning_report.py:283`


### `news_engine.get_news`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.get_today_digests`

- **Defined in:** `news_engine.py`
- **Imported by:** `dashboard_api.py:1819`
- **Imported by:** `server.py:532`


### `news_engine.get_urgent_items`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.handle_news_latest`

- **Defined in:** `news_engine.py`
- **Imported by:** `quick_query.py:150`
- **Imported by:** `server.py:532`


### `news_engine.init_schema`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.last_boursa_refresh`

- **Defined in:** `news_engine.py`
- **Imported by:** `kairos.py:214`
- **Imported by:** `server.py:8102`
- **Imported by:** `server.py:8308`


### `news_engine.last_gemini_refresh`

- **Defined in:** `news_engine.py`
- **Imported by:** `kairos.py:214`
- **Imported by:** `server.py:8102`
- **Imported by:** `server.py:8308`


### `news_engine.refresh_boursa`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `news_engine.refresh_gemini`

- **Defined in:** `news_engine.py`
- **Imported by:** `server.py:532`


### `paper_trading.close_paper_trade`

- **Defined in:** `paper_trading.py`
- **Imported by:** `dashboard_api.py:2406`


### `paper_trading.get_paper_trading_stats`

- **Defined in:** `paper_trading.py`
- **Imported by:** `dashboard_api.py:2382`


### `paper_trading.open_paper_trade`

- **Defined in:** `paper_trading.py`
- **Imported by:** `dashboard_api.py:2394`


### `parallel_coordinator.ParallelCoordinator`

- **Defined in:** `parallel_coordinator.py`
- **Imported by:** `stock_analyzer.py:213`


### `plan_engine.add_plan`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.complete_plan`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.delete_plan`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.format_plans_list`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.get_due_plans`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.get_plan`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.get_stats`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.init`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.list_plans`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.pause_plan`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.record_run`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `plan_engine.resume_plan`

- **Defined in:** `plan_engine.py`
- **Imported by:** `server.py:189`


### `position_engine.PositionEngine`

- **Defined in:** `position_engine.py`
- **Imported by:** `dashboard_api.py:3302`
- **Imported by:** `dashboard_api.py:3350`


### `position_engine.VALID_DIRECTIONS`

- **Defined in:** `position_engine.py`
- **Imported by:** `journal_engine.py:217`
- **Imported by:** `journal_engine.py:427`


### `position_engine.init_position_schema`

- **Defined in:** `position_engine.py`
- **Imported by:** `dashboard_api.py:3302`
- **Imported by:** `journal_engine.py:102`


### `position_engine.run_daily_monitor`

- **Defined in:** `position_engine.py`
- **Imported by:** `dashboard_api.py:3333`
- **Imported by:** `kse_data_collector.py:570`


### `price_source.SOURCE_DELAY_MINUTES`

- **Defined in:** `price_source.py`
- **Imported by:** `dashboard_api.py:882`


### `price_source.YAHOO_TIMEOUT`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/backfill_daily_bars.py:32`
- **Imported by:** `_tools/bar_completeness_probe.py:26`
- **Imported by:** `_tools/intraday_refresh.py:43`


### `price_source._KSE_TRADING_WEEKDAYS`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/prove_guards.py:808`
- **Imported by:** `_tools/quick_check.py:284`
- **Imported by:** `_tools/run_witness.py:302`


### `price_source._SESSION_CLOSE_H`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/intraday_refresh.py:43`
- **Imported by:** `_tools/prove_guards.py:808`
- **Imported by:** `_tools/quick_check.py:284`


### `price_source._SESSION_OPEN_H`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/intraday_refresh.py:43`
- **Imported by:** `_tools/prove_guards.py:808`
- **Imported by:** `_tools/quick_check.py:284`


### `price_source._UA`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/backfill_daily_bars.py:32`
- **Imported by:** `_tools/bar_completeness_probe.py:26`


### `price_source._kse_local`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/intraday_refresh.py:43`
- **Imported by:** `_tools/prove_guards.py:808`
- **Imported by:** `_tools/quick_check.py:284`
- **Imported by:** `_tools/run_witness.py:302`


### `price_source._parse_as_of`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/run_witness.py:249`
- **Imported by:** `_tools/run_witness.py:294`


### `price_source._sessions_since`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/run_witness.py:249`
- **Imported by:** `_tools/run_witness.py:294`


### `price_source._yahoo_opener`

- **Defined in:** `price_source.py`
- **Imported by:** `_tools/backfill_daily_bars.py:32`
- **Imported by:** `_tools/bar_completeness_probe.py:26`


### `price_source.as_of_age_minutes`

- **Defined in:** `price_source.py`
- **Imported by:** `dashboard_api.py:926`
- **Imported by:** `dashboard_api.py:2329`


### `price_source.classify_data_state`

- **Defined in:** `price_source.py`
- **Imported by:** `dashboard_api.py:959`
- **Imported by:** `dashboard_api.py:806`
- **Imported by:** `dashboard_api.py:926`
- **Imported by:** `dashboard_api.py:2307`


### `price_source.combine`

- **Defined in:** `price_source.py`
- **Imported by:** `risk_engine.py:171`


### `price_source.get_price`

- **Defined in:** `price_source.py`
- **Imported by:** `journal_engine.py:329`


### `price_source.get_quote`

- **Defined in:** `price_source.py`
- **Imported by:** `risk_engine.py:171`


### `priority_engine._pe_get_extended_snapshot`

- **Defined in:** `priority_engine.py`
- **Imported by:** `dashboard_api.py:16`
- **Imported by:** `server.py:9391`


### `priority_engine._pe_get_radar_snapshot`

- **Defined in:** `priority_engine.py`
- **Imported by:** `dashboard_api.py:16`
- **Imported by:** `server.py:9391`


### `priority_engine.build_assistant_surface`

- **Defined in:** `priority_engine.py`
- **Imported by:** `dashboard_api.py:16`
- **Imported by:** `server.py:9391`


### `priority_engine.build_priority_engine`

- **Defined in:** `priority_engine.py`
- **Imported by:** `dashboard_api.py:16`
- **Imported by:** `server.py:9391`


### `priority_engine.set_inbox_cache_ref`

- **Defined in:** `priority_engine.py`
- **Imported by:** `server.py:9391`


### `proactive_suggestions.get_suggestion_stats`

- **Defined in:** `proactive_suggestions.py`
- **Imported by:** `server.py:456`


### `proactive_suggestions.proactive_loop`

- **Defined in:** `proactive_suggestions.py`
- **Imported by:** `server.py:456`


### `processing_cursor.ProcessingCursor`

- **Defined in:** `processing_cursor.py`
- **Imported by:** `auto_memory_extractor.py:19`
- **Imported by:** `news_engine.py:22`
- **Imported by:** `stock_radar.py:29`


### `quick_query._active_devices_count`

- **Defined in:** `quick_query.py`
- **Imported by:** `tg_report.py:41`


### `quick_query._covers_status`

- **Defined in:** `quick_query.py`
- **Imported by:** `server.py:5504`


### `quick_query._locks_status`

- **Defined in:** `quick_query.py`
- **Imported by:** `server.py:5530`


### `quick_query._media_status`

- **Defined in:** `quick_query.py`
- **Imported by:** `server.py:5540`


### `quick_query._weather`

- **Defined in:** `quick_query.py`
- **Imported by:** `server.py:5520`
- **Imported by:** `tg_report.py:31`


### `quick_query.quick_answer`

- **Defined in:** `quick_query.py`
- **Imported by:** `server.py:114`


### `relationships_engine.add_contact`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:394`


### `relationships_engine.add_note`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:394`


### `relationships_engine.add_occasion`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:394`


### `relationships_engine.build_contact_snapshot`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:389`
- **Imported by:** `server.py:505`


### `relationships_engine.find_contact`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:394`
- **Imported by:** `server.py:505`


### `relationships_engine.format_contacts_tg`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`


### `relationships_engine.format_person_tg`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:389`
- **Imported by:** `server.py:505`


### `relationships_engine.format_today_tg`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`


### `relationships_engine.format_upcoming_tg`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:408`
- **Imported by:** `server.py:505`


### `relationships_engine.get_morning_occasions_text`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`
- **Imported by:** `tg_morning_report.py:265`


### `relationships_engine.get_today_occasions`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`


### `relationships_engine.get_upcoming_occasions`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `chat_v7.py:408`
- **Imported by:** `server.py:505`


### `relationships_engine.handle_birthday_lookup`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `quick_query.py:289`


### `relationships_engine.handle_occasions_today`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `quick_query.py:272`


### `relationships_engine.handle_occasions_tomorrow`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `quick_query.py:272`


### `relationships_engine.handle_occasions_upcoming`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `quick_query.py:272`


### `relationships_engine.init_schema`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`


### `relationships_engine.list_contacts`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`


### `relationships_engine.seed_family_data`

- **Defined in:** `relationships_engine.py`
- **Imported by:** `server.py:505`


### `risk_engine.RiskEngine`

- **Defined in:** `risk_engine.py`
- **Imported by:** `_tools/intraday_refresh.py:74`
- **Imported by:** `golden_engine.py:943`
- **Imported by:** `signal_engine.py:187`


### `risk_engine._get_risk_config`

- **Defined in:** `risk_engine.py`
- **Imported by:** `dashboard_api.py:2077`
- **Imported by:** `dashboard_api.py:3121`
- **Imported by:** `equity_tracker.py:22`
- **Imported by:** `equity_tracker.py:84`
- **Imported by:** `paper_trading.py:164`


### `risk_engine.calculate_position_size`

- **Defined in:** `risk_engine.py`
- **Imported by:** `paper_trading.py:36`


### `risk_engine.check_can_open`

- **Defined in:** `risk_engine.py`
- **Imported by:** `signal_engine.py:125`


### `risk_engine.get_risk_status`

- **Defined in:** `risk_engine.py`
- **Imported by:** `dashboard_api.py:2428`


### `run_witness.send_telegram`

- **Defined in:** `_tools/run_witness.py`
- **Imported by:** `signal_review.py:693`


### `run_witness.telegram_credentials`

- **Defined in:** `_tools/run_witness.py`
- **Imported by:** `kse_data_collector.py:448`
- **Imported by:** `signal_review.py:644`


### `scanner_universe.get_market`

- **Defined in:** `scanner_universe.py`
- **Imported by:** `gemini_scanner.py:13`


### `scanner_universe.get_scanner_universe`

- **Defined in:** `scanner_universe.py`
- **Imported by:** `gemini_scanner.py:13`


### `sector_map.get_sector`

- **Defined in:** `sector_map.py`
- **Imported by:** `golden_engine.py:952`
- **Imported by:** `risk_engine.py:62`


### `self_check.save_session_summary`

- **Defined in:** `self_check.py`
- **Imported by:** `chat_v7.py:25`


### `self_check.save_tool_outcomes`

- **Defined in:** `self_check.py`
- **Imported by:** `chat_v7.py:25`


### `self_check.validate_answer`

- **Defined in:** `self_check.py`
- **Imported by:** `chat_v7.py:25`


### `service_health.ServiceHealthHub`

- **Defined in:** `service_health.py`
- **Imported by:** `server.py:629`


### `service_health.get_health_hub`

- **Defined in:** `service_health.py`
- **Imported by:** `stock_radar.py:1578`
- **Imported by:** `stock_radar.py:950`
- **Imported by:** `stock_radar.py:989`
- **Imported by:** `stock_radar.py:1017`


### `service_health.set_health_hub`

- **Defined in:** `service_health.py`
- **Imported by:** `server.py:641`


### `session_memory.SessionTracker`

- **Defined in:** `session_memory.py`
- **Imported by:** `server.py:7541`


### `signal_engine.BLACKLIST`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.DAILY_TREND_FILTER`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.LIQUIDITY_FILTER`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.MARKET_REGIME_FILTER`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.SCALPING_MODE`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2441`


### `signal_engine.SWING_MODE`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.WHITELIST`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.WHITELIST_MODE`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine._name_ar`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2247`
- **Imported by:** `dashboard_api.py:2192`


### `signal_engine.build_signals`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:1974`
- **Imported by:** `dashboard_api.py:1985`
- **Imported by:** `dashboard_api.py:2134`
- **Imported by:** `dashboard_api.py:1088`
- **Imported by:** `server.py:3628`
- **Imported by:** `server.py:6427`
- **Imported by:** `trading_brain.py:164`


### `signal_engine.build_signals_30m`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2122`
- **Imported by:** `dashboard_api.py:2441`
- **Imported by:** `server.py:3621`
- **Imported by:** `server.py:6420`


### `signal_engine.calculate_scalping_stop`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2441`


### `signal_engine.check_market_regime`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.check_scalping_exit`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`
- **Imported by:** `dashboard_api.py:2441`


### `signal_engine.get_trading_flags`

- **Defined in:** `signal_engine.py`
- **Imported by:** `dashboard_api.py:2134`


### `signal_engine.init_signal_context`

- **Defined in:** `signal_engine.py`
- **Imported by:** `server.py:2919`


### `signal_review._send_review_telegram`

- **Defined in:** `signal_review.py`
- **Imported by:** `_tools/daily_signal_review.py:29`


### `signal_review.get_reviews_for_dashboard`

- **Defined in:** `signal_review.py`
- **Imported by:** `server.py:254`
- **Imported by:** `server.py:6465`


### `signal_review.init_review_schema`

- **Defined in:** `signal_review.py`
- **Imported by:** `server.py:254`


### `signal_review.review_all_pending`

- **Defined in:** `signal_review.py`
- **Imported by:** `_tools/daily_signal_review.py:29`
- **Imported by:** `server.py:3680`


### `signal_review.review_scheduler`

- **Defined in:** `signal_review.py`
- **Imported by:** `server.py:254`


### `signal_review.review_signals`

- **Defined in:** `signal_review.py`
- **Imported by:** `server.py:254`


### `skill_loader.SkillLoader`

- **Defined in:** `skill_loader.py`
- **Imported by:** `_tools/full_audit.py:203`
- **Imported by:** `dashboard_api.py:3675`


### `smart_router.classify_message`

- **Defined in:** `smart_router.py`
- **Imported by:** `server.py:99`


### `smart_tools.enrich_ha_state`

- **Defined in:** `smart_tools.py`
- **Imported by:** `chat_v7.py:59`


### `smart_tools.enrich_shift_result`

- **Defined in:** `smart_tools.py`
- **Imported by:** `chat_v7.py:59`


### `smart_tools.summarize_tool_result`

- **Defined in:** `smart_tools.py`
- **Imported by:** `chat_v7.py:59`


### `sr_engine.compute_sr`

- **Defined in:** `sr_engine.py`
- **Imported by:** `dashboard_api.py:1064`


### `sr_engine.refresh_sr_for_all`

- **Defined in:** `sr_engine.py`
- **Imported by:** `stock_radar.py:1571`


### `stock_alerts.get_alerts`

- **Defined in:** `stock_alerts.py`
- **Imported by:** `server.py:4691`


### `stock_alerts.get_portfolio`

- **Defined in:** `stock_alerts.py`
- **Imported by:** `server.py:4682`


### `stock_analyzer.analyze_stock`

- **Defined in:** `stock_analyzer.py`
- **Imported by:** `gemini_scanner.py:462`
- **Imported by:** `server.py:8124`


### `stock_analyzer.get_all_cached_analyses`

- **Defined in:** `stock_analyzer.py`
- **Imported by:** `dashboard_api.py:2022`


### `stock_analyzer.refresh_all_analyses_parallel`

- **Defined in:** `stock_analyzer.py`
- **Imported by:** `server.py:2688`


### `stock_personality_engine.get_all_profiles_summary`

- **Defined in:** `stock_personality_engine.py`
- **Imported by:** `server.py:3662`


### `stock_personality_engine.get_symbol_personality`

- **Defined in:** `stock_personality_engine.py`
- **Imported by:** `server.py:3656`


### `stock_radar.WATCHLIST`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/fractal_backtest.py:24`
- **Imported by:** `_tools/fractal_backtest_v2.py:34`
- **Imported by:** `_tools/fractal_backtest_v4.py:42`


### `stock_radar._db`

- **Defined in:** `stock_radar.py`
- **Imported by:** `trading_brain.py:360`


### `stock_radar._get_config`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/radar_diag.py:18`
- **Imported by:** `_tools/test_radar.py:9`
- **Imported by:** `dashboard_api.py:213`
- **Imported by:** `dashboard_api.py:457`
- **Imported by:** `priority_engine.py:83`


### `stock_radar.check_symbol`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/test_radar.py:9`
- **Imported by:** `_tools/test_radar_venv.py:42`
- **Imported by:** `tradingview_bridge.py:398`


### `stock_radar.get_daily_snapshot`

- **Defined in:** `stock_radar.py`
- **Imported by:** `dashboard_api.py:2568`
- **Imported by:** `dashboard_api.py:213`
- **Imported by:** `dashboard_api.py:457`
- **Imported by:** `dashboard_api.py:1341`
- **Imported by:** `gemini_scanner.py:194`
- **Imported by:** `priority_engine.py:83`


### `stock_radar.get_radar_snapshot`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:3043`


### `stock_radar.get_recent_events`

- **Defined in:** `stock_radar.py`
- **Imported by:** `dashboard_api.py:213`
- **Imported by:** `dashboard_api.py:457`
- **Imported by:** `priority_engine.py:83`


### `stock_radar.get_watchlist`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/test_radar.py:9`
- **Imported by:** `brain_backfill.py:291`
- **Imported by:** `brain_backfill.py:426`
- **Imported by:** `dashboard_api.py:213`
- **Imported by:** `dashboard_api.py:457`
- **Imported by:** `dashboard_api.py:1933`
- **Imported by:** `dashboard_api.py:3373`
- **Imported by:** `kse_data_collector.py:115`
- **Imported by:** `priority_engine.py:83`
- **Imported by:** `server.py:3891`
- **Imported by:** `server.py:3043`
- **Imported by:** `signal_engine.py:1602`
- **Imported by:** `signal_engine.py:1349`
- **Imported by:** `signal_engine.py:1412`


### `stock_radar.init_radar_db`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/test_radar.py:9`
- **Imported by:** `server.py:493`


### `stock_radar.radar_loop`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/test_radar.py:9`
- **Imported by:** `_tools/test_radar_task.py:13`
- **Imported by:** `server.py:493`


### `stock_radar.refresh_daily_snapshot`

- **Defined in:** `stock_radar.py`
- **Imported by:** `_tools/run_daily_refresh.py:64`
- **Imported by:** `_tools/run_refresh_check.py:5`
- **Imported by:** `_tools/trigger_refresh.py:7`
- **Imported by:** `_tools/verify_sunday.py:135`
- **Imported by:** `_tools/verify_sunday.py:146`
- **Imported by:** `kse_data_collector.py:274`
- **Imported by:** `server.py:3146`


### `stock_radar.tg_radar_add`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_check`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_last`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_list`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_remove`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_status`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_toggle`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `stock_radar.tg_radar_top`

- **Defined in:** `stock_radar.py`
- **Imported by:** `server.py:493`


### `system_guardian.check_all`

- **Defined in:** `system_guardian.py`
- **Imported by:** `tg_alerts.py:223`


### `system_guardian.get_status`

- **Defined in:** `system_guardian.py`
- **Imported by:** `quick_query.py:438`
- **Imported by:** `server.py:6769`


### `task_engine.CATEGORY_LABEL`

- **Defined in:** `task_engine.py`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.PRIORITY_LABEL`

- **Defined in:** `task_engine.py`
- **Imported by:** `server.py:6188`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.PRIORITY_MAP`

- **Defined in:** `task_engine.py`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.STATUS_LABEL`

- **Defined in:** `task_engine.py`
- **Imported by:** `server.py:6188`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.format_task_list`

- **Defined in:** `task_engine.py`
- **Imported by:** `server.py:6188`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.format_tasks_summary`

- **Defined in:** `task_engine.py`
- **Imported by:** `server.py:8856`
- **Imported by:** `server.py:8969`
- **Imported by:** `tg_morning_report.py:246`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.quick_tasks_active`

- **Defined in:** `task_engine.py`
- **Imported by:** `quick_query.py:337`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.quick_tasks_overdue`

- **Defined in:** `task_engine.py`
- **Imported by:** `quick_query.py:351`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.quick_tasks_today`

- **Defined in:** `task_engine.py`
- **Imported by:** `quick_query.py:344`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_create`

- **Defined in:** `task_engine.py`
- **Imported by:** `inbox_engine.py:183`
- **Imported by:** `inbox_engine.py:210`
- **Imported by:** `quick_query.py:394`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_delete`

- **Defined in:** `task_engine.py`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_done`

- **Defined in:** `task_engine.py`
- **Imported by:** `quick_query.py:375`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_get`

- **Defined in:** `task_engine.py`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_list`

- **Defined in:** `task_engine.py`
- **Imported by:** `inbox_engine.py:183`
- **Imported by:** `inbox_engine.py:210`
- **Imported by:** `proactive_suggestions.py:174`
- **Imported by:** `quick_query.py:300`
- **Imported by:** `server.py:6055`
- **Imported by:** `server.py:6130`
- **Imported by:** `server.py:6188`
- **Imported by:** `server.py:6805`
- **Imported by:** `server.py:6834`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_search`

- **Defined in:** `task_engine.py`
- **Imported by:** `quick_query.py:375`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_stats`

- **Defined in:** `task_engine.py`
- **Imported by:** `quick_query.py:300`
- **Imported by:** `server.py:5436`
- **Imported by:** `server.py:6055`
- **Imported by:** `server.py:6130`
- **Imported by:** `server.py:6188`
- **Imported by:** `server.py:6805`
- **Imported by:** `tg_tasks.py:3`


### `task_engine.task_update`

- **Defined in:** `task_engine.py`
- **Imported by:** `tg_tasks.py:3`


### `task_manager.TaskManager`

- **Defined in:** `task_manager.py`
- **Imported by:** `server.py:8232`
- **Imported by:** `server.py:8321`
- **Imported by:** `server.py:8343`


### `task_manager.TaskType`

- **Defined in:** `task_manager.py`
- **Imported by:** `server.py:8321`
- **Imported by:** `server.py:8343`


### `tasks_db.get_knowledge`

- **Defined in:** `tasks_db.py`
- **Imported by:** `memory_db.py:105`


### `tasks_db.get_latest_session`

- **Defined in:** `tasks_db.py`
- **Imported by:** `memory_db.py:105`


### `tasks_db.get_summary`

- **Defined in:** `tasks_db.py`
- **Imported by:** `memory_db.py:105`


### `tg_alerts.alert_loop`

- **Defined in:** `tg_alerts.py`
- **Imported by:** `server.py:455`


### `tg_email.format_email_report`

- **Defined in:** `tg_email.py`
- **Imported by:** `server.py:152`
- **Imported by:** `tg_intent_router.py:307`


### `tg_email.get_email_for_morning`

- **Defined in:** `tg_email.py`
- **Imported by:** `server.py:152`
- **Imported by:** `tg_morning_report.py:237`


### `tg_email.get_gmail_summary`

- **Defined in:** `tg_email.py`
- **Imported by:** `inbox_engine.py:48`
- **Imported by:** `priority_engine.py:67`


### `tg_email.get_outlook_summary`

- **Defined in:** `tg_email.py`
- **Imported by:** `inbox_engine.py:48`


### `tg_home.cmd_devices`

- **Defined in:** `tg_home.py`
- **Imported by:** `server.py:66`


### `tg_home.cmd_find`

- **Defined in:** `tg_home.py`
- **Imported by:** `server.py:66`


### `tg_home.cmd_rooms`

- **Defined in:** `tg_home.py`
- **Imported by:** `server.py:66`


### `tg_home.cmd_scenes_dynamic`

- **Defined in:** `tg_home.py`
- **Imported by:** `server.py:66`


### `tg_home.find_buttons`

- **Defined in:** `tg_home.py`
- **Imported by:** `server.py:66`


### `tg_home.handle_devctl`

- **Defined in:** `tg_home.py`
- **Imported by:** `server.py:66`


### `tg_intent_router.get_alias_stats`

- **Defined in:** `tg_intent_router.py`
- **Imported by:** `server.py:82`


### `tg_intent_router.learn_alias`

- **Defined in:** `tg_intent_router.py`
- **Imported by:** `server.py:82`


### `tg_intent_router.route_intent`

- **Defined in:** `tg_intent_router.py`
- **Imported by:** `server.py:82`


### `tg_morning_report.build_morning_report`

- **Defined in:** `tg_morning_report.py`
- **Imported by:** `server.py:212`


### `tg_morning_report.send_morning_report`

- **Defined in:** `tg_morning_report.py`
- **Imported by:** `server.py:212`


### `tg_news.get_news_digest`

- **Defined in:** `tg_news.py`
- **Imported by:** `server.py:470`


### `tg_news.news_scheduler`

- **Defined in:** `tg_news.py`
- **Imported by:** `server.py:470`


### `tg_ops.format_approval_buttons`

- **Defined in:** `tg_ops.py`
- **Imported by:** `server.py:59`


### `tg_ops.get_admin_chat_id`

- **Defined in:** `tg_ops.py`
- **Imported by:** `server.py:59`


### `tg_ops.get_pending_approvals`

- **Defined in:** `tg_ops.py`
- **Imported by:** `server.py:59`


### `tg_ops.is_tg_admin`

- **Defined in:** `tg_ops.py`
- **Imported by:** `server.py:59`


### `tg_ops.process_approval`

- **Defined in:** `tg_ops.py`
- **Imported by:** `server.py:59`


### `tg_ops.run_backup`

- **Defined in:** `tg_ops.py`
- **Imported by:** `server.py:59`


### `tg_reminders.add_reminder`

- **Defined in:** `tg_reminders.py`
- **Imported by:** `server.py:463`


### `tg_reminders.cancel_reminder`

- **Defined in:** `tg_reminders.py`
- **Imported by:** `server.py:463`


### `tg_reminders.list_reminders`

- **Defined in:** `tg_reminders.py`
- **Imported by:** `server.py:463`


### `tg_reminders.reminder_loop`

- **Defined in:** `tg_reminders.py`
- **Imported by:** `server.py:463`


### `tg_report.generate_daily_report`

- **Defined in:** `tg_report.py`
- **Imported by:** `server.py:121`


### `tg_session.detect_followup`

- **Defined in:** `tg_session.py`
- **Imported by:** `server.py:73`
- **Imported by:** `server.py:7134`
- **Imported by:** `server.py:7148`


### `tg_session.tg_session_append_context`

- **Defined in:** `tg_session.py`
- **Imported by:** `server.py:73`


### `tg_session.tg_session_get`

- **Defined in:** `tg_session.py`
- **Imported by:** `server.py:73`


### `tg_session.tg_session_get_compacted`

- **Defined in:** `tg_session.py`
- **Imported by:** `server.py:73`


### `tg_session.tg_session_reset`

- **Defined in:** `tg_session.py`
- **Imported by:** `server.py:73`


### `tg_session.tg_session_upsert`

- **Defined in:** `tg_session.py`
- **Imported by:** `server.py:73`


### `tg_session_resolver.resolve_followup_action`

- **Defined in:** `tg_session_resolver.py`
- **Imported by:** `server.py:74`


### `tg_stocks.cmd_price`

- **Defined in:** `tg_stocks.py`
- **Imported by:** `server.py:487`


### `tg_stocks.cmd_stocks`

- **Defined in:** `tg_stocks.py`
- **Imported by:** `server.py:487`


### `tg_suggestions.get_suggestions`

- **Defined in:** `tg_suggestions.py`
- **Imported by:** `server.py:173`


### `tg_tasks._parse_category`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `quick_query.py:395`


### `tg_tasks._parse_due_date`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `quick_query.py:395`


### `tg_tasks._parse_priority`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `quick_query.py:395`


### `tg_tasks.handle_tasks_command`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `server.py:479`
- **Imported by:** `server.py:7029`


### `tg_tasks.llm_tool_task_create`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `chat_v7.py:382`
- **Imported by:** `server.py:479`


### `tg_tasks.llm_tool_task_list`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `chat_v7.py:379`


### `tg_tasks.llm_tool_task_update`

- **Defined in:** `tg_tasks.py`
- **Imported by:** `chat_v7.py:385`
- **Imported by:** `server.py:479`


### `tips_engine.TipsEngine`

- **Defined in:** `tips_engine.py`
- **Imported by:** `server.py:90`


### `tool_cache.cache_get`

- **Defined in:** `tool_cache.py`
- **Imported by:** `chat_v7.py:66`


### `tool_cache.cache_set`

- **Defined in:** `tool_cache.py`
- **Imported by:** `chat_v7.py:66`


### `tool_cache.cache_stats`

- **Defined in:** `tool_cache.py`
- **Imported by:** `chat_v7.py:66`


### `tool_cache.execute_tools_parallel`

- **Defined in:** `tool_cache.py`
- **Imported by:** `chat_v7.py:66`


### `tool_registry.ToolRegistry`

- **Defined in:** `tool_registry.py`
- **Imported by:** `server.py:632`


### `tool_summary.generate_summary`

- **Defined in:** `tool_summary.py`
- **Imported by:** `server.py:7680`


### `trading_brain.adjust_weights`

- **Defined in:** `trading_brain.py`
- **Imported by:** `brain_backfill.py:314`
- **Imported by:** `brain_backfill.py:444`


### `trading_brain.evaluate_pending_signals`

- **Defined in:** `trading_brain.py`
- **Imported by:** `server.py:2979`


### `trading_brain.format_weekly_tg`

- **Defined in:** `trading_brain.py`
- **Imported by:** `server.py:2979`


### `trading_brain.generate_weekly_report`

- **Defined in:** `trading_brain.py`
- **Imported by:** `server.py:2979`


### `trading_brain.get_adjusted_confluence`

- **Defined in:** `trading_brain.py`
- **Imported by:** `signal_engine.py:1272`


### `trading_brain.get_brain_stats`

- **Defined in:** `trading_brain.py`
- **Imported by:** `dashboard_api.py:2603`


### `trading_brain.get_indicator_weights`

- **Defined in:** `trading_brain.py`
- **Imported by:** `gemini_scanner.py:299`
- **Imported by:** `stock_radar.py:363`
- **Imported by:** `stock_radar.py:664`


### `trading_brain.get_optimal_thresholds`

- **Defined in:** `trading_brain.py`
- **Imported by:** `dashboard_api.py:2603`
- **Imported by:** `signal_engine.py:86`


### `trading_brain.init_brain_context`

- **Defined in:** `trading_brain.py`
- **Imported by:** `server.py:2963`


### `trading_brain.init_schema`

- **Defined in:** `trading_brain.py`
- **Imported by:** `server.py:2963`


### `trading_brain.snapshot_signals`

- **Defined in:** `trading_brain.py`
- **Imported by:** `server.py:2979`


### `trading_brain.update_indicator_performance`

- **Defined in:** `trading_brain.py`
- **Imported by:** `brain_backfill.py:314`
- **Imported by:** `brain_backfill.py:444`


### `trading_decision_engine.compute_entry_status`

- **Defined in:** `trading_decision_engine.py`
- **Imported by:** `golden_engine.py:717`


### `trading_engine.get_morning_trading_text`

- **Defined in:** `trading_engine.py`
- **Imported by:** `tg_morning_report.py:308`


### `trading_engine.handle_trade_log`

- **Defined in:** `trading_engine.py`
- **Imported by:** `server.py:590`


### `trading_engine.handle_trade_review`

- **Defined in:** `trading_engine.py`
- **Imported by:** `server.py:590`


### `trading_engine.handle_trades_list`

- **Defined in:** `trading_engine.py`
- **Imported by:** `server.py:590`


### `trading_engine.init_schema`

- **Defined in:** `trading_engine.py`
- **Imported by:** `server.py:590`


### `trading_engine.llm_tool_trade_journal`

- **Defined in:** `trading_engine.py`
- **Imported by:** `chat_v7.py:443`


### `trading_engine.llm_tool_trade_log`

- **Defined in:** `trading_engine.py`
- **Imported by:** `chat_v7.py:440`


### `trading_engine.quick_trade_stats`

- **Defined in:** `trading_engine.py`
- **Imported by:** `server.py:590`


### `trading_engine.quick_trades_recent`

- **Defined in:** `trading_engine.py`
- **Imported by:** `server.py:590`


### `tradingview_bridge.get_morning_tv_text`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `tg_morning_report.py:315`


### `tradingview_bridge.handle_tv_add`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_tv_last`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_tv_remove`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_tv_stats`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_tv_summary`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_tv_test`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_tv_watchlist`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.handle_webhook`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.init_tradingview_domain`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.llm_tool_tv_last_signal`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `chat_v7.py:454`


### `tradingview_bridge.llm_tool_tv_signal_summary`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `chat_v7.py:457`


### `tradingview_bridge.llm_tool_tv_watchlist_add`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `chat_v7.py:448`


### `tradingview_bridge.llm_tool_tv_watchlist_list`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `chat_v7.py:451`


### `tradingview_bridge.mark_telegram_sent`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.quick_tv_last`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.quick_tv_summary_today`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.quick_tv_watchlist`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.render_tv_alert_message`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tradingview_bridge.sync_tv_from_radar`

- **Defined in:** `tradingview_bridge.py`
- **Imported by:** `server.py:602`


### `tv_advisor.build_advisor_prompt`

- **Defined in:** `tv_advisor.py`
- **Imported by:** `chat_v7.py:477`


### `tv_advisor.format_advisor_response`

- **Defined in:** `tv_advisor.py`
- **Imported by:** `chat_v7.py:477`


### `tv_analysis.format_analysis_arabic`

- **Defined in:** `tv_analysis.py`
- **Imported by:** `chat_v7.py:467`
- **Imported by:** `chat_v7.py:476`
- **Imported by:** `quick_query.py:251`
- **Imported by:** `tv_advisor.py:62`


### `tv_analysis.full_analysis`

- **Defined in:** `tv_analysis.py`
- **Imported by:** `chat_v7.py:467`
- **Imported by:** `chat_v7.py:476`
- **Imported by:** `quick_query.py:251`


### `tv_data.KSE_STOCKS`

- **Defined in:** `tv_data.py`
- **Imported by:** `dashboard_api.py:458`
- **Imported by:** `dashboard_api.py:1342`
- **Imported by:** `priority_engine.py:84`
- **Imported by:** `server.py:3717`
- **Imported by:** `server.py:3767`
- **Imported by:** `server.py:3826`
- **Imported by:** `server.py:3892`
- **Imported by:** `signal_engine.py:352`
- **Imported by:** `stock_radar.py:208`
- **Imported by:** `stock_radar.py:252`
- **Imported by:** `stock_radar.py:585`
- **Imported by:** `stock_radar.py:811`
- **Imported by:** `stock_radar.py:1058`
- **Imported by:** `stock_radar.py:1091`
- **Imported by:** `stock_radar.py:1134`
- **Imported by:** `stock_radar.py:1242`
- **Imported by:** `stock_radar.py:1600`
- **Imported by:** `stock_radar.py:1190`
- **Imported by:** `stock_radar.py:962`


### `tv_data._get_tv`

- **Defined in:** `tv_data.py`
- **Imported by:** `_tools/radar_diag.py:40`


### `tv_data._is_market_open`

- **Defined in:** `tv_data.py`
- **Imported by:** `_tools/radar_diag.py:11`
- **Imported by:** `_tools/test_radar.py:25`
- **Imported by:** `_tools/verify_sunday.py:134`
- **Imported by:** `_tools/verify_sunday.py:145`
- **Imported by:** `_tools/verify_sunday.py:200`
- **Imported by:** `dashboard_api.py:214`
- **Imported by:** `priority_engine.py:84`
- **Imported by:** `signal_engine.py:1290`
- **Imported by:** `stock_radar.py:1174`
- **Imported by:** `stock_radar.py:1279`
- **Imported by:** `stock_radar.py:939`


### `tv_data._normalize_price_to_fils`

- **Defined in:** `tv_data.py`
- **Imported by:** `dashboard_api.py:1218`
- **Imported by:** `dashboard_api.py:719`
- **Imported by:** `server.py:3571`
- **Imported by:** `server.py:2857`
- **Imported by:** `tg_stocks.py:109`
- **Imported by:** `tradingview_bridge.py:304`


### `tv_data.format_top_volume_arabic`

- **Defined in:** `tv_data.py`
- **Imported by:** `chat_v7.py:498`
- **Imported by:** `quick_query.py:198`


### `tv_data.get_price`

- **Defined in:** `tv_data.py`
- **Imported by:** `chat_v7.py:462`
- **Imported by:** `chat_v7.py:466`
- **Imported by:** `chat_v7.py:475`
- **Imported by:** `quick_query.py:250`


### `tv_data.get_top_volume`

- **Defined in:** `tv_data.py`
- **Imported by:** `chat_v7.py:498`
- **Imported by:** `quick_query.py:198`


### `tv_data.resolve_symbol`

- **Defined in:** `tv_data.py`
- **Imported by:** `_tools/radar_diag.py:40`
- **Imported by:** `dashboard_api.py:1218`
- **Imported by:** `dashboard_api.py:719`
- **Imported by:** `server.py:2857`
- **Imported by:** `stock_radar.py:208`
- **Imported by:** `stock_radar.py:225`
- **Imported by:** `stock_radar.py:794`
- **Imported by:** `stock_radar.py:811`
- **Imported by:** `stock_radar.py:1134`
- **Imported by:** `tg_stocks.py:109`


### `world_state.get_snapshot_data`

- **Defined in:** `world_state.py`
- **Imported by:** `server.py:136`


### `world_state.get_snapshot_text`

- **Defined in:** `world_state.py`
- **Imported by:** `chat_v7.py:662`
- **Imported by:** `server.py:136`


### `world_state.get_status`

- **Defined in:** `world_state.py`
- **Imported by:** `server.py:136`


### `world_state.start_world_state`

- **Defined in:** `world_state.py`
- **Imported by:** `server.py:136`


### `world_state_delta._get_db`

- **Defined in:** `world_state_delta.py`
- **Imported by:** `quick_query.py:446`
- **Imported by:** `server.py:6776`


### `world_state_delta._last_event`

- **Defined in:** `world_state_delta.py`
- **Imported by:** `quick_query.py:446`
- **Imported by:** `server.py:6776`


### `world_state_delta.build_delta`

- **Defined in:** `world_state_delta.py`
- **Imported by:** `world_state.py:266`


### `world_state_delta.get_delta_text`

- **Defined in:** `world_state_delta.py`
- **Imported by:** `chat_v7.py:664`


### `yahoo_gate.circuit_state`

- **Defined in:** `yahoo_gate.py`
- **Imported by:** `_tools/quick_check.py:403`
- **Imported by:** `dashboard_api.py:134`
- **Imported by:** `dashboard_api.py:887`


## Zero-consumer summary (retire-safely candidates)

> If this list seems too short, check the dynamic requests section and the excluded directories — that is where scanner blind spots surface first.


### Endpoints with no detected consumers


**`/action/execute`**
  - `server.py:4908` handler=`action_execute_endpoint`

**`/agent`**
  - `server.py:4191` handler=`agent_endpoint`

**`/aliases`**
  - `server.py:8437` handler=`aliases_endpoint`

**`/anomalies`**
  - `server.py:4058` handler=`get_anomalies_ep`
  - `server.py:9285` handler=`anomalies_endpoint`

**`/api/analyze`**
  - `server.py:8115` handler=`api_analyze`

**`/api/analyze/refresh`**
  - `server.py:8142` handler=`api_analyze_refresh`

**`/api/analyze/refresh-all`**
  - `server.py:8148` handler=`api_analyze_refresh_all`

**`/api/collect-now`**
  - `dashboard_api.py:3260` handler=`api_collect_now`

**`/api/data-freshness`**
  - `dashboard_api.py:3164` handler=`api_data_freshness`

**`/api/data-health`**
  - `dashboard_api.py:3153` handler=`api_data_health`

**`/api/decisions-now`**
  - `server.py:3615` handler=`api_decisions_now`

**`/api/flags/{name}/toggle`**
  - `server.py:8075` handler=`toggle_feature_flag`

**`/api/hooks/log`**
  - `server.py:8280` handler=`get_hooks_log`

**`/api/hooks/stats`**
  - `server.py:8276` handler=`get_hooks_stats`

**`/api/kairos/log`**
  - `server.py:8269` handler=`get_kairos_log`

**`/api/news`**
  - `server.py:8300` handler=`api_news`

**`/api/news/refresh-boursa`**
  - `server.py:8314` handler=`api_news_refresh_boursa`

**`/api/news/refresh-gemini`**
  - `server.py:8337` handler=`api_news_refresh_gemini`

**`/api/paper-trade/close`**
  - `dashboard_api.py:2400` handler=`api_paper_trade_close`

**`/api/paper-trade/open`**
  - `dashboard_api.py:2388` handler=`api_paper_trade_open`

**`/api/portfolio-alert-ack`**
  - `dashboard_api.py:3341` handler=`api_portfolio_alert_ack`

**`/api/portfolio-monitor`**
  - `dashboard_api.py:3328` handler=`api_portfolio_monitor`

**`/api/portfolio-status`**
  - `dashboard_api.py:3298` handler=`api_portfolio_status`

**`/api/portfolio/transactions/{trade_id}`**
  - `server.py:8216` handler=`api_trade_transactions`

**`/api/radar/progress`**
  - `dashboard_api.py:3632` handler=`api_radar_progress`

**`/api/refresh-analysis`**
  - `server.py:8163` handler=`api_refresh_analysis`

**`/api/review-now`**
  - `server.py:3673` handler=`manual_review`

**`/api/skills`**
  - `dashboard_api.py:3671` handler=`api_skills`

**`/api/stocks/symbol/{symbol}`**
  - `server.py:3653` handler=`get_stock_personality`

**`/api/tools`**
  - `server.py:8284` handler=`get_tools`

**`/api/tools/{name}`**
  - `server.py:8290` handler=`get_tool_detail`

**`/approvals/pending`**
  - `server.py:4340` handler=`list_pending_approvals`

**`/approve/{approval_id}`**
  - `server.py:4292` handler=`approve_action`

**`/ask`**
  - `server.py:4075` handler=`ask`

**`/audit`**
  - `server.py:4841` handler=`get_audit`

**`/brain/analytics`**
  - `server.py:3296` handler=`analytics_endpoint`

**`/brain/diag`**
  - `server.py:3316` handler=`brain_diag_endpoint`

**`/brain/expertise`**
  - `server.py:5163` handler=`brain_expertise`

**`/brain/feedback`**
  - `server.py:3308` handler=`feedback_endpoint`

**`/brain/stats`**
  - `server.py:3251` handler=`brain_stats_endpoint`

**`/brain/users`**
  - `server.py:3302` handler=`users_endpoint`

**`/bridge/status`**
  - `server.py:3109` handler=`bridge_circuit_status`

**`/calendar/stats`**
  - `server.py:3513` handler=`calendar_stats_endpoint`

**`/calendar/sync`**
  - `server.py:3523` handler=`calendar_sync_endpoint`

**`/chat/clear`**
  - `server.py:8365` handler=`clear_chat_history`

**`/classify`**
  - `server.py:9250` handler=`classify_msg`

**`/claude`**
  - `server.py:4496` handler=`claude_context`

**`/corrections`**
  - `server.py:9214` handler=`get_corrections_stats`

**`/corrections/decay`**
  - `server.py:9223` handler=`decay_corrections_endpoint`

**`/cost`**
  - `server.py:9297` handler=`cost_dashboard`

**`/daily-snapshot/refresh`**
  - `server.py:3127` handler=`refresh_daily_snapshot_manual`

**`/dashboard/brain`**
  - `dashboard_api.py:2599` handler=`dashboard_brain`

**`/dashboard/bridge`**
  - `dashboard_api.py:1879` handler=`dashboard_bridge`

**`/dashboard/bridge/{symbol}`**
  - `dashboard_api.py:1903` handler=`dashboard_bridge_symbol`

**`/dashboard/ema-active`**
  - `server.py:3798` handler=`dashboard_ema_active`

**`/dashboard/ema-crosses`**
  - `server.py:3686` handler=`dashboard_ema_crosses`

**`/dashboard/ema-live`**
  - `server.py:3880` handler=`dashboard_ema_live`

**`/dashboard/ema-proximity`**
  - `server.py:3753` handler=`dashboard_ema_proximity`

**`/dashboard/jobs`**
  - `dashboard_api.py:431` handler=`dashboard_jobs_list`

**`/dashboard/paper-trading`**
  - `dashboard_api.py:2378` handler=`dashboard_paper_trading`

**`/dashboard/regime`**
  - `dashboard_api.py:2565` handler=`dashboard_regime`

**`/dashboard/reviews`**
  - `server.py:3666` handler=`dashboard_reviews`

**`/dashboard/scalper`**
  - `dashboard_api.py:2434` handler=`dashboard_scalper`

**`/dashboard/strategies`**
  - `dashboard_api.py:2940` handler=`dashboard_strategies`

**`/debug/test_approval`**
  - `server.py:3346` handler=`debug_test_approval`

**`/decompose`**
  - `server.py:9255` handler=`decompose_msg`

**`/deploy`**
  - `server.py:4707` handler=`deploy_file`

**`/dev/context`**
  - `server.py:5181` handler=`dev_context`

**`/dream/run`**
  - `server.py:3280` handler=`dream_run_endpoint`

**`/dream/status`**
  - `server.py:3271` handler=`dream_status_endpoint`

**`/entity-map/arabize`**
  - `server.py:8498` handler=`entity_map_arabize`

**`/entity-map/health`**
  - `server.py:8485` handler=`entity_map_health`

**`/event`**
  - `server.py:4937` handler=`ingest_event`

**`/event_rules`**
  - `server.py:4985` handler=`get_event_rules`

**`/events`**
  - `server.py:4974` handler=`list_events_ep`

**`/events/{event_id}`**
  - `server.py:4978` handler=`get_event_ep`

**`/feedback/digest`**
  - `server.py:9274` handler=`feedback_digest_endpoint`

**`/feedback/stats`**
  - `server.py:9266` handler=`feedback_stats_endpoint`

**`/gmail/auth`**
  - `server.py:3362` handler=`gmail_auth_start`

**`/gmail/callback`**
  - `server.py:3397` handler=`gmail_auth_callback`

**`/google/auth`**
  - `server.py:3453` handler=`google_auth_start`

**`/google/auth/status`**
  - `server.py:3503` handler=`google_auth_status`

**`/google/callback`**
  - `server.py:3471` handler=`google_auth_callback`

**`/ha/service`**
  - `server.py:4256` handler=`ha_call_service_ep`

**`/ha/states`**
  - `server.py:4265` handler=`ha_get_states`

**`/ha/states/{entity_id:path}`**
  - `server.py:4270` handler=`ha_get_state`

**`/health`**
  - `server.py:3973` handler=`health`

**`/health/external`**
  - `server.py:8046` handler=`health_external`

**`/health/external/test`**
  - `server.py:8404` handler=`health_external_test`

**`/history/{entity_id:path}`**
  - `server.py:3993` handler=`entity_history_endpoint`

**`/knowledge`**
  - `server.py:4603` handler=`list_knowledge`
  - `server.py:4626` handler=`create_knowledge`

**`/knowledge/{kid}`**
  - `server.py:4617` handler=`get_knowledge`
  - `server.py:4637` handler=`update_knowledge`
  - `server.py:4649` handler=`delete_knowledge`

**`/kpi`**
  - `server.py:9308` handler=`kpi_dashboard`

**`/memory`**
  - `server.py:4747` handler=`create_memory_ep`
  - `server.py:4756` handler=`list_memories_ep`

**`/memory/message`**
  - `server.py:4798` handler=`save_msg`

**`/memory/recent`**
  - `server.py:4791` handler=`memory_recent`

**`/memory/stats`**
  - `server.py:4769` handler=`mem_stats`

**`/patterns`**
  - `server.py:4040` handler=`patterns_endpoint`

**`/patterns/learn`**
  - `server.py:4067` handler=`patterns_learn_endpoint`

**`/patterns/suggestions`**
  - `server.py:4051` handler=`patterns_suggestions_endpoint`

**`/plugins`**
  - `server.py:4902` handler=`list_plugins`

**`/plugins/{name}/disable`**
  - `server.py:4922` handler=`disable_plugin`

**`/plugins/{name}/enable`**
  - `server.py:4915` handler=`enable_plugin`

**`/router/stats`**
  - `server.py:8446` handler=`router_stats_endpoint`

**`/schema`**
  - `server.py:4867` handler=`schema_status`

**`/schema/ensure`**
  - `server.py:4887` handler=`schema_ensure`

**`/sessions`**
  - `server.py:4556` handler=`create_session`
  - `server.py:4568` handler=`list_sessions`

**`/sessions/latest`**
  - `server.py:4578` handler=`latest_session`

**`/shift`**
  - `server.py:4469` handler=`shift_info`

**`/ssh/run`**
  - `server.py:4283` handler=`ssh_run`

**`/stability`**
  - `server.py:8422` handler=`stability_endpoint`

**`/stats/capture`**
  - `server.py:4454` handler=`stats_capture`

**`/stats/daily`**
  - `server.py:4439` handler=`stats_daily`

**`/stocks/alerts`**
  - `server.py:4688` handler=`stock_alerts_history`

**`/stocks/portfolio`**
  - `server.py:4679` handler=`stock_portfolio`

**`/structured-memory`**
  - `server.py:9142` handler=`smem_stats`

**`/structured-memory/context`**
  - `server.py:9147` handler=`smem_context`

**`/structured-memory/correction`**
  - `server.py:9174` handler=`smem_save_correction`

**`/structured-memory/decay`**
  - `server.py:9203` handler=`smem_decay`

**`/structured-memory/event`**
  - `server.py:9163` handler=`smem_save_event`

**`/structured-memory/fact`**
  - `server.py:9152` handler=`smem_save_fact`

**`/structured-memory/migrate`**
  - `server.py:9193` handler=`smem_migrate`

**`/structured-memory/search`**
  - `server.py:9184` handler=`smem_search`

**`/structured-memory/seed`**
  - `server.py:9198` handler=`smem_seed`

**`/structured-memory/{memory_id}`**
  - `server.py:9209` handler=`smem_delete`

**`/system/backup`**
  - `server.py:3265` handler=`backup_endpoint`

**`/system/context`**
  - `server.py:5019` handler=`system_context`

**`/system/diag`**
  - `server.py:3258` handler=`system_diag_endpoint`

**`/system/knowledge`**
  - `server.py:5142` handler=`system_knowledge_endpoint`

**`/system/knowledge/summary`**
  - `server.py:5152` handler=`system_knowledge_summary`

**`/tasks`**
  - `server.py:4662` handler=`list_tasks_ep`

**`/tasks/{task_id}`**
  - `server.py:4667` handler=`get_task_ep`

**`/tg/stats`**
  - `server.py:8374` handler=`tg_stats`

**`/tips`**
  - `server.py:3289` handler=`tips_endpoint`

**`/tool-stats`**
  - `server.py:3545` handler=`tool_stats_endpoint`

**`/traces`**
  - `server.py:9242` handler=`traces_list`

**`/traces/stats`**
  - `server.py:9246` handler=`traces_stats`

**`/trading/{page}`**
  - `server.py:3156` handler=`serve_trading_page`

**`/tradingview/webhook`**
  - `server.py:3554` handler=`tradingview_webhook`

**`/users`**
  - `server.py:4812` handler=`create_user`
  - `server.py:4827` handler=`list_users`

**`/webhook/event`**
  - `server.py:5004` handler=`webhook_event`

**`/win/jobs`**
  - `server.py:4421` handler=`win_jobs`

**`/win/poll`**
  - `server.py:4398` handler=`win_poll`

**`/win/register`**
  - `server.py:4390` handler=`win_register`

**`/win/report`**
  - `server.py:4409` handler=`win_report`

**`/world-state`**
  - `server.py:3534` handler=`world_state_endpoint`


### Tables never read (write-only)

- `buy_now_shadow`
- `calendar_parse_log`
- `calendar_sources`
- `confidence_census`
- `confluence_decisions`
- `contact`
- `current`
- `cursor`
- `daily_digest`
- `dashboard`
- `deployments`
- `failed`
- `health_status`
- `home`
- `indicator`
- `last_monitored`
- `migration_log`
- `notes`
- `progress`
- `risk`
- `session_summaries`
- `stop`
- `suggestions`
- `target`
- `task`
- `task_categories`
- `time`
- `trade`
- `trades_new`
- `trailing`


### Tables never written (read-only)

- `__future__`
- `_tools`
- `action`
- `adhan_script_v3`
- `adx`
- `all`
- `anomaly_engine`
- `anomaly_log`
- `anthropic`
- `apply_text_patch`
- `approval_ux`
- `arabic`
- `audit`
- `auto_memory_extractor`
- `backup`
- `bar`
- `bars`
- `birthday`
- `brain`
- `brain_analytics`
- `brain_core`
- `brain_learning`
- `brain_multiuser`
- `brain_observability`
- `brain_personality`
- `brain_proactive`
- `bridge`
- `bridge_client`
- `calendar_db`
- `calendar_engine`
- `calendar_reporting`
- `chat_v7`
- `chatgpt`
- `circuit_breaker`
- `claude`
- `coalesced_executor`
- `collections`
- `complete`
- `confidence_engine`
- `configuration`
- `confluence_engine`
- `context`
- `context_compactor`
- `context_manager`
- `contextlib`
- `contract`
- `corrections_loop`
- `correlated`
- `cost_tracker`
- `cron`
- `csv`
- `dashboard_api`
- `data`
- `data_integrity`
- `dataclasses`
- `datetime`
- `db_backup`
- `degraded_mode`
- `discovered`
- `discovery`
- `disk`
- `domain_kpis`
- `dotenv`
- `dream_consolidator`
- `email`
- `entity`
- `entity_health`
- `entity_id`
- `entity_map`
- `entry`
- `entry_idx`
- `enum`
- `equity_snapshots`
- `equity_tracker`
- `errors`
- `exec_policy`
- `expenses_engine`
- `family_assistant`
- `fastapi`
- `feedback_learner`
- `fixed`
- `fresher`
- `gdrive`
- `gemini`
- `get_multi_analysis_30m`
- `gmail`
- `gmail_credentials`
- `golden_engine`
- `google`
- `google_auth_ext`
- `googleapiclient`
- `ha_doctor`
- `ha_history`
- `habit_engine`
- `health`
- `health_engine`
- `here`
- `hijridate`
- `historical`
- `home_brain`
- `hooks`
- `https`
- `inbox_engine`
- `indicators`
- `instead`
- `intent_state_machine`
- `itertools`
- `its`
- `journal_engine`
- `kairos`
- `keyword`
- `kse_data_collector`
- `kwse`
- `last`
- `learned`
- `life_expenses`
- `life_health`
- `life_router`
- `life_stocks`
- `life_work`
- `live`
- `llm`
- `logging`
- `master_ai`
- `master_ai_tool`
- `memory_db`
- `memory_recall`
- `mined_strategies`
- `mini_planner`
- `module`
- `modules`
- `multiple`
- `news_engine`
- `nightly`
- `nobody`
- `ohlc`
- `ohlcv`
- `old`
- `open`
- `openai`
- `our`
- `paper_trading`
- `parallel_coordinator`
- `past`
- `pathlib`
- `payload`
- `peak`
- `period`
- `plan_engine`
- `plugin`
- `position_engine`
- `pragma`
- `price`
- `price_source`
- `priority_engine`
- `proactive_suggestions`
- `processing_cursor`
- `profile`
- `project`
- `pydantic`
- `python`
- `queue`
- `quick_query`
- `radar`
- `radar_config`
- `radar_events`
- `raw`
- `recent`
- `relationships_engine`
- `response`
- `rest`
- `risk_engine`
- `rpi`
- `run_witness`
- `saved`
- `scan_opportunities`
- `scanner_universe`
- `scratch`
- `sector_map`
- `self_check`
- `server`
- `service_health`
- `session_memory`
- `signal`
- `signal_engine`
- `signal_outcomes`
- `signal_review`
- `skill_loader`
- `skills`
- `smart_router`
- `smart_tools`
- `sqlite_master`
- `sr_engine`
- `stale`
- `starlette`
- `start`
- `stock_alerts`
- `stock_analyzer`
- `stock_personality_engine`
- `stock_radar`
- `sub`
- `swing`
- `system_guardian`
- `task_engine`
- `task_manager`
- `tasks_db`
- `telegram`
- `template`
- `text`
- `tg_alerts`
- `tg_email`
- `tg_home`
- `tg_intent_router`
- `tg_morning_report`
- `tg_news`
- `tg_ops`
- `tg_reminders`
- `tg_report`
- `tg_session`
- `tg_session_resolver`
- `tg_stocks`
- `tg_suggestions`
- `tg_tasks`
- `this`
- `those`
- `tier1`
- `tips_engine`
- `today`
- `tool_cache`
- `tool_registry`
- `tool_summary`
- `top`
- `trading_brain`
- `trading_decision_engine`
- `trading_engine`
- `tradingview`
- `tradingview_bridge`
- `tv_advisor`
- `tv_analysis`
- `tv_data`
- `tvdatafeed`
- `typing`
- `universe`
- `unknown`
- `urllib`
- `user`
- `whatever`
- `windows`
- `world_state`
- `world_state_delta`
- `xml`
- `yahoo`
- `yahoo_gate`
- `yesterday`
- `zero`
