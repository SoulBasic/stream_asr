from __future__ import annotations

from pathlib import Path
import logging
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from server.asr_engine.engine_factory import create_engine
from server.asr_engine.qwen3_adapter import Qwen3ASREngine
from server.asr_engine.qwen_engine import MockQwenASREngine
from server.config import Settings


def test_factory_selects_mock_engine_when_configured() -> None:
    settings = Settings(asr_engine="mock")

    selected = create_engine(settings=settings, logger=logging.getLogger("test"))

    assert isinstance(selected.engine, MockQwenASREngine)
    assert selected.engine_name == "mock"
    assert selected.backend == "mock"
    assert selected.engine_fallback_reason is None


def test_factory_selects_qwen3_engine_when_dependency_available(monkeypatch) -> None:
    settings = Settings(asr_engine="qwen3")

    monkeypatch.setattr("server.asr_engine.engine_factory._ensure_qwen3_dependencies", lambda: None)

    selected = create_engine(settings=settings, logger=logging.getLogger("test"))

    assert isinstance(selected.engine, Qwen3ASREngine)
    assert selected.engine_name == "qwen3"
    assert selected.backend == "cpu"
    assert selected.engine_fallback_reason is None


def test_factory_falls_back_to_mock_when_qwen3_dependency_missing(monkeypatch) -> None:
    settings = Settings(asr_engine="qwen3")

    def _raise_import_error() -> None:
        raise ImportError("No module named 'qwen3_asr'")

    monkeypatch.setattr("server.asr_engine.engine_factory._ensure_qwen3_dependencies", _raise_import_error)

    selected = create_engine(settings=settings, logger=logging.getLogger("test"))

    assert isinstance(selected.engine, MockQwenASREngine)
    assert selected.engine_name == "mock"
    assert selected.backend == "mock"
    assert selected.engine_fallback_reason is not None
    assert "qwen3_dependency_unavailable" in selected.engine_fallback_reason
