from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from server.asr_engine.qwen3_adapter import Qwen3ASREngine


def _pcm16_bytes(duration_ms: int, sample_rate: int = 16000) -> bytes:
    samples = int(sample_rate * (duration_ms / 1000))
    return b"\x01\x00" * samples


def test_qwen3_transcribe_contract_fields_types_and_duration_consistency(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(
        transcribe_bytes=lambda audio_bytes, lang, sample_rate: {
            "text": f"real-{lang}",
            "segments": [
                {
                    "start_ms": 0,
                    "end_ms": int((len(audio_bytes) / 2 / sample_rate) * 1000),
                    "text": f"real-{lang}",
                }
            ],
        }
    )
    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: fake_module)

    engine = Qwen3ASREngine(device="cpu")
    sample_rate = 16000
    audio = _pcm16_bytes(duration_ms=2200, sample_rate=sample_rate)

    result = engine.transcribe(audio_bytes=audio, lang="zh", sample_rate=sample_rate)

    assert isinstance(result["text"], str)
    assert isinstance(result["segments"], list)
    assert len(result["segments"]) >= 1

    expected_duration_ms = int((len(audio) / 2 / sample_rate) * 1000)
    assert result["segments"][0]["start_ms"] == 0
    assert result["segments"][-1]["end_ms"] == expected_duration_ms

    previous_end = 0
    for segment in result["segments"]:
        assert isinstance(segment["text"], str)
        assert isinstance(segment["start_ms"], int)
        assert isinstance(segment["end_ms"], int)
        assert 0 <= segment["start_ms"] <= segment["end_ms"]
        assert segment["start_ms"] >= previous_end
        previous_end = segment["end_ms"]


def test_qwen3_stream_partial_and_final_contract_and_zero_audio_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: SimpleNamespace())
    engine = Qwen3ASREngine(device="cpu")

    partial = engine.stream_partial(audio_bytes=b"", lang="zh", sample_rate=16000)
    final = engine.stream_final(audio_bytes=b"", lang="zh", sample_rate=16000)

    assert isinstance(partial["text"], str)
    assert partial["start_ms"] == 0
    assert partial["end_ms"] == 0

    assert isinstance(final["sentence_id"], int)
    assert final["sentence_id"] >= 1
    assert isinstance(final["text"], str)
    assert final["start_ms"] == 0
    # final 结果对空音频也有最小时长保护，防止 0ms 导致上游边界问题
    assert final["end_ms"] >= 1


def test_qwen3_engine_capabilities_fields_with_real_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = SimpleNamespace(transcribe=lambda **_: {"text": "ok", "segments": []})
    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: fake_module)

    engine = Qwen3ASREngine(device="cpu")

    capabilities = engine.engine_capabilities()
    assert capabilities == {
        "model_loaded": True,
        "is_placeholder": False,
        "model_source": "qwen3_asr",
    }


def test_qwen3_engine_capabilities_fields_with_placeholder_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: SimpleNamespace())

    engine = Qwen3ASREngine(device="cpu")

    capabilities = engine.engine_capabilities()
    assert capabilities["model_loaded"] is False
    assert capabilities["is_placeholder"] is True
    assert capabilities["model_source"] == "qwen3-placeholder"
    assert capabilities["fallback_reason"] == "qwen_asr_no_supported_transcribe_callable"


def test_qwen3_transcribe_runtime_failure_falls_back_to_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_: object) -> dict[str, object]:
        raise RuntimeError("backend crashed")

    monkeypatch.setattr("server.asr_engine.qwen3_adapter.import_module", lambda _: SimpleNamespace(transcribe=_boom))
    engine = Qwen3ASREngine(device="cpu")

    result = engine.transcribe(audio_bytes=_pcm16_bytes(1000), lang="zh", sample_rate=16000)

    assert result["text"].startswith("[qwen3-zh] transcribed")
    capabilities = engine.engine_capabilities()
    assert capabilities["model_loaded"] is True
    assert capabilities["is_placeholder"] is True
    assert capabilities["model_source"] == "qwen3_asr"
    assert "qwen3_transcribe_failed" in str(capabilities["fallback_reason"])
