"""FastAPI application: the JSON API under /api and the browser app at /."""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from imageskin import __version__
from imageskin.config import default_home
from imageskin.consent import load_consent, save_consent
from imageskin.uploads import MEDIA_TYPE, Kind, Upload, UploadError, UploadStore

logger = logging.getLogger(__name__)

# Built from web/ (React + TypeScript) by `npm run build`; the built files are committed.
STATIC_DIR = Path(__file__).parent / "static"


class ConsentRequest(BaseModel):
    agreed: bool


def create_app(home: Path | None = None) -> FastAPI:
    app = FastAPI(title="ImageSkinForLLM", version=__version__)
    data_home = home or default_home()
    # The built browser files are committed unminified so they stay readable; compressing
    # responses here makes them small on the wire instead (less than half the size).
    app.add_middleware(GZipMiddleware, minimum_size=1000)

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

    def require_consent() -> None:
        if not load_consent(data_home).agreed:
            logger.warning("Upload API used before consent")
            raise HTTPException(
                status_code=403, detail="Confirm consent on the setup page before uploading."
            )

    store = UploadStore(data_home)
    uploads_api = "/api/uploads/{kind}"
    needs_consent = [Depends(require_consent)]

    @app.post(uploads_api, dependencies=needs_consent)
    def upload(kind: Kind, file: UploadFile) -> Upload:
        try:
            return store.save(kind, file.filename, file.file)
        except UploadError as e:
            raise HTTPException(status_code=e.status, detail=str(e)) from e

    @app.get(uploads_api, dependencies=needs_consent)
    def list_uploads(kind: Kind) -> list[Upload]:
        return store.list(kind)

    @app.get(uploads_api + "/{upload_id}", dependencies=needs_consent)
    def get_upload(kind: Kind, upload_id: str) -> FileResponse:
        path = store.path(kind, upload_id)
        if path is None:
            raise HTTPException(status_code=404, detail="No such file.")
        # nosniff: browsers must use our type, never guess one from the contents.
        return FileResponse(
            path, media_type=MEDIA_TYPE[path.suffix], headers={"X-Content-Type-Options": "nosniff"}
        )

    @app.delete(uploads_api + "/{upload_id}", dependencies=needs_consent)
    def remove_upload(kind: Kind, upload_id: str) -> dict[str, bool]:
        if not store.remove(kind, upload_id):
            raise HTTPException(status_code=404, detail="No such file.")
        return {"removed": True}

    # Last, so /health and /api routes win over the static files.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
