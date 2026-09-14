#!/bin/bash
# SessionStart hook for Claude Code on the web.
# Synchronous, idempotent: installs deps for both the Python backend and the
# TypeScript/React frontend so lint/typecheck/tests work immediately. Only
# runs in a remote (web) session.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

# --- Backend: Python venv + pip install ---
if [ ! -d "backend/.venv" ]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/pip install --upgrade pip
backend/.venv/bin/pip install -r backend/requirements.txt
# Kronos extras (backend/requirements-kronos.txt, ~2GB torch) are optional
# and deliberately NOT installed here — CI doesn't install them either, and
# the Kronos-dependent tests pass without it (they test the in-process call
# contract, not real inference).

# --- Frontend: npm install (not `npm ci`) so a cached container layer's
# node_modules is reused and only updated, rather than wiped and reinstalled
# from scratch. ---
(cd frontend && npm install)

# Put the backend venv on PATH so `pytest`, `python`, `pip` resolve to it
# without callers needing to know the venv's location.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  grep -qxF "export PATH=\"$PROJECT_DIR/backend/.venv/bin:\$PATH\"" "$CLAUDE_ENV_FILE" 2>/dev/null || \
    echo "export PATH=\"$PROJECT_DIR/backend/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

exit 0
