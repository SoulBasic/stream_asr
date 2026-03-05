from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
from server.asr_engine.vad import SimpleVAD
from server.config import Settings


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        "ASR_DEVICE",
        "ASR_ENGINE",
        "ASR_PARTIAL_BYTES_THRESHOLD",
        "ASR_PARTIAL_INTERVAL_MS",
        "ASR_VAD_ENERGY_THRESHOLD",
        "ASR_VAD_SILENCE_MS",
        "ASR_TRANSCRIBE_TIMEOUT_MS",
        "ASR_WS_IDLE_TIMEOUT_MS",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_settings_from_env_defaults_to_balanced_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)

    settings = Settings.from_env()

    assert settings.asr_engine == "mock"
    assert settings.partial_bytes_threshold == 24000
    assert settings.partial_interval_ms == 180
    assert settings.vad_energy_threshold == 120.0
    assert settings.vad_silence_ms == 350
    assert settings.transcribe_timeout_ms == 15000
    assert settings.ws_idle_timeout_ms == 10000


def test_settings_from_env_invalid_device_falls_back_to_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_DEVICE", "TPU")

    settings = Settings.from_env()

    assert settings.asr_device == "cpu"


def test_settings_from_env_accepts_qwen3_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_ENGINE", "qwen3")

    settings = Settings.from_env()

    assert settings.asr_engine == "qwen3"


def test_settings_from_env_invalid_engine_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_ENGINE", "foobar")

    settings = Settings.from_env()

    assert settings.asr_engine == "mock"


def test_settings_from_env_partial_bytes_threshold_clamped_to_min(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_PARTIAL_BYTES_THRESHOLD", "1")

    settings = Settings.from_env()

    assert settings.partial_bytes_threshold == 1024


def test_settings_from_env_partial_interval_clamped_to_min(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_PARTIAL_INTERVAL_MS", "0")

    settings = Settings.from_env()

    assert settings.partial_interval_ms == 50


def test_settings_from_env_vad_threshold_parse_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_VAD_ENERGY_THRESHOLD", "not-a-float")
    monkeypatch.setenv("ASR_VAD_SILENCE_MS", "not-an-int")

    settings = Settings.from_env()

    assert settings.vad_energy_threshold == 120.0
    assert settings.vad_silence_ms == 350


def test_settings_from_env_can_switch_to_stability_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_PARTIAL_INTERVAL_MS", "240")
    monkeypatch.setenv("ASR_PARTIAL_BYTES_THRESHOLD", "32000")
    monkeypatch.setenv("ASR_VAD_ENERGY_THRESHOLD", "150")
    monkeypatch.setenv("ASR_VAD_SILENCE_MS", "500")

    settings = Settings.from_env()

    assert settings.partial_interval_ms == 240
    assert settings.partial_bytes_threshold == 32000
    assert settings.vad_energy_threshold == 150.0
    assert settings.vad_silence_ms == 500


def test_settings_from_env_timeout_values_are_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("ASR_TRANSCRIBE_TIMEOUT_MS", "10")
    monkeypatch.setenv("ASR_WS_IDLE_TIMEOUT_MS", "20")

    settings = Settings.from_env()

    assert settings.transcribe_timeout_ms == 500
    assert settings.ws_idle_timeout_ms == 1000


def test_simple_vad_should_cut_after_silence_reaches_threshold() -> None:
    vad = SimpleVAD(silence_ms_threshold=300, energy_threshold=10.0)
    silence_100ms = b"\x00\x00" * 1600

    assert vad.should_cut(silence_100ms, sample_rate=16000) is False
    assert vad.should_cut(silence_100ms, sample_rate=16000) is False
    assert vad.should_cut(silence_100ms, sample_rate=16000) is True
    assert vad.silence_acc_ms == 300


def test_simple_vad_voice_frame_resets_silence_accumulator() -> None:
    vad = SimpleVAD(silence_ms_threshold=300, energy_threshold=10.0)
    silence_100ms = b"\x00\x00" * 1600
    voice_100ms = b"\x64\x00" * 1600

    assert vad.should_cut(silence_100ms, sample_rate=16000) is False
    assert vad.should_cut(silence_100ms, sample_rate=16000) is False
    assert vad.silence_acc_ms == 200

    assert vad.should_cut(voice_100ms, sample_rate=16000) is False
    assert vad.silence_acc_ms == 0

    assert vad.should_cut(silence_100ms, sample_rate=16000) is False
    assert vad.should_cut(silence_100ms, sample_rate=16000) is False
    assert vad.silence_acc_ms == 200
