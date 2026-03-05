from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import time


REQUIRED_FILES = ("summary.json", "healthz.json", "transcribe.json", "uvicorn.log")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _verify_summary_consistency(summary: dict[str, Any], run_dir: Path) -> None:
    # smoke 脚本会写入这些路径字段；离线验收时应与当前 run_dir 一致
    summary_run_dir = summary.get("run_dir")
    if summary_run_dir is not None:
        _assert(Path(summary_run_dir).resolve() == run_dir.resolve(), "summary.run_dir mismatches input run_dir")

    path_checks = {
        "healthz_path": run_dir / "healthz.json",
        "transcribe_path": run_dir / "transcribe.json",
        "uvicorn_log": run_dir / "uvicorn.log",
    }
    for key, expected_path in path_checks.items():
        value = summary.get(key)
        if value is None:
            continue
        _assert(Path(value).resolve() == expected_path.resolve(), f"summary.{key} mismatches artifact path")


def _verify_transcribe_segments(segments: Any) -> None:
    _assert(isinstance(segments, list) and len(segments) >= 1, "transcribe.segments must be non-empty list")
    for i, seg in enumerate(segments):
        _assert(isinstance(seg, dict), f"transcribe.segments[{i}] must be object")
        _assert("start_ms" in seg and "end_ms" in seg and "text" in seg, f"transcribe.segments[{i}] missing required keys")

        start_ms = seg.get("start_ms")
        end_ms = seg.get("end_ms")
        text = seg.get("text")

        _assert(isinstance(start_ms, int) and start_ms >= 0, f"transcribe.segments[{i}].start_ms must be non-negative int")
        _assert(isinstance(end_ms, int) and end_ms >= start_ms, f"transcribe.segments[{i}].end_ms must be int and >= start_ms")
        _assert(isinstance(text, str) and text.strip() != "", f"transcribe.segments[{i}].text must be non-empty string")


def _resolve_latest_run_dir(root_dir: Path) -> Path:
    _assert(root_dir.exists() and root_dir.is_dir(), f"root_dir not found: {root_dir}")
    candidates = [p for p in root_dir.iterdir() if p.is_dir()]
    _assert(len(candidates) > 0, f"no run directories found under: {root_dir}")
    # 优先按目录名排序（smoke_qwen3.sh 采用时间戳命名）；回退到 mtime 以兼容手工目录
    candidates.sort(key=lambda p: (p.name, p.stat().st_mtime), reverse=True)
    return candidates[0]


def _assert_run_fresh(run_dir: Path, max_age_minutes: int) -> None:
    _assert(max_age_minutes > 0, "max_age_minutes must be > 0")
    age_seconds = time.time() - run_dir.stat().st_mtime
    _assert(
        age_seconds <= max_age_minutes * 60,
        f"run_dir too old: age={age_seconds:.0f}s exceeds {max_age_minutes} minutes",
    )


def verify_run_dir(run_dir: Path) -> list[str]:
    notes: list[str] = []

    _assert(run_dir.exists() and run_dir.is_dir(), f"run_dir not found: {run_dir}")
    for filename in REQUIRED_FILES:
        file_path = run_dir / filename
        _assert(file_path.exists(), f"missing required artifact: {filename}")
        _assert(file_path.stat().st_size > 0, f"empty artifact: {filename}")

    summary = _load_json(run_dir / "summary.json")
    healthz = _load_json(run_dir / "healthz.json")
    transcribe = _load_json(run_dir / "transcribe.json")

    _assert(summary.get("result") == "PASS", "summary.result must be PASS")
    _assert(summary.get("fail_count") == 0, "summary.fail_count must be 0")
    _assert(summary.get("pass_count", 0) >= 3, "summary.pass_count should be >= 3")
    _verify_summary_consistency(summary, run_dir)

    _assert(healthz.get("engine") == "qwen3", "healthz.engine must be qwen3")
    _assert(healthz.get("engine_ready") is True, "healthz.engine_ready must be true")
    capabilities = healthz.get("engine_capabilities")
    _assert(isinstance(capabilities, dict), "healthz.engine_capabilities must be object")
    _assert(
        capabilities.get("model_source") in {"qwen3_asr", "qwen_asr"},
        "healthz.engine_capabilities.model_source must be qwen3_asr|qwen_asr",
    )
    _assert(capabilities.get("is_placeholder") is False, "healthz.engine_capabilities.is_placeholder must be false")
    _assert(healthz.get("engine_fallback_reason") is None, "healthz.engine_fallback_reason must be null")

    text = transcribe.get("text")
    segments = transcribe.get("segments")
    metrics = transcribe.get("metrics")
    _assert(isinstance(text, str) and text.strip() != "", "transcribe.text must be non-empty string")
    _verify_transcribe_segments(segments)
    _assert(isinstance(metrics, dict) and "processing_ms" in metrics, "transcribe.metrics.processing_ms missing")

    notes.append("verify summary.json: PASS + artifact path consistency")
    notes.append("verify healthz.json: engine_ready=true")
    notes.append("verify transcribe.json: text/segments/metrics valid")
    return notes


def _json_report(result: str, run_dir: Path | None, notes: list[str], error: str | None = None) -> str:
    payload: dict[str, Any] = {
        "result": result,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "notes": notes,
    }
    if error is not None:
        payload["error"] = error
    return json.dumps(payload, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify artifacts generated by scripts/smoke_qwen3.sh")
    parser.add_argument("run_dir", type=Path, nargs="?", help="Path to logs/smoke_qwen3/<timestamp> directory")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Verify latest run dir under --root-dir (default: logs/smoke_qwen3)",
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=Path("logs/smoke_qwen3"),
        help="Root dir containing smoke run directories (used by --latest)",
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=None,
        help="Optional freshness check for selected run directory",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON result for CI usage",
    )
    args = parser.parse_args()

    target_run_dir: Path | None = None
    try:
        if args.latest:
            target_run_dir = _resolve_latest_run_dir(args.root_dir)
        else:
            _assert(args.run_dir is not None, "run_dir is required unless --latest is used")
            target_run_dir = args.run_dir

        if args.max_age_minutes is not None:
            _assert_run_fresh(target_run_dir, args.max_age_minutes)

        notes = verify_run_dir(target_run_dir)
    except Exception as exc:  # pragma: no cover - CLI path
        if args.json:
            print(_json_report("FAIL", target_run_dir, [], str(exc)))
        else:
            print(f"FAIL: {exc}")
        return 1

    if args.json:
        print(_json_report("PASS", target_run_dir, notes))
    else:
        print(f"PASS: artifact verification ok ({target_run_dir})")
        for item in notes:
            print(f" - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
