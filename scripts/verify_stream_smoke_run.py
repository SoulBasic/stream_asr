from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

REQUIRED_FILES = ("summary.json", "events.jsonl")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    _assert(isinstance(data, dict), f"JSON root must be object: {path}")
    return data


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"events.jsonl line {idx} is not valid JSON: {exc}") from exc
            _assert(isinstance(obj, dict), f"events.jsonl line {idx} must be object")
            events.append(obj)
    _assert(len(events) > 0, "events.jsonl must contain at least 1 event")
    return events


def _resolve_latest_run_dir(root_dir: Path) -> Path:
    _assert(root_dir.exists() and root_dir.is_dir(), f"root_dir not found: {root_dir}")
    candidates = [p for p in root_dir.iterdir() if p.is_dir()]
    _assert(len(candidates) > 0, f"no run directories found under: {root_dir}")
    candidates.sort(key=lambda p: (p.name, p.stat().st_mtime), reverse=True)
    return candidates[0]


def _assert_run_fresh(run_dir: Path, max_age_minutes: int) -> None:
    _assert(max_age_minutes > 0, "max_age_minutes must be > 0")
    age_seconds = time.time() - run_dir.stat().st_mtime
    _assert(
        age_seconds <= max_age_minutes * 60,
        f"run_dir too old: age={age_seconds:.0f}s exceeds {max_age_minutes} minutes",
    )


def _verify_summary(summary: dict[str, Any], run_dir: Path) -> None:
    _assert(summary.get("result") == "PASS", "summary.result must be PASS")
    _assert(isinstance(summary.get("partial_count"), int), "summary.partial_count must be int")
    _assert(summary.get("partial_count", 0) >= 1, "summary.partial_count must be >= 1")
    _assert(isinstance(summary.get("events"), int) and summary.get("events") >= 3, "summary.events must be >= 3")

    summary_run_dir = summary.get("run_dir")
    if summary_run_dir is not None:
        _assert(Path(summary_run_dir).resolve() == run_dir.resolve(), "summary.run_dir mismatches input run_dir")

    events_path = summary.get("events_path")
    if events_path is not None:
        _assert(Path(events_path).resolve() == (run_dir / "events.jsonl").resolve(), "summary.events_path mismatches artifact path")


def _verify_event_sequence(events: list[dict[str, Any]]) -> None:
    types = [e.get("type") for e in events]
    _assert(types[0] in {"status", "start", "session_started"}, "first event must be session start/status")
    _assert("final" in types, "events must contain final event")

    first_final_idx = types.index("final")
    partials_before_final = [e for e in events[:first_final_idx] if e.get("type") == "partial"]
    _assert(len(partials_before_final) >= 1, "must have at least 1 partial event before final")

    prev_end_ms = -1
    for idx, event in enumerate(events, start=1):
        event_type = event.get("type")
        if event_type not in {"partial", "final"}:
            continue

        _assert("start_ms" in event and "end_ms" in event and "text" in event, f"event #{idx} missing start_ms/end_ms/text")
        start_ms = event.get("start_ms")
        end_ms = event.get("end_ms")
        text = event.get("text")

        _assert(isinstance(start_ms, int) and start_ms >= 0, f"event #{idx} start_ms must be non-negative int")
        _assert(isinstance(end_ms, int) and end_ms >= start_ms, f"event #{idx} end_ms must be int and >= start_ms")
        _assert(isinstance(text, str) and text.strip() != "", f"event #{idx} text must be non-empty string")
        _assert(end_ms >= prev_end_ms, f"event #{idx} end_ms must be monotonic non-decreasing")
        prev_end_ms = end_ms

        metrics = event.get("metrics")
        _assert(isinstance(metrics, dict), f"event #{idx} metrics must be object")
        if event_type == "partial":
            _assert("first_token_latency_ms" in metrics, f"partial event #{idx} missing metrics.first_token_latency_ms")
            _assert(
                isinstance(metrics.get("first_token_latency_ms"), int)
                and metrics.get("first_token_latency_ms") >= 0,
                f"partial event #{idx} metrics.first_token_latency_ms must be non-negative int",
            )
        if event_type == "final":
            _assert("sentence_latency_ms" in metrics, f"final event #{idx} missing metrics.sentence_latency_ms")
            _assert(
                isinstance(metrics.get("sentence_latency_ms"), int)
                and metrics.get("sentence_latency_ms") >= 0,
                f"final event #{idx} metrics.sentence_latency_ms must be non-negative int",
            )


def verify_run_dir(run_dir: Path) -> list[str]:
    notes: list[str] = []
    _assert(run_dir.exists() and run_dir.is_dir(), f"run_dir not found: {run_dir}")

    for filename in REQUIRED_FILES:
        file_path = run_dir / filename
        _assert(file_path.exists(), f"missing required artifact: {filename}")
        _assert(file_path.stat().st_size > 0, f"empty artifact: {filename}")

    summary = _load_json(run_dir / "summary.json")
    events = _load_jsonl(run_dir / "events.jsonl")

    _verify_summary(summary, run_dir)
    _verify_event_sequence(events)

    notes.append("verify summary.json: PASS + run/events_path consistency")
    notes.append("verify events.jsonl: start/partial/final sequence valid")
    notes.append("verify stream metrics: first_token_latency_ms/sentence_latency_ms valid")
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
    parser = argparse.ArgumentParser(description="Verify artifacts generated by scripts/stream_smoke_qwen3.py")
    parser.add_argument("run_dir", type=Path, nargs="?", help="Path to logs/stream_smoke_qwen3/<timestamp> directory")
    parser.add_argument("--latest", action="store_true", help="Verify latest run dir under --root-dir")
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=Path("logs/stream_smoke_qwen3"),
        help="Root dir containing stream smoke run directories (used by --latest)",
    )
    parser.add_argument("--max-age-minutes", type=int, default=None, help="Optional freshness check for selected run directory")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result for CI usage")
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
        print(f"PASS: stream artifact verification ok ({target_run_dir})")
        for item in notes:
            print(f" - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
