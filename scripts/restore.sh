#!/bin/bash

BACKUP_DIR="/home/kmtech/backups/netpulse"
DB_PATH="/home/kmtech/Projects/NetPulse/network-monitor/data/monitor.db"

echo "========================================="
echo "     NetPulse Restore Utility"
echo "========================================="

if [ ! -d "$BACKUP_DIR" ]; then
    echo "❌ No backups found"
    exit 1
fi

echo -e "\nAvailable backups:"
ls -lh "$BACKUP_DIR"/monitor.db.* 2>/dev/null | tail -10

echo ""
read -p "Enter backup file to restore (or press Enter for latest): " BACKUP_FILE

if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/monitor.db.* 2>/dev/null | head -1)
    echo "Using latest backup: $(basename "$BACKUP_FILE")"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found"
    exit 1
fi

echo ""
read -p "Are you sure? This will overwrite current data! (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

# Stop services
sudo systemctl stop netpulse-api netpulse-web 2>/dev/null

# Restore
cp "$BACKUP_FILE" "$DB_PATH"
echo "✅ Database restored"

# Start services
sudo systemctl start netpulse-api netpulse-web 2>/dev/null

echo "✅ Restore complete!"
