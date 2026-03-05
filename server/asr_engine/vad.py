from __future__ import annotations

from array import array


class SimpleVAD:
    """Lightweight energy-based VAD placeholder."""

    def __init__(self, silence_ms_threshold: int = 500, energy_threshold: float = 500.0) -> None:
        self.silence_ms_threshold = max(0, int(silence_ms_threshold))
        self.energy_threshold = max(0.0, float(energy_threshold))
        self._silence_acc_ms = 0

    @property
    def silence_acc_ms(self) -> int:
        return self._silence_acc_ms

    def reset(self) -> None:
        self._silence_acc_ms = 0

    def _mean_abs_energy(self, pcm_bytes: bytes) -> float:
        if len(pcm_bytes) < 2:
            return 0.0
        even_len = len(pcm_bytes) - (len(pcm_bytes) % 2)
        samples = array("h")
        samples.frombytes(pcm_bytes[:even_len])
        if not samples:
            return 0.0
        return sum(abs(sample) for sample in samples) / len(samples)

    def should_cut(self, pcm_bytes: bytes, sample_rate: int = 16000) -> bool:
        if sample_rate <= 0:
            return False

        sample_count = len(pcm_bytes) // 2
        if sample_count == 0:
            return False

        frame_ms = int(sample_count * 1000 / sample_rate)
        if frame_ms <= 0:
            return False

        energy = self._mean_abs_energy(pcm_bytes)
        if energy < self.energy_threshold:
            self._silence_acc_ms += frame_ms
        else:
            self._silence_acc_ms = 0

        return self._silence_acc_ms >= self.silence_ms_threshold > 0
