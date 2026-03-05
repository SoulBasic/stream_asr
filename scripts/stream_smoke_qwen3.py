#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

import websockets


def _chunk_bytes(audio: bytes, chunk_size: int) -> list[bytes]:
    return [audio[i : i + chunk_size] for i in range(0, len(audio), chunk_size)]


def _read_wav_pcm16(path: Path) -> tuple[bytes, int, int, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        audio = wf.readframes(frames)
    if sample_width != 2:
        raise ValueError(f"only PCM16 wav is supported, got sample_width={sample_width}")
    return audio, sample_rate, channels, sample_width


async def _run_stream(
    base_url: str,
    audio_path: Path,
    lang: str,
    chunk_ms: int,
    out_root: Path,
) -> dict[str, Any]:
    audio, sample_rate, channels, sample_width = _read_wav_pcm16(audio_path)
    bytes_per_ms = int(sample_rate * channels * sample_width / 1000)
    chunk_size = max(1, bytes_per_ms * chunk_ms)
    chunks = _chunk_bytes(audio, chunk_size)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    events_path = run_dir / "events.jsonl"
    summary_path = run_dir / "summary.json"

    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://") + "/v1/asr/stream"

    started_at = time.monotonic()
    partial_count = 0
    final_event: dict[str, Any] | None = None
    all_events: list[dict[str, Any]] = []

    async with websockets.connect(ws_url, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "start", "sample_rate": sample_rate, "lang": lang}))
        start_ack = json.loads(await ws.recv())
        all_events.append(start_ack)

        for chunk in chunks:
            await ws.send(chunk)
            # 尝试读尽当前可得消息，避免最后 stop 前堆积
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.02)
                except asyncio.TimeoutError:
                    break
                event = json.loads(msg)
                all_events.append(event)
                if event.get("type") == "partial":
                    partial_count += 1

        await ws.send(json.dumps({"type": "stop"}))
        while True:
            msg = await ws.recv()
            event = json.loads(msg)
            all_events.append(event)
            if event.get("type") == "partial":
                partial_count += 1
            if event.get("type") == "final":
                final_event = event
                break

    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    with events_path.open("w", encoding="utf-8") as f:
        for event in all_events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    result = "PASS"
    notes: list[str] = []
    if final_event is None:
        result = "FAIL"
        notes.append("missing final event")
    if partial_count < 1:
        result = "FAIL"
        notes.append("partial_count < 1")

    summary = {
        "result": result,
        "run_dir": str(run_dir),
        "audio_path": str(audio_path),
        "audio_bytes": len(audio),
        "sample_rate": sample_rate,
        "channels": channels,
        "chunk_ms": chunk_ms,
        "chunk_size": chunk_size,
        "chunks": len(chunks),
        "events": len(all_events),
        "partial_count": partial_count,
        "final_text": (final_event or {}).get("text", ""),
        "elapsed_ms": elapsed_ms,
        "events_path": str(events_path),
        "notes": notes,
    }

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run qwen3 stream smoke test and save artifacts")
    parser.add_argument("--audio", required=True, type=Path, help="PCM16 wav audio path")
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--lang", default="zh")
    parser.add_argument("--chunk-ms", default=120, type=int)
    parser.add_argument("--out-dir", default="logs/stream_smoke_qwen3", type=Path)
    args = parser.parse_args()

    summary = asyncio.run(
        _run_stream(
            base_url=args.base_url.rstrip("/"),
            audio_path=args.audio,
            lang=args.lang,
            chunk_ms=args.chunk_ms,
            out_root=args.out_dir,
        )
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary.get("result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
