from __future__ import annotations

import asyncio
import json
from time import monotonic
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["asr"])


@router.websocket("/v1/asr/stream")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    app = websocket.app
    logger = app.state.logger
    engine = app.state.engine
    settings = app.state.settings
    partial_threshold = settings.partial_bytes_threshold
    partial_interval_s = settings.partial_interval_ms / 1000.0
    ws_idle_timeout_s = settings.ws_idle_timeout_ms / 1000.0
    min_sample_rate = 8000
    max_sample_rate = 48000
    min_audio_bytes = 320

    started = False
    session_id = ""
    lang = "zh"
    sample_rate = 16000
    audio_buffer = bytearray()
    last_partial_size = 0
    last_partial_at = monotonic()
    session_started_at = 0.0
    first_partial_sent = False

    async def send_error(code: str, message: str) -> None:
        await websocket.send_json({"type": "error", "code": code, "message": message})

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=ws_idle_timeout_s)
            except TimeoutError:
                await send_error("SESSION_IDLE_TIMEOUT", "no message received within idle timeout")
                logger.warning("ws_idle_timeout session_id=%s timeout_ms=%s", session_id, settings.ws_idle_timeout_ms)
                await websocket.close()
                return
            msg_type = message.get("type")

            if msg_type == "websocket.disconnect":
                break

            text_payload = message.get("text")
            if text_payload is not None:
                try:
                    event = json.loads(text_payload)
                except json.JSONDecodeError:
                    await send_error("BAD_JSON", "invalid json")
                    continue

                if not isinstance(event, dict):
                    await send_error("BAD_JSON", "json payload must be an object")
                    continue

                event_type = event.get("type")
                if event_type == "start":
                    sample_rate_raw = event.get("sample_rate")
                    if sample_rate_raw is None:
                        await send_error("BAD_START", "sample_rate is required")
                        continue
                    try:
                        parsed_sample_rate = int(sample_rate_raw)
                    except (TypeError, ValueError):
                        await send_error("BAD_START", "sample_rate must be an integer")
                        continue
                    if not (min_sample_rate <= parsed_sample_rate <= max_sample_rate):
                        await send_error(
                            "BAD_START",
                            f"sample_rate out of range [{min_sample_rate}, {max_sample_rate}]",
                        )
                        continue

                    started = True
                    session_id = event.get("session_id") or f"sess_{uuid4().hex[:8]}"
                    lang = event.get("lang", "zh")
                    sample_rate = parsed_sample_rate
                    audio_buffer.clear()
                    last_partial_size = 0
                    last_partial_at = monotonic()
                    session_started_at = last_partial_at
                    first_partial_sent = False
                    await websocket.send_json(
                        {
                            "type": "status",
                            "message": "session_started",
                            "session_id": session_id,
                            "sample_rate": sample_rate,
                            "lang": lang,
                        }
                    )
                    logger.info("ws_start session_id=%s sample_rate=%s lang=%s", session_id, sample_rate, lang)
                    continue

                if event_type == "stop":
                    if not started:
                        await send_error("BAD_AUDIO_STATE", "start required before stop")
                        continue
                    if not audio_buffer:
                        await send_error("BAD_AUDIO_STATE", "no audio received before stop")
                        continue
                    if len(audio_buffer) < min_audio_bytes:
                        await send_error("BAD_AUDIO_TOO_SHORT", "audio too short")
                        continue
                    final_result = engine.stream_final(bytes(audio_buffer), lang=lang, sample_rate=sample_rate)
                    sentence_latency_ms = int((monotonic() - session_started_at) * 1000)
                    await websocket.send_json(
                        {
                            "type": "final",
                            **final_result,
                            "metrics": {
                                "sentence_latency_ms": sentence_latency_ms,
                            },
                        }
                    )
                    logger.info(
                        "ws_stop session_id=%s bytes=%s sentence_latency_ms=%s",
                        session_id,
                        len(audio_buffer),
                        sentence_latency_ms,
                    )
                    await websocket.close()
                    return

                await send_error("BAD_JSON", "supported text events: start/stop")
                continue

            chunk = message.get("bytes")
            if chunk is not None:
                if not started:
                    await send_error("BAD_AUDIO_STATE", "send start event first")
                    continue
                if len(chunk) % 2 != 0:
                    await send_error("BAD_AUDIO_FORMAT", "pcm16 payload must be even-length bytes")
                    continue

                audio_buffer.extend(chunk)
                now = monotonic()
                bytes_trigger = len(audio_buffer) - last_partial_size >= partial_threshold
                time_trigger = now - last_partial_at >= partial_interval_s and len(audio_buffer) > last_partial_size
                if bytes_trigger or time_trigger:
                    partial_result = engine.stream_partial(bytes(audio_buffer), lang=lang, sample_rate=sample_rate)
                    first_token_latency_ms = int((now - session_started_at) * 1000)
                    await websocket.send_json(
                        {
                            "type": "partial",
                            **partial_result,
                            "metrics": {
                                "first_token_latency_ms": first_token_latency_ms,
                            },
                        }
                    )
                    if not first_partial_sent:
                        logger.info(
                            "ws_first_partial session_id=%s bytes=%s first_token_latency_ms=%s",
                            session_id,
                            len(audio_buffer),
                            first_token_latency_ms,
                        )
                        first_partial_sent = True
                    last_partial_size = len(audio_buffer)
                    last_partial_at = now
                continue
    except WebSocketDisconnect:
        logger.info("ws_disconnect session_id=%s", session_id)
    except Exception:
        logger.exception("ws_error session_id=%s", session_id)
        try:
            await send_error("INTERNAL_ERROR", "internal error")
        except Exception:
            pass
