from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from server.app import app

client = TestClient(app)


def test_healthz() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["device"] in {"cpu", "cuda"}
    assert data["model_loaded"] is True
    assert isinstance(data["engine_ready"], bool)
    assert isinstance(data["engine_capabilities"], dict)
    assert data["engine_capabilities"]["model_loaded"] is True
    assert isinstance(data["engine_capabilities"]["is_placeholder"], bool)
    assert data["engine_ready"] is (data["model_loaded"] and not data["engine_capabilities"]["is_placeholder"] and data["engine_fallback_reason"] is None)
    assert data["engine"] in {"mock", "qwen3"}
    assert data["backend"] in {"mock", "cpu"}
    assert "engine_fallback_reason" in data


def test_transcribe() -> None:
    files = {"file": ("sample.pcm", b"\x00\x01" * 32000, "application/octet-stream")}
    data = {"lang": "zh"}
    resp = client.post("/v1/asr/transcribe", files=files, data=data)

    assert resp.status_code == 200
    payload = resp.json()
    assert "text" in payload
    assert payload["text"].startswith("[mock-zh]")
    assert isinstance(payload["segments"], list)
    assert len(payload["segments"]) >= 1
    assert "metrics" in payload and "processing_ms" in payload["metrics"]


def test_transcribe_short_audio_returns_400() -> None:
    files = {"file": ("short.pcm", b"\x00\x01" * 50, "application/octet-stream")}
    data = {"lang": "zh"}
    resp = client.post("/v1/asr/transcribe", files=files, data=data)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "audio too short"


def test_transcribe_odd_bytes_returns_400() -> None:
    files = {"file": ("bad.pcm", b"\x00\x01\x02", "application/octet-stream")}
    data = {"lang": "zh"}
    resp = client.post("/v1/asr/transcribe", files=files, data=data)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid pcm16 payload"
