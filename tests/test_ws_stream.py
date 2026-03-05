from __future__ import annotations

from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))
from server.app import app

client = TestClient(app)


def test_ws_stream_start_audio_stop() -> None:
    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_json({"type": "start", "session_id": "sess_test", "sample_rate": 16000, "lang": "zh"})
        start_ack = ws.receive_json()
        assert start_ack["type"] == "status"
        assert start_ack["message"] == "session_started"

        ws.send_bytes(b"\x01\x00" * 17000)
        partial = ws.receive_json()
        assert partial["type"] == "partial"
        assert partial["text"].startswith("[mock-zh] partial")
        assert partial["metrics"]["first_token_latency_ms"] >= 0

        ws.send_json({"type": "stop"})
        final = ws.receive_json()
        assert final["type"] == "final"
        assert final["text"].startswith("[mock-zh] final")
        assert final["metrics"]["sentence_latency_ms"] >= partial["metrics"]["first_token_latency_ms"]


def test_ws_stream_audio_before_start_returns_error() -> None:
    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_bytes(b"\x01\x00" * 100)
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "BAD_AUDIO_STATE"


def test_ws_stream_bad_pcm_chunk_returns_error() -> None:
    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "lang": "zh"})
        _ = ws.receive_json()
        ws.send_bytes(b"\x01")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "BAD_AUDIO_FORMAT"


def test_ws_stream_idle_timeout_returns_error() -> None:
    original_timeout = app.state.settings.ws_idle_timeout_ms
    app.state.settings.ws_idle_timeout_ms = 50
    try:
        with client.websocket_connect("/v1/asr/stream") as ws:
            ws.send_json({"type": "start", "sample_rate": 16000, "lang": "zh"})
            _ = ws.receive_json()
            time.sleep(0.08)
            err = ws.receive_json()
            assert err["type"] == "error"
            assert err["code"] == "SESSION_IDLE_TIMEOUT"
    finally:
        app.state.settings.ws_idle_timeout_ms = original_timeout


def test_ws_stream_stop_without_audio_returns_error() -> None:
    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_json({"type": "start", "sample_rate": 16000, "lang": "zh"})
        _ = ws.receive_json()
        ws.send_json({"type": "stop"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "BAD_AUDIO_STATE"


def test_ws_stream_bad_json_returns_error() -> None:
    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_text("{bad json")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["code"] == "BAD_JSON"


def test_ws_stream_reconnect_with_same_session_id_is_allowed() -> None:
    for _ in range(2):
        with client.websocket_connect("/v1/asr/stream") as ws:
            ws.send_json({"type": "start", "session_id": "sess_reuse", "sample_rate": 16000, "lang": "zh"})
            start_ack = ws.receive_json()
            assert start_ack["type"] == "status"
            assert start_ack["session_id"] == "sess_reuse"
            ws.send_bytes(b"\x01\x00" * 500)
            ws.send_json({"type": "stop"})
            final = ws.receive_json()
            assert final["type"] == "final"


def test_ws_stream_time_triggered_partial_with_jitter_and_silence(monkeypatch) -> None:
    class FakeClock:
        def __init__(self, now: float = 1000.0) -> None:
            self.now = now

        def monotonic(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    clock = FakeClock()
    monkeypatch.setattr("server.routes.ws_stream.monotonic", clock.monotonic)

    # Ensure partial is time-driven in this scenario, not bytes-driven.
    bytes_threshold = 64000
    partial_interval_ms = 200
    monkeypatch.setattr(app.state.settings, "partial_bytes_threshold", bytes_threshold)
    monkeypatch.setattr(app.state.settings, "partial_interval_ms", partial_interval_ms)

    chunk_1 = b"\x01\x00" * 80
    chunk_2 = b"\x02\x00" * 90
    silence_chunk = b"\x00\x00" * 70
    total_bytes = len(chunk_1) + len(chunk_2) + len(silence_chunk)
    assert total_bytes < bytes_threshold

    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_json({"type": "start", "session_id": "sess_jitter", "sample_rate": 16000, "lang": "zh"})
        start_ack = ws.receive_json()
        assert start_ack["type"] == "status"
        assert start_ack["message"] == "session_started"

        # Jittery chunk cadence with a silence gap: 60ms, 70ms, then 180ms.
        clock.advance(0.06)
        ws.send_bytes(chunk_1)
        clock.advance(0.07)
        ws.send_bytes(chunk_2)
        clock.advance(0.18)
        ws.send_bytes(silence_chunk)

        partial = ws.receive_json()
        assert partial["type"] == "partial"
        assert partial["text"].startswith("[mock-zh] partial")
        assert partial["metrics"]["first_token_latency_ms"] >= partial_interval_ms

        clock.advance(0.35)
        ws.send_json({"type": "stop"})
        final = ws.receive_json()
        assert final["type"] == "final"
        sentence_latency_ms = final["metrics"]["sentence_latency_ms"]
        first_token_latency_ms = partial["metrics"]["first_token_latency_ms"]
        assert sentence_latency_ms >= first_token_latency_ms
        assert sentence_latency_ms < 5000
