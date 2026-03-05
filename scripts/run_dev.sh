#!/usr/bin/env bash
set -euo pipefail

export ASR_DEVICE="${ASR_DEVICE:-cpu}"
export ASR_LOG_PATH="${ASR_LOG_PATH:-logs/asr-service.log}"
export ASR_LOG_LEVEL="${ASR_LOG_LEVEL:-INFO}"

uvicorn server.app:app --host 0.0.0.0 --port 8000 --reload
