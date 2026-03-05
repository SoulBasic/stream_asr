from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

from fastapi.testclient import TestClient
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from server.app import create_app


def test_transcribe_keeps_200_and_healthz_fallback_reason_on_qwen3_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(**_: object) -> dict[str, object]:
        raise RuntimeError("backend crashed in api")

    monkeypatch.setenv("ASR_ENGINE", "qwen3")
    monkeypatch.setattr("server.asr_engine.engine_factory._ensure_qwen3_dependencies", lambda: None)
    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: SimpleNamespace(transcribe=_boom))

    client = TestClient(create_app())

    files = {"file": ("sample.pcm", b"\x00\x01" * 32000, "application/octet-stream")}
    data = {"lang": "zh"}
    transcribe_resp = client.post("/v1/asr/transcribe", files=files, data=data)

    assert transcribe_resp.status_code == 200
    payload = transcribe_resp.json()
    assert payload["text"].startswith("[qwen3-zh] transcribed")
    assert isinstance(payload["segments"], list)
    assert "metrics" in payload and payload["metrics"]["processing_ms"] >= 0

    healthz_resp = client.get("/healthz")
    assert healthz_resp.status_code == 200
    healthz = healthz_resp.json()

    assert healthz["engine"] == "qwen3"
    assert healthz["engine_ready"] is False
    assert healthz["engine_capabilities"]["is_placeholder"] is True
    assert "qwen3_transcribe_failed" in str(healthz["engine_capabilities"].get("fallback_reason"))
    assert healthz["engine_fallback_reason"] == healthz["engine_capabilities"]["fallback_reason"]


def test_transcribe_runtime_failure_then_recovery_clears_fallback_and_engine_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"calls": 0}

    def _flaky(**_: object) -> dict[str, object]:
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("backend temporary failure")
        return {
            "text": "real-recovered",
            "segments": [{"start": 0, "end": 1000, "content": "real-recovered"}],
        }

    monkeypatch.setenv("ASR_ENGINE", "qwen3")
    monkeypatch.setattr("server.asr_engine.engine_factory._ensure_qwen3_dependencies", lambda: None)
    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: SimpleNamespace(transcribe=_flaky))

    client = TestClient(create_app())
    files = {"file": ("sample.pcm", b"\x00\x01" * 32000, "application/octet-stream")}
    data = {"lang": "zh"}

    first_resp = client.post("/v1/asr/transcribe", files=files, data=data)
    assert first_resp.status_code == 200
    assert first_resp.json()["text"].startswith("[qwen3-zh] transcribed")

    healthz_after_failure = client.get("/healthz")
    assert healthz_after_failure.status_code == 200
    h1 = healthz_after_failure.json()
    assert h1["engine_ready"] is False
    assert "qwen3_transcribe_failed" in str(h1["engine_capabilities"].get("fallback_reason"))

    second_resp = client.post("/v1/asr/transcribe", files=files, data=data)
    assert second_resp.status_code == 200
    second_payload = second_resp.json()
    assert second_payload["text"] == "real-recovered"
    assert second_payload["segments"] == [{"start_ms": 0, "end_ms": 1000, "text": "real-recovered"}]

    healthz_after_recovery = client.get("/healthz")
    assert healthz_after_recovery.status_code == 200
    h2 = healthz_after_recovery.json()
    assert h2["engine_ready"] is True
    assert h2["engine_capabilities"]["is_placeholder"] is False
    assert h2["engine_capabilities"].get("fallback_reason") is None
    assert h2["engine_fallback_reason"] is None
