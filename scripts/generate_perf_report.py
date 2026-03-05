#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass
class RunMetrics:
    run_dir: Path
    elapsed_ms: int
    audio_bytes: int
    partial_count: int
    first_token_latency_ms: list[int]
    sentence_latency_ms: list[int]


def _latest_run(root: Path) -> Path:
    if not root.exists():
        raise FileNotFoundError(f"root dir not found: {root}")
    runs = [p for p in root.iterdir() if p.is_dir()]
    if not runs:
        raise FileNotFoundError(f"no run dirs found under: {root}")
    return sorted(runs, key=lambda p: p.name)[-1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_stream_metrics(run_dir: Path) -> RunMetrics:
    summary = _load_json(run_dir / "summary.json")
    events_path = Path(summary.get("events_path") or run_dir / "events.jsonl")
    if not events_path.is_absolute():
        events_path = run_dir / events_path.name

    first_token: list[int] = []
    sentence_latency: list[int] = []

    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            metrics = event.get("metrics") or {}
            if "first_token_latency_ms" in metrics:
                first_token.append(int(metrics["first_token_latency_ms"]))
            if "sentence_latency_ms" in metrics:
                sentence_latency.append(int(metrics["sentence_latency_ms"]))

    return RunMetrics(
        run_dir=run_dir,
        elapsed_ms=int(summary.get("elapsed_ms", 0)),
        audio_bytes=int(summary.get("audio_bytes", 0)),
        partial_count=int(summary.get("partial_count", 0)),
        first_token_latency_ms=first_token,
        sentence_latency_ms=sentence_latency,
    )


def _safe_mean(values: list[int]) -> float | None:
    return round(mean(values), 2) if values else None


def _safe_p95(values: list[int]) -> int | None:
    if not values:
        return None
    sorted_values = sorted(values)
    idx = max(0, int(len(sorted_values) * 0.95) - 1)
    return sorted_values[idx]


def _resolve_http_metrics(smoke_run: Path, smoke_summary: dict[str, Any]) -> tuple[int | None, int | None]:
    elapsed_ms = smoke_summary.get("transcribe_elapsed_ms")
    audio_bytes = smoke_summary.get("audio_bytes")

    transcribe_path = smoke_run / "transcribe.json"
    if transcribe_path.exists():
        transcribe = _load_json(transcribe_path)
        if elapsed_ms is None:
            elapsed_ms = (transcribe.get("metrics") or {}).get("processing_ms")
        if audio_bytes is None:
            text = transcribe.get("text") or ""
            # 兼容早期 run 无原始 audio_bytes，至少给出近似文本大小信号（非严格音频字节）
            audio_bytes = smoke_summary.get("audio_bytes") or (len(text.encode("utf-8")) if text else None)

    return (int(elapsed_ms) if elapsed_ms is not None else None, int(audio_bytes) if audio_bytes is not None else None)


def generate_report(smoke_root: Path, stream_root: Path, out_dir: Path) -> dict[str, Any]:
    smoke_run = _latest_run(smoke_root)
    stream_run = _latest_run(stream_root)

    smoke_summary = _load_json(smoke_run / "summary.json")
    stream_metrics = _parse_stream_metrics(stream_run)
    http_elapsed_ms, http_audio_bytes = _resolve_http_metrics(smoke_run, smoke_summary)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline": "cpu",
        "http": {
            "run_dir": str(smoke_run),
            "result": smoke_summary.get("result"),
            "transcribe_elapsed_ms": http_elapsed_ms,
            "audio_bytes": http_audio_bytes,
        },
        "stream": {
            "run_dir": str(stream_run),
            "partial_count": stream_metrics.partial_count,
            "elapsed_ms": stream_metrics.elapsed_ms,
            "audio_bytes": stream_metrics.audio_bytes,
            "first_token_latency_mean_ms": _safe_mean(stream_metrics.first_token_latency_ms),
            "first_token_latency_p95_ms": _safe_p95(stream_metrics.first_token_latency_ms),
            "sentence_latency_mean_ms": _safe_mean(stream_metrics.sentence_latency_ms),
            "sentence_latency_p95_ms": _safe_p95(stream_metrics.sentence_latency_ms),
        },
        "gpu_placeholder": {
            "status": "pending-5090-validation",
            "notes": "Run same scripts on 5090 and fill comparable metrics.",
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "perf_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# 性能对比报告（模板）",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "## CPU 基线（已实测）",
        f"- HTTP run: `{report['http']['run_dir']}`",
        f"- HTTP transcribe elapsed(ms): `{report['http']['transcribe_elapsed_ms']}`",
        f"- Stream run: `{report['stream']['run_dir']}`",
        f"- Stream partial_count: `{report['stream']['partial_count']}`",
        f"- First token latency mean/p95(ms): `{report['stream']['first_token_latency_mean_ms']}` / `{report['stream']['first_token_latency_p95_ms']}`",
        f"- Sentence latency mean/p95(ms): `{report['stream']['sentence_latency_mean_ms']}` / `{report['stream']['sentence_latency_p95_ms']}`",
        "",
        "## GPU 5090（待实测）",
        "- 状态：pending-5090-validation",
        "- 方法：复用同一批音频、同一脚本，填入同结构指标即可横向对比",
    ]
    (out_dir / "PERF_REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate CPU baseline perf report from latest smoke artifacts")
    parser.add_argument("--smoke-root", type=Path, default=Path("logs/smoke_qwen3"))
    parser.add_argument("--stream-root", type=Path, default=Path("logs/stream_smoke_qwen3"))
    parser.add_argument("--out-dir", type=Path, default=Path("docs/perf"))
    args = parser.parse_args()

    report = generate_report(args.smoke_root, args.stream_root, args.out_dir)
    print(json.dumps({"result": "PASS", "out_dir": str(args.out_dir), "stream": report["stream"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
