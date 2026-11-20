# One command starts the whole app for local development (Windows PowerShell):
#   .\start-dev.ps1
# It opens the scraper, backend and frontend in their own windows. The intelligent tool needs no
# window of its own: the scraper imports it directly (add -WithToolDashboard to also open its dashboard).
param([switch]$WithToolDashboard)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Start-Window($title, $dir, $cmd) {
    Start-Process powershell -ArgumentList '-NoExit', '-Command',
        "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location '$dir'; $cmd"
}

Start-Window 'SalesForge scraper :8000' "$root\scraper" 'python -m uvicorn main:app --port 8000'
Start-Window 'SalesForge backend'       "$root\backend" 'npm run dev'
Start-Window 'SalesForge frontend'      "$root\frontend" 'npm run dev'
if ($WithToolDashboard) {
    Start-Window 'LeadScore tool :5000' "$root\tools\leadscore-termux" 'python app.py --web'
}
Write-Host 'Started. Open http://localhost:5173  (Redis and Postgres must already be running).'
