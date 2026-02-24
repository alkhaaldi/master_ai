#!/bin/bash
# Cloudflare Quick Tunnel wrapper - captures URL and updates HA sensor
LOG=/var/log/cloudflared.log
URL_FILE=/home/pi/master_ai/tunnel_url.txt
HA_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDVlZWRkMzk0MjY0MDk2OTY0YThlNjYyZDU0NTYzYiIsImlhdCI6MTc3MTI1NDI4NywiZXhwIjoyMDg2NjE0Mjg3fQ.Ws_86k8u0abSGfBZMYxKVSxzO8r6kX2yyIXPicjyFd0"

# Start cloudflared and pipe output
cloudflared tunnel --url http://localhost:9000 2>&1 | while IFS= read -r line; do
    echo "$line" >> $LOG
    # Check if line contains the tunnel URL
    URL=$(echo "$line" | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com')
    if [ -n "$URL" ]; then
        echo "$URL" > $URL_FILE
        echo "$(date): Tunnel URL: $URL" >> $LOG
        
        # Update HA input_text entity with the URL
        curl -s -X POST http://localhost:8123/api/states/sensor.master_ai_tunnel_url \
            -H "Authorization: Bearer $HA_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"state\": \"$URL\", \"attributes\": {\"friendly_name\": \"Master AI Tunnel URL\", \"updated\": \"$(date -Iseconds)\"}}" > /dev/null 2>&1
    fi
done
