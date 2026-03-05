from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from server.asr_engine.base import BaseASREngine
from server.asr_engine.qwen_engine import MockQwenASREngine


def _pcm16_bytes(duration_ms: int, sample_rate: int = 16000) -> bytes:
    samples = int(sample_rate * (duration_ms / 1000))
    return b"\x01\x00" * samples


def test_base_asr_engine_contract_can_be_satisfied_by_minimal_impl() -> None:
    class MinimalEngine(BaseASREngine):
        def transcribe(self, audio_bytes: bytes, lang: str, sample_rate: int = 16000) -> dict[str, object]:
            return {"text": "", "segments": []}

        def stream_partial(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
            return {"text": "", "start_ms": 0, "end_ms": 0}

        def stream_final(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
            return {"sentence_id": 1, "text": "", "start_ms": 0, "end_ms": 1}

    engine = MinimalEngine(device="cpu")

    assert isinstance(engine, BaseASREngine)
    assert engine.model_loaded is True
    assert engine.engine_capabilities() == {"model_loaded": True, "is_placeholder": False}
    assert isinstance(engine.transcribe(b"", "zh"), dict)
    assert isinstance(engine.stream_partial(b"", "zh", 16000), dict)
    assert isinstance(engine.stream_final(b"", "zh", 16000), dict)


def test_mock_engine_capabilities_fields() -> None:
    engine = MockQwenASREngine(device="cpu")

    capabilities = engine.engine_capabilities()
    assert capabilities == {
        "model_loaded": True,
        "is_placeholder": True,
        "model_source": "mock",
    }


def test_mock_transcribe_contract_fields_types_and_duration_consistency() -> None:
    engine = MockQwenASREngine(device="cpu")
    sample_rate = 16000
    audio = _pcm16_bytes(duration_ms=2500, sample_rate=sample_rate)

    result = engine.transcribe(audio_bytes=audio, lang="zh", sample_rate=sample_rate)

    assert isinstance(result["text"], str)
    assert isinstance(result["segments"], list)
    assert len(result["segments"]) >= 1

    expected_duration_ms = int((len(audio) / 2 / sample_rate) * 1000)
    previous_end = 0
    for segment in result["segments"]:
        # Each segment must include timing + text with correct types.
        assert isinstance(segment["text"], str)
        assert isinstance(segment["start_ms"], int)
        assert isinstance(segment["end_ms"], int)
        assert 0 <= segment["start_ms"] <= segment["end_ms"]
        assert segment["start_ms"] >= previous_end
        previous_end = segment["end_ms"]

    assert result["segments"][0]["start_ms"] == 0
    assert result["segments"][-1]["end_ms"] == expected_duration_ms


def test_mock_stream_partial_contract_fields_types_and_duration_consistency() -> None:
    engine = MockQwenASREngine(device="cpu")
    sample_rate = 16000
    audio = _pcm16_bytes(duration_ms=600, sample_rate=sample_rate)

    partial = engine.stream_partial(audio_bytes=audio, lang="zh", sample_rate=sample_rate)

    assert isinstance(partial["text"], str)
    assert isinstance(partial["start_ms"], int)
    assert isinstance(partial["end_ms"], int)
    assert partial["start_ms"] == 0

    expected_duration_ms = int((len(audio) / 2 / sample_rate) * 1000)
    assert partial["end_ms"] == expected_duration_ms
    assert partial["end_ms"] >= partial["start_ms"]


def test_mock_stream_final_contract_fields_types_sentence_id_and_duration_consistency() -> None:
    engine = MockQwenASREngine(device="cpu")
    sample_rate = 16000
    audio = _pcm16_bytes(duration_ms=1200, sample_rate=sample_rate)

    final = engine.stream_final(audio_bytes=audio, lang="zh", sample_rate=sample_rate)

    assert isinstance(final["sentence_id"], int)
    assert final["sentence_id"] >= 1
    assert isinstance(final["text"], str)
    assert isinstance(final["start_ms"], int)
    assert isinstance(final["end_ms"], int)
    assert final["start_ms"] == 0

    expected_duration_ms = int((len(audio) / 2 / sample_rate) * 1000)
    assert final["end_ms"] == expected_duration_ms
    assert final["end_ms"] >= final["start_ms"]
