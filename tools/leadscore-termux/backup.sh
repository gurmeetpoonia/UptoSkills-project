#!/data/data/com.termux/files/usr/bin/bash
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$APP_DIR/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
if [ -f "$APP_DIR/data/leads.db" ]; then
  cp "$APP_DIR/data/leads.db" "$APP_DIR/backups/leads-$STAMP.db"
  echo "Backup created: $APP_DIR/backups/leads-$STAMP.db"
else
  echo 'No database exists yet.'
fi
