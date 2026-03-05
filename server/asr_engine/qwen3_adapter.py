from __future__ import annotations

import os
from importlib import import_module
from math import ceil
from types import ModuleType
from typing import Any, Callable

from server.asr_engine.base import BaseASREngine


class Qwen3ASREngine(BaseASREngine):
    """CPU-first qwen3 adapter.

    - 如果本机存在可调用的 `qwen3_asr` 推理入口，则优先走真实 transcribe。
    - 若本机只有 `qwen_asr` 官方包，则尝试加载 `Qwen3ASRModel` 作为真实后端。
    - 若依赖不可用或入口不兼容，则自动回退占位输出，保证服务可用。
    """

    def __init__(self, device: str) -> None:
        super().__init__(device=device)
        self.backend = "cpu"
        self.model_source = "qwen3-placeholder"
        self.fallback_reason: str | None = None
        self.runtime_fallback_reason: str | None = None
        self._transcribe_impl: Callable[..., Any] | None = None
        self._qwen_asr_model: Any | None = None
        self._qwen_asr_model_name = os.getenv("ASR_QWEN_MODEL", "Qwen/Qwen3-ASR-0.6B").strip() or "Qwen/Qwen3-ASR-0.6B"
        self._probe_backend()

    def _probe_backend(self) -> None:
        # 优先兼容已有的 qwen3_asr 入口
        try:
            module = import_module("qwen3_asr")
            impl = self._resolve_transcribe_callable(module)
            if impl is not None:
                self._transcribe_impl = impl
                self.model_loaded = True
                self.model_source = "qwen3_asr"
                self.fallback_reason = None
                return
        except Exception as exc:
            self.fallback_reason = f"qwen3_import_failed: {exc}"

        # 兼容官方 qwen-asr 包（qwen_asr）
        try:
            qwen_asr_module = import_module("qwen_asr")
        except Exception as exc:
            self.model_loaded = False
            self.fallback_reason = f"qwen_dependency_unavailable: {exc}"
            return

        impl = self._build_qwen_asr_transcribe_callable(qwen_asr_module)
        if impl is None:
            self.model_loaded = False
            self.fallback_reason = "qwen_asr_no_supported_transcribe_callable"
            return

        self._transcribe_impl = impl
        self.model_loaded = True
        self.model_source = "qwen_asr"
        self.fallback_reason = None

    @staticmethod
    def _resolve_transcribe_callable(module: ModuleType) -> Callable[..., Any] | None:
        for attr in ("transcribe_bytes", "transcribe"):
            candidate = getattr(module, attr, None)
            if callable(candidate):
                return candidate
        return None

    def _build_qwen_asr_transcribe_callable(self, module: ModuleType) -> Callable[..., Any] | None:
        model_cls = getattr(module, "Qwen3ASRModel", None)
        if model_cls is None or not hasattr(model_cls, "from_pretrained"):
            return None

        try:
            model = model_cls.from_pretrained(
                self._qwen_asr_model_name,
                device_map="cuda:0" if self.device == "cuda" else "cpu",
            )
        except Exception as exc:
            self.model_loaded = False
            self.fallback_reason = f"qwen_asr_model_load_failed: {exc}"
            return None

        self._qwen_asr_model = model

        def _transcribe_impl(*, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
            import numpy as np

            pcm = np.frombuffer(audio_bytes, dtype="<i2").astype("float32") / 32768.0
            raw = self._qwen_asr_model.transcribe(
                audio=(pcm, sample_rate),
                language=lang,
                return_time_stamps=True,
            )
            return self._normalize_qwen_asr_transcribe_result(raw)

        return _transcribe_impl

    @staticmethod
    def _normalize_qwen_asr_transcribe_result(raw: object) -> dict[str, object]:
        item = raw
        if isinstance(raw, list):
            item = raw[0] if raw else {}

        text = ""
        segments: list[dict[str, object]] = []

        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            raw_segments = item.get("segments")
            if isinstance(raw_segments, list):
                segments = [segment for segment in raw_segments if isinstance(segment, dict)]
        else:
            text = str(getattr(item, "text", "")).strip()
            raw_segments = getattr(item, "segments", None)
            if isinstance(raw_segments, list):
                segments = [segment for segment in raw_segments if isinstance(segment, dict)]

        return {"text": text, "segments": segments}

    def engine_capabilities(self) -> dict[str, object]:
        capabilities = super().engine_capabilities()
        capabilities["is_placeholder"] = self._transcribe_impl is None or self.runtime_fallback_reason is not None
        capabilities["model_source"] = self.model_source
        fallback_reason = self.runtime_fallback_reason or self.fallback_reason
        if fallback_reason:
            capabilities["fallback_reason"] = fallback_reason
        return capabilities

    def _duration_ms(self, audio_bytes: bytes, sample_rate: int) -> int:
        if sample_rate <= 0:
            sample_rate = 16000
        return int((len(audio_bytes) / 2 / sample_rate) * 1000)

    def _placeholder_transcribe(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
        duration_ms = max(1, self._duration_ms(audio_bytes, sample_rate))
        text = f"[qwen3-{lang}] transcribed {len(audio_bytes)} bytes"

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

    @staticmethod
    def _to_non_negative_int(value: object, fallback: int) -> int:
        if isinstance(value, bool):
            return fallback
        if isinstance(value, (int, float)):
            return max(0, int(value))
        if isinstance(value, str):
            try:
                return max(0, int(float(value.strip())))
            except ValueError:
                return fallback
        return fallback

    def _normalize_segments(
        self,
        raw_segments: object,
        default_text: str,
        default_duration_ms: int,
    ) -> list[dict[str, object]]:
        if not isinstance(raw_segments, list):
            return [{"start_ms": 0, "end_ms": default_duration_ms, "text": default_text}]

        normalized: list[dict[str, object]] = []
        previous_end = 0
        for raw_segment in raw_segments:
            if not isinstance(raw_segment, dict):
                continue
            start_ms = self._to_non_negative_int(raw_segment.get("start_ms", raw_segment.get("start")), previous_end)
            start_ms = max(start_ms, previous_end)
            end_ms = self._to_non_negative_int(raw_segment.get("end_ms", raw_segment.get("end")), start_ms)
            end_ms = max(end_ms, start_ms)
            segment_text = str(raw_segment.get("text", raw_segment.get("content", default_text))).strip() or default_text
            normalized.append({"start_ms": start_ms, "end_ms": end_ms, "text": segment_text})
            previous_end = end_ms

        if normalized:
            return normalized
        return [{"start_ms": 0, "end_ms": default_duration_ms, "text": default_text}]

    def transcribe(self, audio_bytes: bytes, lang: str, sample_rate: int = 16000) -> dict[str, object]:
        if self._transcribe_impl is None:
            return self._placeholder_transcribe(audio_bytes=audio_bytes, lang=lang, sample_rate=sample_rate)

        try:
            raw = self._transcribe_impl(audio_bytes=audio_bytes, lang=lang, sample_rate=sample_rate)
        except Exception as exc:
            self.runtime_fallback_reason = f"qwen3_transcribe_failed: {exc}"
            return self._placeholder_transcribe(audio_bytes=audio_bytes, lang=lang, sample_rate=sample_rate)

        self.runtime_fallback_reason = None
        if not isinstance(raw, dict):
            self.runtime_fallback_reason = "qwen3_transcribe_invalid_response"
            return self._placeholder_transcribe(audio_bytes=audio_bytes, lang=lang, sample_rate=sample_rate)

        text = str(raw.get("text", "")).strip() or f"[qwen3-{lang}]"
        duration_ms = max(1, self._duration_ms(audio_bytes, sample_rate))
        segments = self._normalize_segments(
            raw_segments=raw.get("segments"),
            default_text=text,
            default_duration_ms=duration_ms,
        )
        return {"text": text, "segments": segments}

    def stream_partial(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
        duration_ms = self._duration_ms(audio_bytes, sample_rate)
        return {
            "text": f"[qwen3-{lang}] partial up to {duration_ms}ms",
            "start_ms": 0,
            "end_ms": duration_ms,
        }

    def stream_final(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, object]:
        duration_ms = max(1, self._duration_ms(audio_bytes, sample_rate))
        return {
            "sentence_id": 1,
            "text": f"[qwen3-{lang}] final {len(audio_bytes)} bytes",
            "start_ms": 0,
            "end_ms": duration_ms,
        }
