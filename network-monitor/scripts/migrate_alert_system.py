#!/usr/bin/env python3
"""Migrate database for new alert system"""

import sqlite3
import os
import sys

def migrate():
    db_path = "data/monitor.db"
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(devices)")
    columns = [col[1] for col in cursor.fetchall()]
    
    new_columns = ['down_since', 'last_down_alert_sent_at', 'last_recovery_alert_sent_at', 'last_erratic_alert_sent_at']
    
    for col in new_columns:
        if col not in columns:
            cursor.execute(f"ALTER TABLE devices ADD COLUMN {col} TIMESTAMP")
            print(f"✅ Added column: {col}")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ Created device_status_history table")
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_status_history_device 
        ON device_status_history(device_id, recorded_at)
    """)
    print("✅ Created index")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    migrate()
