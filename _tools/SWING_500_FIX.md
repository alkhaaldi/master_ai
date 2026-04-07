# CRITICAL BUG FIX: /dashboard/swing returns 500
# Error: "cannot access local variable 'sig' where it is not associated with a value"
# 
# The error is in signal_engine.py or dashboard_api.py
# A variable named 'sig' is used before being defined in all code paths.
#
# Find the exact location:
#   grep -n "sig " signal_engine.py | grep -v "signal\|assign\|design"
#
# Fix: ensure 'sig' is initialized before use in all branches
# 
# Claude Code command:
# > CRITICAL: /dashboard/swing returns 500 error "cannot access local variable 'sig'". 
# > Find where 'sig' is used without being defined and fix it. Test with curl.
