FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install Python deps, then the Chromium build that matches the installed
# playwright version, plus the OS libraries Chromium needs.
# libatomic1: Playwright's node driver needs it (without it "playwright install" exits with code 127)
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Chromium is only the optional fallback when LinkedIn's guest API returns nothing, so never fail the build for it
RUN pip install --no-cache-dir -r requirements.txt \
 && (playwright install --with-deps chromium || echo "WARNING: Chromium not installed; the guest API path still works")

COPY . .

# Render injects $PORT; bind to 0.0.0.0 so it is reachable from outside the container.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]