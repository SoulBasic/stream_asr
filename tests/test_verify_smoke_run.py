from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.verify_smoke_run import verify_run_dir, _resolve_latest_run_dir, _assert_run_fresh


def _write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _build_valid_run_dir(run_dir: Path) -> None:
    _write(
        run_dir / "summary.json",
        {
            "result": "PASS",
            "pass_count": 3,
            "fail_count": 0,
            "run_dir": str(run_dir),
            "healthz_path": str(run_dir / "healthz.json"),
            "transcribe_path": str(run_dir / "transcribe.json"),
            "uvicorn_log": str(run_dir / "uvicorn.log"),
        },
    )
    _write(
        run_dir / "healthz.json",
        {
            "engine": "qwen3",
            "engine_ready": True,
            "engine_fallback_reason": None,
            "engine_capabilities": {
                "model_source": "qwen3_asr",
                "is_placeholder": False,
            },
        },
    )
    _write(
        run_dir / "transcribe.json",
        {
            "text": "hello",
            "segments": [{"start_ms": 0, "end_ms": 1000, "text": "hello"}],
            "metrics": {"processing_ms": 10},
        },
    )
    (run_dir / "uvicorn.log").write_text("ok", encoding="utf-8")


def test_verify_smoke_run_pass(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260303_235959"
    run_dir.mkdir(parents=True)
    _build_valid_run_dir(run_dir)

    notes = verify_run_dir(run_dir)
    assert len(notes) == 3


def test_verify_smoke_run_fail_on_healthz_not_ready(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260303_235959"
    run_dir.mkdir(parents=True)
    _build_valid_run_dir(run_dir)

    _write(
        run_dir / "healthz.json",
        {
            "engine": "qwen3",
            "engine_ready": False,
            "engine_fallback_reason": "qwen3_transcribe_failed",
            "engine_capabilities": {
                "model_source": "qwen3_asr",
                "is_placeholder": True,
            },
        },
    )

    try:
        verify_run_dir(run_dir)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "engine_ready" in str(exc)


def test_verify_smoke_run_fail_on_segment_schema_invalid(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260303_235959"
    run_dir.mkdir(parents=True)
    _build_valid_run_dir(run_dir)

    _write(
        run_dir / "transcribe.json",
        {
            "text": "hello",
            "segments": [{"start_ms": 100, "end_ms": 90, "text": "hello"}],
            "metrics": {"processing_ms": 10},
        },
    )

    try:
        verify_run_dir(run_dir)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "end_ms" in str(exc)


def test_verify_smoke_run_fail_on_summary_path_mismatch(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260303_235959"
    run_dir.mkdir(parents=True)
    _build_valid_run_dir(run_dir)

    _write(
        run_dir / "summary.json",
        {
            "result": "PASS",
            "pass_count": 3,
            "fail_count": 0,
            "run_dir": str(tmp_path / "wrong_run_dir"),
            "healthz_path": str(run_dir / "healthz.json"),
            "transcribe_path": str(run_dir / "transcribe.json"),
            "uvicorn_log": str(run_dir / "uvicorn.log"),
        },
    )

    try:
        verify_run_dir(run_dir)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "summary.run_dir" in str(exc)


def test_resolve_latest_run_dir_selects_latest_by_name(tmp_path: Path) -> None:
    old_dir = tmp_path / "20260303_235959"
    new_dir = tmp_path / "20260304_001500"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    latest = _resolve_latest_run_dir(tmp_path)
    assert latest == new_dir


def test_assert_run_fresh_fail_when_too_old(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260303_235959"
    run_dir.mkdir(parents=True)

    # 把 mtime 调到 2 小时前
    old_ts = run_dir.stat().st_mtime - 7200
    run_dir.touch()
    import os

    os.utime(run_dir, (old_ts, old_ts))

    try:
        _assert_run_fresh(run_dir, 30)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "too old" in str(exc)


def test_verify_smoke_run_cli_json_pass(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260304_011500"
    run_dir.mkdir(parents=True)
    _build_valid_run_dir(run_dir)

    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/verify_smoke_run.py", str(run_dir), "--json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["result"] == "PASS"
    assert payload["run_dir"] == str(run_dir)
    assert len(payload["notes"]) == 3


def test_verify_smoke_run_cli_json_fail(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260304_011501"
    run_dir.mkdir(parents=True)
    _build_valid_run_dir(run_dir)

    _write(
        run_dir / "healthz.json",
        {
            "engine": "qwen3",
            "engine_ready": False,
            "engine_fallback_reason": "qwen3_transcribe_failed",
            "engine_capabilities": {
                "model_source": "qwen3_asr",
                "is_placeholder": True,
            },
        },
    )

    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/verify_smoke_run.py", str(run_dir), "--json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["result"] == "FAIL"
    assert payload["run_dir"] == str(run_dir)
    assert "engine_ready" in payload["error"]
