from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    asr_device: str = "cpu"
    asr_engine: str = "mock"
    log_path: str = "logs/asr-service.log"
    log_level: str = "INFO"
    partial_bytes_threshold: int = 24000
    partial_interval_ms: int = 180
    vad_energy_threshold: float = 120.0
    vad_silence_ms: int = 350
    transcribe_timeout_ms: int = 15000
    ws_idle_timeout_ms: int = 10000

    @classmethod
    def from_env(cls) -> "Settings":
        device = os.getenv("ASR_DEVICE", "cpu").strip().lower() or "cpu"
        if device not in {"cpu", "cuda"}:
            device = "cpu"

        asr_engine = os.getenv("ASR_ENGINE", "mock").strip().lower() or "mock"
        if asr_engine not in {"mock", "qwen3"}:
            asr_engine = "mock"

        log_path = os.getenv("ASR_LOG_PATH", "logs/asr-service.log").strip() or "logs/asr-service.log"
        log_level = os.getenv("ASR_LOG_LEVEL", "INFO").strip().upper() or "INFO"

        threshold_raw = os.getenv("ASR_PARTIAL_BYTES_THRESHOLD", "24000").strip()
        try:
            threshold = max(1024, int(threshold_raw))
        except ValueError:
            threshold = 24000

        partial_interval_raw = os.getenv("ASR_PARTIAL_INTERVAL_MS", "180").strip()
        try:
            partial_interval_ms = max(50, int(partial_interval_raw))
        except ValueError:
            partial_interval_ms = 180

        vad_energy_raw = os.getenv("ASR_VAD_ENERGY_THRESHOLD", "120").strip()
        try:
            vad_energy_threshold = max(0.0, float(vad_energy_raw))
        except ValueError:
            vad_energy_threshold = 120.0

        vad_silence_raw = os.getenv("ASR_VAD_SILENCE_MS", "350").strip()
        try:
            vad_silence_ms = max(0, int(vad_silence_raw))
        except ValueError:
            vad_silence_ms = 350

        transcribe_timeout_raw = os.getenv("ASR_TRANSCRIBE_TIMEOUT_MS", "15000").strip()
        try:
            transcribe_timeout_ms = max(500, int(transcribe_timeout_raw))
        except ValueError:
            transcribe_timeout_ms = 15000

        ws_idle_timeout_raw = os.getenv("ASR_WS_IDLE_TIMEOUT_MS", "10000").strip()
        try:
            ws_idle_timeout_ms = max(1000, int(ws_idle_timeout_raw))
        except ValueError:
            ws_idle_timeout_ms = 10000

        return cls(
            asr_device=device,
            asr_engine=asr_engine,
            log_path=log_path,
            log_level=log_level,
            partial_bytes_threshold=threshold,
            partial_interval_ms=partial_interval_ms,
            vad_energy_threshold=vad_energy_threshold,
            vad_silence_ms=vad_silence_ms,
            transcribe_timeout_ms=transcribe_timeout_ms,
            ws_idle_timeout_ms=ws_idle_timeout_ms,
        )
