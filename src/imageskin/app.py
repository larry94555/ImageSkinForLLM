"""FastAPI application: the JSON API under /api and the browser app at /."""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from imageskin import __version__
from imageskin.config import default_home
from imageskin.consent import load_consent, save_consent

logger = logging.getLogger(__name__)

# Built from web/ (React + TypeScript) by `npm run build`; the built files are committed.
STATIC_DIR = Path(__file__).parent / "static"


class ConsentRequest(BaseModel):
    agreed: bool


def create_app(home: Path | None = None) -> FastAPI:
    app = FastAPI(title="ImageSkinForLLM", version=__version__)
    data_home = home or default_home()

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Request failed",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        logger.info(
            "Request handled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/consent")
    def get_consent() -> dict[str, object]:
        return asdict(load_consent(data_home))

    @app.post("/api/consent")
    def post_consent(body: ConsentRequest) -> dict[str, object]:
        if not body.agreed:
            raise HTTPException(status_code=400, detail="Tick the box to confirm consent.")
        return asdict(save_consent(data_home))

    # Last, so /health and /api routes win over the static files.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
