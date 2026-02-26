# Master AI Deploy Checklist

## Pre-Deploy
- [ ] git status shows clean working tree
- [ ] git branch is main
- [ ] curl localhost:9000/health returns ok
- [ ] systemctl is-active master-ai returns active

## Deploy
- [ ] bash update.sh
- [ ] Watch output for errors

## Post-Deploy
- [ ] curl localhost:9000/health returns ok
- [ ] Check version field matches expected
- [ ] systemctl is-active master-ai returns active
- [ ] curl localhost:9000/system/context returns valid JSON
- [ ] Check server.log tail for errors

## If Failed
- [ ] bash scripts/rollback_last.sh
- [ ] Or: git checkout HEAD~1 -- server.py
- [ ] sudo systemctl restart master-ai
- [ ] Verify health again
