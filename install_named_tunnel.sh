#!/bin/bash
# Install Named Cloudflare Tunnel
sudo systemctl stop cloudflared-tunnel
sudo systemctl disable cloudflared-tunnel

cat << 'SVCEOF' | sudo tee /etc/systemd/system/cloudflared-named.service
[Unit]
Description=Cloudflare Named Tunnel for Master AI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/cloudflared tunnel run --token eyJhIjoiOWMwNTMyNWYwYjg4ZjIxYzMzNzEzYzZiMzMwYTIzMmYiLCJ0IjoiYjMxYTNlMmItNmExYi00ZWVjLWI5NDItZDEzY2ZmZjFkOTlhIiwicyI6Ik5qYzNZakJqT1RBdE1USTFZaTAwWVRFNExXSTBOMlF0WldJMlltVmpaREJsTkRndyJ9
Restart=always
RestartSec=10
Environment=NO_AUTOUPDATE=true

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable cloudflared-named
sudo systemctl start cloudflared-named
sleep 3
sudo systemctl status cloudflared-named --no-pager
