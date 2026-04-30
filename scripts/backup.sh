#!/bin/bash
# NetPulse Automated Backup Script

BACKUP_DIR="/home/kmtech/backups/netpulse"
DB_PATH="/home/kmtech/Projects/NetPulse/network-monitor/data/monitor.db"
ENV_PATH="/home/kmtech/Projects/NetPulse/network-monitor/.env"
DATE=$(date +%Y-%m-%d_%H-%M-%S)

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting NetPulse backup..."

# Backup database
if [ -f "$DB_PATH" ]; then
    cp "$DB_PATH" "$BACKUP_DIR/monitor.db.$DATE"
    echo "✅ Database backed up"
    
    # Keep backups for 30 days, compress older than 7
    find "$BACKUP_DIR" -name "monitor.db.*" -mtime +7 -exec gzip {} \;
    find "$BACKUP_DIR" -name "monitor.db.*.gz" -mtime +30 -delete
    find "$BACKUP_DIR" -name "monitor.db.*" -mtime +30 ! -name "*.gz" -delete
fi

# Backup .env file
if [ -f "$ENV_PATH" ]; then
    cp "$ENV_PATH" "$BACKUP_DIR/.env.$DATE"
    ls -t "$BACKUP_DIR"/.env.* 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
fi

echo "[$(date)] Backup completed"
