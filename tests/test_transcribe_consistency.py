from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from server.app import create_app


def _post_transcribe(client: TestClient) -> dict[str, object]:
    files = {"file": ("sample.pcm", b"\x00\x01" * 32000, "application/octet-stream")}
    response = client.post("/v1/asr/transcribe", files=files, data={"lang": "zh"})
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def _assert_segment_contract(payload: dict[str, object]) -> tuple[set[str], dict[str, type]]:
    segments = payload["segments"]
    assert isinstance(segments, list)
    assert len(segments) >= 1

    first = segments[0]
    assert isinstance(first, dict)
    segment_keys = set(first.keys())
    segment_types = {key: type(first[key]) for key in segment_keys}

    for segment in segments:
        assert isinstance(segment, dict)
        assert set(segment.keys()) == segment_keys
        for key, expected_type in segment_types.items():
            assert isinstance(segment[key], expected_type)
        assert isinstance(segment["start_ms"], int)
        assert isinstance(segment["end_ms"], int)
        assert segment["start_ms"] >= 0
        assert segment["end_ms"] >= 0
        assert segment["end_ms"] >= segment["start_ms"]

    return segment_keys, segment_types


def test_transcribe_response_schema_consistent_between_mock_and_qwen3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_ENGINE", "mock")
    mock_payload = _post_transcribe(TestClient(create_app()))

    # Keep qwen3 path testable without external deps. Adapter will auto-use real backend or placeholder fallback.
    monkeypatch.setenv("ASR_ENGINE", "qwen3")
    monkeypatch.setattr("server.asr_engine.engine_factory._ensure_qwen3_dependencies", lambda: None)
    qwen3_payload = _post_transcribe(TestClient(create_app()))

    assert set(mock_payload.keys()) == set(qwen3_payload.keys())
    for key in mock_payload:
        assert isinstance(qwen3_payload[key], type(mock_payload[key]))

    assert isinstance(mock_payload["metrics"], dict)
    assert isinstance(qwen3_payload["metrics"], dict)
    assert isinstance(mock_payload["metrics"]["processing_ms"], int)
    assert isinstance(qwen3_payload["metrics"]["processing_ms"], int)
    assert mock_payload["metrics"]["processing_ms"] >= 0
    assert qwen3_payload["metrics"]["processing_ms"] >= 0

    mock_segment_keys, mock_segment_types = _assert_segment_contract(mock_payload)
    qwen3_segment_keys, qwen3_segment_types = _assert_segment_contract(qwen3_payload)
    assert mock_segment_keys == qwen3_segment_keys
    assert qwen3_segment_types == mock_segment_types
