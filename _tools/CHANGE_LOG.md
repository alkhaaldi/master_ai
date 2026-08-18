# CHANGE LOG - one line per task run

Written by `_tools/run_task.sh`, not by hand. The detail lives in the report
named on each line; this file is only the index of what happened when.

A run cannot end without that report - `.claude/hooks/report_gate.sh` refuses
to let the session stop until it exists and carries all four headings:
what changed, who consumes it, what might break, what is left.

