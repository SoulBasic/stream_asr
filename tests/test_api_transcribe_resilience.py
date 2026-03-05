from __future__ import annotations

from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from server.app import app


client = TestClient(app)


def test_transcribe_engine_failure_returns_503(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("engine down")

    monkeypatch.setattr(app.state.engine, "transcribe", _boom)

    files = {"file": ("sample.pcm", b"\x00\x01" * 16000, "application/octet-stream")}
    data = {"lang": "zh"}
    resp = client.post("/v1/asr/transcribe", files=files, data=data)

    assert resp.status_code == 503
    assert resp.json()["detail"] == "asr engine unavailable"


def test_transcribe_timeout_returns_504(monkeypatch) -> None:
    original_timeout = app.state.settings.transcribe_timeout_ms
    app.state.settings.transcribe_timeout_ms = 50

    def _slow(*args, **kwargs):
        time.sleep(0.2)
        return {
            "text": "late",
            "segments": [{"start_ms": 0, "end_ms": 200, "text": "late"}],
        }

    monkeypatch.setattr(app.state.engine, "transcribe", _slow)

    files = {"file": ("sample.pcm", b"\x00\x01" * 16000, "application/octet-stream")}
    data = {"lang": "zh"}
    resp = client.post("/v1/asr/transcribe", files=files, data=data)

    app.state.settings.transcribe_timeout_ms = original_timeout

    assert resp.status_code == 504
    assert resp.json()["detail"] == "asr transcribe timeout"
