#!/usr/bin/env bash
set -euo pipefail

# Start the complete fictional follow-up application.
# Intended to run behind a trusted HTTPS reverse proxy.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

export FOLLOWUP_ENABLE_LOCAL_AGENT=1
export FOLLOWUP_DEMO_DB="runtime/active/clinic.db"

# Public visitors each get a private fictional case, so nobody can
# complete or jam the demo for the next reviewer. Behind the proxy
# every client looks local, so the shared case must not be served.
export FOLLOWUP_GUEST_SESSIONS=1
# The site is served over HTTPS only.
export FOLLOWUP_SECURE_COOKIES=1

if [[ -z "${VULTR_SERVERLESS_INFERENCE_API_KEY:-}" ]]; then
    echo "ERROR: Vultr inference API key is missing."
    exit 1
fi

if [[ -z "${VULTR_MODEL:-}" ]]; then
    echo "ERROR: VULTR_MODEL is not configured."
    exit 1
fi

if [[ ! -f runtime/active/clinic.db ]]; then
    echo "ERROR: Fictional demo database is missing."
    echo "Initialize it using api.demo_state.prepare_demo_db."
    exit 1
fi

echo "Starting complete Lab2Care application."
echo "Model: ${VULTR_MODEL}"
echo "Backend: http://127.0.0.1:${FOLLOWUP_PORT:-8000}"
echo "Data mode: fictional"

exec python -m uvicorn api.dev_main:app \
    --host 127.0.0.1 \
    --port "${FOLLOWUP_PORT:-8000}" \
    --workers 1 \
    --no-proxy-headers
