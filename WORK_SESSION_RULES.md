# Work Session Rules

1. One SSH command per message. Never chain with && or ; or pipe with |
2. Always check health BEFORE and AFTER any change
3. Use /deploy endpoint for file writes (small files only)
4. For server.py edits: locate line numbers first, edit minimal lines
5. After any .py edit: run py_compile before restart
6. If command output is large: use tail -N or head -N (no pipes)
7. Never paste large code blocks into SSH commands
8. If a step needs interactive terminal (nano): say Manual Step Required
9. Rollback plan always ready: bash scripts/rollback_last.sh
10. Push to git after every successful change: git add . then git commit then git push
