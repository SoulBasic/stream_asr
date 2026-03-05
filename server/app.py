from __future__ import annotations

from fastapi import FastAPI

from server.asr_engine.engine_factory import create_engine
from server.config import Settings
from server.logger import setup_logging
from server.routes.transcribe import router as transcribe_router
from server.routes.ws_stream import router as ws_router


def create_app() -> FastAPI:
    settings = Settings.from_env()
    logger = setup_logging(settings.log_path, settings.log_level)
    engine_selection = create_engine(settings=settings, logger=logger)

    app = FastAPI(title="stream_asr", version="0.1.0")
    app.state.settings = settings
    app.state.logger = logger
    app.state.engine = engine_selection.engine
    app.state.engine_name = engine_selection.engine_name
    app.state.engine_fallback_reason = engine_selection.engine_fallback_reason
    app.state.engine_backend = engine_selection.backend

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        capabilities = engine_selection.engine.engine_capabilities()
        runtime_or_probe_fallback = capabilities.get("fallback_reason")
        fallback_reason = runtime_or_probe_fallback or engine_selection.engine_fallback_reason
        is_placeholder = bool(capabilities.get("is_placeholder", False))
        engine_ready = bool(engine_selection.engine.model_loaded) and not is_placeholder and fallback_reason is None
        return {
            "ok": True,
            "device": settings.asr_device,
            "model_loaded": engine_selection.engine.model_loaded,
            "engine_ready": engine_ready,
            "engine_capabilities": capabilities,
            "engine": engine_selection.engine_name,
            "backend": engine_selection.backend,
            "engine_fallback_reason": fallback_reason,
        }

    app.include_router(transcribe_router)
    app.include_router(ws_router)
    logger.info(
        "app_started device=%s engine=%s fallback_reason=%s log_path=%s",
        settings.asr_device,
        engine_selection.engine_name,
        engine_selection.engine_fallback_reason,
        settings.log_path,
    )
    return app


app = create_app()
