from __future__ import annotations

from pathlib import Path
import stat


def test_smoke_script_exists_and_executable() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_qwen3.sh"

    assert script.exists(), "smoke_qwen3.sh should exist"
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR, "smoke_qwen3.sh should be executable"


def test_smoke_script_contains_required_checks() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "smoke_qwen3.sh"
    content = script.read_text(encoding="utf-8")

    assert "ASR_ENGINE=qwen3" in content
    assert "/healthz" in content
    assert "engine_ready" in content
    assert "/v1/asr/transcribe" in content
