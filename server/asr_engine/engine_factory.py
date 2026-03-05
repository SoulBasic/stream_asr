from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from logging import Logger

from server.asr_engine.base import BaseASREngine
from server.asr_engine.qwen3_adapter import Qwen3ASREngine
from server.asr_engine.qwen_engine import MockQwenASREngine
from server.config import Settings


@dataclass(slots=True)
class EngineSelection:
    engine: BaseASREngine
    engine_name: str
    backend: str
    engine_fallback_reason: str | None


def _ensure_qwen3_dependencies() -> None:
    # Keep dependency checks lightweight for M2 bootstrap.
    try:
        import_module("qwen3_asr")
        return
    except Exception:
        pass
    import_module("qwen_asr")


def create_engine(settings: Settings, logger: Logger) -> EngineSelection:
    if settings.asr_engine == "qwen3":
        try:
            _ensure_qwen3_dependencies()
            return EngineSelection(
                engine=Qwen3ASREngine(device=settings.asr_device),
                engine_name="qwen3",
                backend="cpu",
                engine_fallback_reason=None,
            )
        except Exception as exc:
            reason = f"qwen3_dependency_unavailable: {exc}"
            logger.warning("engine_fallback requested=qwen3 selected=mock reason=%s", reason)
            return EngineSelection(
                engine=MockQwenASREngine(device=settings.asr_device),
                engine_name="mock",
                backend="mock",
                engine_fallback_reason=reason,
            )

    return EngineSelection(
        engine=MockQwenASREngine(device=settings.asr_device),
        engine_name="mock",
        backend="mock",
        engine_fallback_reason=None,
    )
