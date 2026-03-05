from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _make_run(root: Path, name: str, summary: dict, events: list[dict] | None = None) -> Path:
    run = root / name
    run.mkdir(parents=True, exist_ok=True)
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    if events is not None:
        with (run / "events.jsonl").open("w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return run


def test_generate_perf_report_cli(tmp_path: Path) -> None:
    smoke_root = tmp_path / "smoke"
    stream_root = tmp_path / "stream"
    out_dir = tmp_path / "out"

    _make_run(
        smoke_root,
        "20260305_100000",
        {
            "result": "PASS",
            "transcribe_elapsed_ms": 123,
            "audio_bytes": 32000,
        },
    )
    _make_run(
        stream_root,
        "20260305_100000",
        {
            "result": "PASS",
            "elapsed_ms": 880,
            "audio_bytes": 64000,
            "partial_count": 3,
            "events_path": "events.jsonl",
        },
        events=[
            {"type": "partial", "metrics": {"first_token_latency_ms": 180}},
            {"type": "partial", "metrics": {"first_token_latency_ms": 220}},
            {"type": "final", "metrics": {"sentence_latency_ms": 900}},
        ],
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "generate_perf_report.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--smoke-root",
            str(smoke_root),
            "--stream-root",
            str(stream_root),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert (out_dir / "perf_report.json").exists()
    assert (out_dir / "PERF_REPORT.md").exists()

    report = json.loads((out_dir / "perf_report.json").read_text(encoding="utf-8"))
    assert report["http"]["transcribe_elapsed_ms"] == 123
    assert report["stream"]["first_token_latency_mean_ms"] == 200.0
    assert report["stream"]["sentence_latency_p95_ms"] == 900
