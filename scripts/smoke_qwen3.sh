#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8011}"
BASE_URL="http://${HOST}:${PORT}"
TMP_DIR="${TMPDIR:-/tmp}"
AUDIO_PATH="${AUDIO_PATH:-$TMP_DIR/qwen3_smoke_1s_silence.wav}"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/logs/smoke_qwen3}"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$OUT_DIR/$RUN_TS"
UVICORN_LOG="$RUN_DIR/uvicorn.log"
HEALTHZ_PATH="$RUN_DIR/healthz.json"
TRANSCRIBE_PATH="$RUN_DIR/transcribe.json"
SUMMARY_PATH="$RUN_DIR/summary.json"

PASS_COUNT=0
FAIL_COUNT=0
export PASS_COUNT FAIL_COUNT
UVICORN_PID=""

mkdir -p "$RUN_DIR"

pass() {
  echo "PASS: $*"
  PASS_COUNT=$((PASS_COUNT + 1))
  export PASS_COUNT
}

fail() {
  echo "FAIL: $*"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  export FAIL_COUNT
}

cleanup() {
  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" >/dev/null 2>&1; then
    kill "$UVICORN_PID" >/dev/null 2>&1 || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
}

write_summary() {
  "$PYTHON_BIN" - <<'PY' || true
import json
import os
from datetime import datetime

summary = {
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "base_url": os.environ.get("BASE_URL"),
    "audio_path": os.environ.get("AUDIO_PATH"),
    "run_dir": os.environ.get("RUN_DIR"),
    "pass_count": int(os.environ.get("PASS_COUNT", "0")),
    "fail_count": int(os.environ.get("FAIL_COUNT", "0")),
    "healthz_path": os.environ.get("HEALTHZ_PATH"),
    "transcribe_path": os.environ.get("TRANSCRIBE_PATH"),
    "uvicorn_log": os.environ.get("UVICORN_LOG"),
    "result": "PASS" if os.environ.get("FAIL_COUNT", "0") == "0" else "FAIL",
}

with open(os.environ["SUMMARY_PATH"], "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
PY
}

export BASE_URL AUDIO_PATH RUN_DIR HEALTHZ_PATH TRANSCRIBE_PATH UVICORN_LOG SUMMARY_PATH
trap 'write_summary; cleanup' EXIT

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "FAIL: Python not found or not executable at $PYTHON_BIN"
  exit 2
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import importlib.util
if importlib.util.find_spec("qwen3_asr") is None and importlib.util.find_spec("qwen_asr") is None:
    raise SystemExit(1)
PY
then
  echo "FAIL: qwen3 dependency missing. Install/import 'qwen3_asr' or 'qwen_asr' first, then retry."
  exit 2
fi
pass "qwen3 dependency import check (qwen3_asr|qwen_asr)"

if [[ ! -f "$AUDIO_PATH" ]]; then
  "$PYTHON_BIN" - "$AUDIO_PATH" <<'PY'
import struct
import sys
import wave

path = sys.argv[1]
sample_rate = 16000
seconds = 1
samples = sample_rate * seconds
with wave.open(path, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(struct.pack("<" + "h" * samples, *([0] * samples)))
PY
  pass "generated 1s silence wav at $AUDIO_PATH"
else
  pass "using existing audio file: $AUDIO_PATH"
fi

echo "Starting FastAPI with ASR_ENGINE=qwen3 on ${BASE_URL} ..."
ASR_ENGINE=qwen3 "$PYTHON_BIN" -m uvicorn server.app:app --host "$HOST" --port "$PORT" >"$UVICORN_LOG" 2>&1 &
UVICORN_PID=$!

healthz_json=""
for _ in {1..40}; do
  if healthz_json="$(curl -fsS "$BASE_URL/healthz" 2>/dev/null)"; then
    break
  fi
  sleep 0.25
done

if [[ -z "$healthz_json" ]]; then
  fail "server did not become ready at $BASE_URL/healthz"
  echo "Hint: check $UVICORN_LOG"
  exit 1
fi
printf '%s\n' "$healthz_json" >"$HEALTHZ_PATH"

export HEALTHZ_JSON="$healthz_json"
if ! health_eval="$("$PYTHON_BIN" - <<'PY'
import json
import os
import sys

obj = json.loads(os.environ["HEALTHZ_JSON"])
engine = obj.get("engine")
engine_ready = obj.get("engine_ready")
caps = obj.get("engine_capabilities") if isinstance(obj.get("engine_capabilities"), dict) else {}
model_source = caps.get("model_source")
is_placeholder = caps.get("is_placeholder")
fallback_reason = obj.get("engine_fallback_reason")

print(f"engine={engine}")
print(f"engine_ready={engine_ready}")
print(f"engine_capabilities={json.dumps(caps, ensure_ascii=False, sort_keys=True)}")

ok = True
if engine != "qwen3":
    print("reason=engine_not_qwen3")
    ok = False
if model_source not in {"qwen3_asr", "qwen_asr"}:
    print("reason=model_source_not_supported")
    ok = False
if engine_ready is not True:
    print("reason=engine_ready_not_true")
    ok = False
if is_placeholder is not False:
    print("reason=is_placeholder_not_false")
    ok = False
if fallback_reason is not None:
    print("reason=engine_fallback_present")
    ok = False

sys.exit(0 if ok else 1)
PY
)"; then
  echo "$health_eval"
  fail "/healthz qwen3 real-backend validation"
  exit 1
fi

echo "$health_eval"
pass "/healthz qwen3 real-backend validation"

transcribe_json=""
if ! transcribe_json="$(curl -fsS -X POST "$BASE_URL/v1/asr/transcribe" -F "file=@$AUDIO_PATH" -F "lang=zh" 2>/dev/null)"; then
  fail "POST /v1/asr/transcribe failed"
  exit 1
fi
printf '%s\n' "$transcribe_json" >"$TRANSCRIBE_PATH"

export TRANSCRIBE_JSON="$transcribe_json"
if ! transcribe_eval="$("$PYTHON_BIN" - <<'PY'
import json
import os
import sys

obj = json.loads(os.environ["TRANSCRIBE_JSON"])
text = obj.get("text")
segments = obj.get("segments")
metrics = obj.get("metrics")

ok = isinstance(text, str) and text.strip() != ""
ok = ok and isinstance(segments, list) and len(segments) >= 1
ok = ok and isinstance(metrics, dict) and "processing_ms" in metrics

print(f"text={text!r}")
print(f"segments_count={len(segments) if isinstance(segments, list) else 'invalid'}")

sys.exit(0 if ok else 1)
PY
)"; then
  echo "$transcribe_eval"
  fail "/v1/asr/transcribe minimal validation"
  exit 1
fi

echo "$transcribe_eval"
pass "/v1/asr/transcribe minimal validation"

echo "Artifacts: run_dir=$RUN_DIR"
echo "Summary: PASS=${PASS_COUNT}, FAIL=${FAIL_COUNT}"
exit 0
