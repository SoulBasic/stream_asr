from __future__ import annotations

import asyncio
from time import perf_counter

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

router = APIRouter(prefix="/v1/asr", tags=["asr"])
MIN_AUDIO_BYTES = 320


@router.post("/transcribe")
async def transcribe(request: Request, file: UploadFile = File(...), lang: str = Form("zh")) -> dict[str, object]:
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="empty file")
    if len(audio) % 2 != 0:
        raise HTTPException(status_code=400, detail="invalid pcm16 payload")
    if len(audio) < MIN_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="audio too short")

    start = perf_counter()
    timeout_s = request.app.state.settings.transcribe_timeout_ms / 1000.0
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(request.app.state.engine.transcribe, audio, lang=lang, sample_rate=16000),
            timeout=timeout_s,
        )
    except TimeoutError:
        request.app.state.logger.warning(
            "transcribe_timeout filename=%s bytes=%s lang=%s timeout_ms=%s",
            file.filename,
            len(audio),
            lang,
            request.app.state.settings.transcribe_timeout_ms,
        )
        raise HTTPException(status_code=504, detail="asr transcribe timeout")
    except Exception:
        request.app.state.logger.exception(
            "transcribe_failed filename=%s bytes=%s lang=%s",
            file.filename,
            len(audio),
            lang,
        )
        raise HTTPException(status_code=503, detail="asr engine unavailable")

    cost_ms = int((perf_counter() - start) * 1000)

    request.app.state.logger.info(
        "transcribe filename=%s bytes=%s lang=%s processing_ms=%s",
        file.filename,
        len(audio),
        lang,
        cost_ms,
    )

    return {
        "text": result["text"],
        "segments": result["segments"],
        "metrics": {"processing_ms": cost_ms},
    }
