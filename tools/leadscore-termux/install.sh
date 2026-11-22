#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_NAME="leadscore-termux"
TARGET="$HOME/$APP_NAME"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

printf '\n=== LeadScore Termux installer ===\n'
command -v pkg >/dev/null 2>&1 || { echo 'Run this script inside Termux.'; exit 1; }
pkg update -y
pkg install -y python
mkdir -p "$TARGET/data"
# Start with an empty workspace for the user's own data. Preserve any previous DB as a backup.
if [ -s "$TARGET/data/leads.db" ]; then
  BACKUP="$TARGET/data/leads-before-v1.5.0-$(date +%Y%m%d-%H%M%S).db"
  cp "$TARGET/data/leads.db" "$BACKUP"
  rm -f "$TARGET/data/leads.db" "$TARGET/data/leads.db-wal" "$TARGET/data/leads.db-shm"
  echo "Previous database backed up to: $BACKUP"
fi
# Copy application files, never copy or overwrite the existing database/logs.
for f in app.py start.sh test_suite.py README.md backup.sh VERSION.txt; do
  [ -f "$SOURCE_DIR/$f" ] && cp "$SOURCE_DIR/$f" "$TARGET/$f"
done
cp -n "$SOURCE_DIR/data/.keep" "$TARGET/data/.keep" 2>/dev/null || true
chmod +x "$TARGET/app.py" "$TARGET/start.sh" "$TARGET/test_suite.py" "$TARGET/backup.sh"

if command -v termux-setup-storage >/dev/null 2>&1; then
  echo 'Requesting shared-storage permission (needed only to pick files from Downloads).'
  termux-setup-storage || true
fi

echo 'Running offline regression tests...'
python "$TARGET/test_suite.py"
echo
echo "Installed at: $TARGET"
echo 'Start with: bash ~/leadscore-termux/start.sh'
echo 'Open: http://127.0.0.1:5000'
echo 'A fresh empty database is ready for your own imports.'
