from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from scripts.verify_stream_smoke_run import _assert_run_fresh, _resolve_latest_run_dir, verify_run_dir


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_valid_stream_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "summary.json",
        {
            "result": "PASS",
            "run_dir": str(run_dir),
            "events": 4,
            "partial_count": 2,
            "events_path": str(run_dir / "events.jsonl"),
        },
    )

    events = [
        {"type": "status", "message": "session_started"},
        {
            "type": "partial",
            "text": "p1",
            "start_ms": 0,
            "end_ms": 800,
            "metrics": {"first_token_latency_ms": 120},
        },
        {
            "type": "partial",
            "text": "p2",
            "start_ms": 0,
            "end_ms": 1600,
            "metrics": {"first_token_latency_ms": 250},
        },
        {
            "type": "final",
            "text": "f",
            "start_ms": 0,
            "end_ms": 2000,
            "metrics": {"sentence_latency_ms": 500},
        },
    ]
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_verify_stream_run_dir_pass(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260304_124752"
    _make_valid_stream_run(run_dir)

    notes = verify_run_dir(run_dir)
    assert len(notes) >= 3


def test_verify_stream_run_dir_fails_when_final_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260304_124752"
    _make_valid_stream_run(run_dir)

    events_path = run_dir / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    events_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    try:
        verify_run_dir(run_dir)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "final" in str(exc)


def test_resolve_latest_and_freshness(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    older = root / "20260304_120000"
    newer = root / "20260304_130000"
    _make_valid_stream_run(older)
    _make_valid_stream_run(newer)

    resolved = _resolve_latest_run_dir(root)
    assert resolved == newer

    old_mtime = time.time() - 3600
    old_run = root / "20260304_090000"
    _make_valid_stream_run(old_run)
    old_run.touch()
    (old_run / "summary.json").touch()
    (old_run / "events.jsonl").touch()
    import os

    os.utime(old_run, (old_mtime, old_mtime))
    try:
        _assert_run_fresh(old_run, max_age_minutes=5)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "too old" in str(exc)


def test_verify_stream_cli_json_pass(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260304_124752"
    _make_valid_stream_run(run_dir)

    cmd = [
        sys.executable,
        "scripts/verify_stream_smoke_run.py",
        str(run_dir),
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout.strip())
    assert payload["result"] == "PASS"


def test_verify_stream_cli_json_fail(tmp_path: Path) -> None:
    bad_run = tmp_path / "bad"
    bad_run.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "scripts/verify_stream_smoke_run.py",
        str(bad_run),
        "--json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode != 0
    payload = json.loads(proc.stdout.strip())
    assert payload["result"] == "FAIL"
    assert "missing required artifact" in payload["error"]
