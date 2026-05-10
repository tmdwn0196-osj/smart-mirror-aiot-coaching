#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${APP_DIR}/.." && pwd)"

cd "${APP_DIR}"

PYTHON_BIN=""
EXTERNAL_HOST="${HOST-}"
EXTERNAL_PORT="${PORT-}"
EXTERNAL_LOG_LEVEL="${LOG_LEVEL-}"

if [ -f "${REPO_DIR}/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "${REPO_DIR}/.venv/bin/activate"
  PYTHON_BIN="${REPO_DIR}/.venv/bin/python"
fi

if [ -f "${APP_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${APP_DIR}/.env"
  set +a
fi

if [ -n "${EXTERNAL_HOST}" ]; then
  HOST="${EXTERNAL_HOST}"
fi

if [ -n "${EXTERNAL_PORT}" ]; then
  PORT="${EXTERNAL_PORT}"
fi

if [ -n "${EXTERNAL_LOG_LEVEL}" ]; then
  LOG_LEVEL="${EXTERNAL_LOG_LEVEL}"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7000}"
LOG_LEVEL="${LOG_LEVEL:-info}"

if [ -z "${PYTHON_BIN}" ] || [ ! -x "${PYTHON_BIN}" ]; then
  echo "root virtualenv not found: ${REPO_DIR}/.venv/bin/python" >&2
  exit 127
fi

exec "${PYTHON_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" --log-level "${LOG_LEVEL}"
