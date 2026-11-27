#!/data/data/com.termux/files/usr/bin/bash
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"
mkdir -p data
printf '\nLeadScore Termux\nOpen http://127.0.0.1:5000 in your browser.\nPress Ctrl+C here to stop.\n\n'
exec python app.py --web --port 5000
