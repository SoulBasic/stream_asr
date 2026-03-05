from __future__ import annotations

from math import ceil

from server.asr_engine.base import BaseASREngine


class MockQwenASREngine(BaseASREngine):
    """Mock engine with deterministic outputs, ready to swap for real qwen3-asr."""

    def engine_capabilities(self) -> dict[str, object]:
        capabilities = super().engine_capabilities()
        capabilities["is_placeholder"] = True
        capabilities["model_source"] = "mock"
        return capabilities

    def _duration_ms(self, audio_bytes: bytes, sample_rate: int) -> int:
        if sample_rate <= 0:
            sample_rate = 16000
        # PCM16 mono -> 2 bytes per sample
        return int((len(audio_bytes) / 2 / sample_rate) * 1000)

    def transcribe(self, audio_bytes: bytes, lang: str, sample_rate: int = 16000) -> dict[str, object]:
        duration_ms = max(1, self._duration_ms(audio_bytes, sample_rate))
        text = f"[mock-{lang}] transcribed {len(audio_bytes)} bytes"

        seg_count = max(1, min(3, ceil(duration_ms / 1000)))
        seg_len = max(1, duration_ms // seg_count)
        segments = []
        for idx in range(seg_count):
            start_ms = idx * seg_len
            end_ms = duration_ms if idx == seg_count - 1 else (idx + 1) * seg_len
            segments.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "text": f"{text} (seg-{idx + 1})",
                }
            )

        return {"text": text, "segments": segments}

    def stream_partial(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
        duration_ms = self._duration_ms(audio_bytes, sample_rate)
        return {
            "text": f"[mock-{lang}] partial up to {duration_ms}ms",
            "start_ms": 0,
            "end_ms": duration_ms,
        }

    def stream_final(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
        duration_ms = max(1, self._duration_ms(audio_bytes, sample_rate))
        return {
            "sentence_id": 1,
            "text": f"[mock-{lang}] final {len(audio_bytes)} bytes",
            "start_ms": 0,
            "end_ms": duration_ms,
        }
