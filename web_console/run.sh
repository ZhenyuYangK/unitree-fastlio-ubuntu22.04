#!/usr/bin/env bash
set -Eeuo pipefail
CONSOLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export G1_WEB_MODE="${G1_WEB_MODE:-local}"
if [[ "${G1_WEB_MODE}" == ros_readonly || "${G1_WEB_MODE}" == ros_control ]]; then
  source "${CONSOLE_DIR}/../g1_slam_ws/script/g1_env.sh"
  g1_source_environment
fi
export PYTHONPATH="${CONSOLE_DIR}/backend${PYTHONPATH:+:${PYTHONPATH}}"
if [[ -x "${CONSOLE_DIR}/.venv/bin/python" ]]; then
  WEB_PYTHON="${G1_WEB_PYTHON:-${CONSOLE_DIR}/.venv/bin/python}"
else
  WEB_PYTHON="${G1_WEB_PYTHON:-python3}"
fi
exec "${WEB_PYTHON}" -m g1_web
