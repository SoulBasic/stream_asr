from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseASREngine(ABC):
    def __init__(self, device: str) -> None:
        self.device = device
        self.model_loaded = True

    def engine_capabilities(self) -> dict[str, object]:
        return {
            "model_loaded": self.model_loaded,
            "is_placeholder": False,
        }

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, lang: str, sample_rate: int = 16000) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def stream_partial(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def stream_final(self, audio_bytes: bytes, lang: str, sample_rate: int) -> dict[str, Any]:
        raise NotImplementedError
