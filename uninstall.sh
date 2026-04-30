#!/bin/bash

echo "========================================="
echo "     NetPulse Uninstaller"
echo "========================================="

read -p "Remove NetPulse services? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

# Stop and disable services
sudo systemctl stop netpulse-api netpulse-web 2>/dev/null
sudo systemctl disable netpulse-api netpulse-web 2>/dev/null

# Remove service files
sudo rm -f /etc/systemd/system/netpulse-api.service
sudo rm -f /etc/systemd/system/netpulse-web.service
sudo systemctl daemon-reload

echo "✅ Services removed"

read -p "Remove backups? (yes/no): " RM_BACKUPS
if [ "$RM_BACKUPS" == "yes" ]; then
    rm -rf /home/kmtech/backups/netpulse
    echo "✅ Backups removed"
fi

echo "✅ Uninstall complete"
