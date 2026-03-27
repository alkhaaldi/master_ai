#!/bin/bash
# Emergency revert - run this on RPi
cd /home/pi/master_ai
git checkout HEAD~1 -- server.py
echo "REVERTED server.py"
wc -l server.py
sudo systemctl restart master-ai.service
sleep 5
systemctl is-active master-ai.service
curl -s http://localhost:9000/health | head -1
echo "DONE"
