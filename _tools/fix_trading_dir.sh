#!/bin/bash
cd /var/lib/homeassistant/share/master_ai/www
mv trading trading_old
mkdir trading
cp trading_old/* trading/
chown -R pi:pi trading
chmod 755 trading
chmod 644 trading/*
ls -la trading/system.html
echo "RECREATED OK"
