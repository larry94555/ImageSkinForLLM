"""FastAPI application: the JSON API under /api and the browser app at /."""

import functools
import importlib.util
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from imageskin import __version__
from imageskin.accent import Accent, load_accent, save_accent
from imageskin.chat import AskLlm, Conversation, LlmClient, LlmError, LlmSettings
from imageskin.config import default_home
from imageskin.consent import load_consent, save_consent
from imageskin.prepare_job import (
    ClipName,
    PrepareError,
    PrepareFace,
    PrepareJob,
    PrepareStatus,
    PrepareVoice,
    RenderClip,
    clip_voice,
    photoreal_clip,
    photoreal_face,
)
from imageskin.review import accept, load_review, withdraw
from imageskin.speaker_checks import SpeakerChecker
from imageskin.uploads import (
    MEDIA_TYPE,
    Kind,
    PhotoCheck,
    PhotoChoice,
    SoundCheck,
    Upload,
    UploadError,
    UploadStore,
    VoiceSample,
)

logger = logging.getLogger(__name__)

# Built from web/ (React + TypeScript) by `npm run build`; the built files are committed.
STATIC_DIR = Path(__file__).parent / "static"


class ConsentRequest(BaseModel):
    agreed: bool


class PhotoChoiceRequest(BaseModel):
    id: str


class AccentRequest(BaseModel):
    accent: Accent


class ChatRequest(BaseModel):
    prompt: str


CHAT_LOCKED = "The chat is locked until you accept a sample video at the end of setup."


class ReviewRequest(BaseModel):
    # The four choices under the sample video (feature item 7).
    decision: Literal["accept", "reject-image", "reject-voice", "change-accent"]


NEEDS_CLONE = (
    "Another accent needs the person's own voice installed; see 'Your own voice' in the README."
)
WAIT_FOR_PREPARE = "Wait until Prepare finishes, then choose the accent."


class AccentChoice(BaseModel):
    accent: Accent
    # False when the person's own voice is not installed: Kokoro then speaks, in its own accent.
    available: bool


def face_checker(home: Path) -> PhotoCheck | None:
    """The face checks when MediaPipe is installed; photos are then checked as they arrive."""
    if importlib.util.find_spec("mediapipe") is None:
        logger.warning(
            'Face checks are off: MediaPipe is not installed. Run: pip install -e ".[faces]"'
        )
        return None
    from imageskin.face_checks import FaceChecker

    logger.info("Face checks are on")
    checker = FaceChecker(home / "models" / "faces")
    # Download the models now, so the first photo isn't held up by it.
    threading.Thread(target=checker.prepare, name="face-models", daemon=True).start()
    return checker.check


def sound_checker(speakers: SpeakerChecker) -> SoundCheck:
    """The sound checks, with the check for a second voice (roadmap R11)."""
    from imageskin import sound_checks

    # Download the model now, so the first recording isn't held up by it.
    threading.Thread(target=speakers.prepare, name="speaker-model", daemon=True).start()
    return functools.partial(sound_checks.check, voices=speakers.check)


def create_app(
    home: Path | None = None,
    check_photo: PhotoCheck | None = None,
    check_sound: SoundCheck | None = None,
    prepare_voice: PrepareVoice | None = None,
    prepare_face: PrepareFace | None = None,
    render_clip: RenderClip | None = None,
    llm: LlmSettings | None = None,
    ask_llm: AskLlm | None = None,
) -> FastAPI:
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
                status_code=403,
                detail="Consent is needed before uploading. Open the app's setup page"
                " (/#/consent), tick the box, then try again.",
            )

    # One speaker model for the one-speaker check and for picking an accent's base voice.
    speakers = SpeakerChecker(data_home / "models" / "speakers")
    store = UploadStore(
        data_home,
        check_photo or face_checker(data_home),
        check_sound or sound_checker(speakers),
    )
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

    @app.post(uploads_api + "/{upload_id}/check", dependencies=needs_consent)
    def check_upload_now(kind: Kind, upload_id: str) -> Upload:
        checked = store.check(kind, upload_id)
        if checked is None:
            raise HTTPException(status_code=404, detail="No such file.")
        return checked

    @app.get("/api/voice-sample", dependencies=needs_consent)
    def get_voice_sample() -> VoiceSample:
        return store.voice_sample()

    @app.get("/api/voice-sample/audio", dependencies=needs_consent)
    def get_voice_sample_audio() -> FileResponse:
        if not store.voice_sample_file.is_file():
            raise HTTPException(status_code=404, detail="No recording has passed the checks yet.")
        # no-store: it changes whenever a recording is added or removed.
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
        return FileResponse(store.voice_sample_file, media_type="audio/wav", headers=headers)

    # Before the {upload_id} routes; ids are 32 hex digits, so they never clash.
    @app.get("/api/uploads/photos/chosen", dependencies=needs_consent)
    def get_photo_choice() -> PhotoChoice:
        return store.photo_choice()

    @app.put("/api/uploads/photos/chosen", dependencies=needs_consent)
    def put_photo_choice(body: PhotoChoiceRequest) -> PhotoChoice:
        try:
            return store.choose_photo(body.id)
        except UploadError as e:
            raise HTTPException(status_code=e.status, detail=str(e)) from e

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

    # One voice engine for the job, so Prepare loads the voice model once.
    def accent() -> Accent:
        return load_accent(data_home)

    voice_step, voice_engine, voice, voice_kind = clip_voice(
        store.voice_sample_file, accent, speakers
    )
    job = PrepareJob(
        data_home,
        store,
        prepare_voice or voice_step,
        prepare_face or photoreal_face(data_home),
        render_clip or photoreal_clip(data_home, voice_engine, voice),
        voice_kind,
        accent,
    )
    app.state.prepare_job = job
    job.resume()  # a job the server was stopped in the middle of carries on

    @app.get("/api/prepare", dependencies=needs_consent)
    def get_prepare() -> PrepareStatus:
        return job.status()

    @app.post("/api/prepare", dependencies=needs_consent)
    def start_prepare() -> PrepareStatus:
        try:
            return job.start()
        except PrepareError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @app.get("/api/accent", dependencies=needs_consent)
    def get_accent() -> AccentChoice:
        # Without the person's own voice, Kokoro speaks in its own accent, so that is the one shown.
        available = voice_kind == "clone"
        return AccentChoice(accent=accent() if available else "own", available=available)

    @app.put("/api/accent", dependencies=needs_consent)
    def put_accent(body: AccentRequest) -> AccentChoice:
        if body.accent != "own" and voice_kind != "clone":
            raise HTTPException(status_code=409, detail=NEEDS_CLONE)
        if not job.change_accent(lambda: save_accent(data_home, body.accent)):
            # The running job would finish in the old accent; it is chosen before or after it.
            raise HTTPException(status_code=409, detail=WAIT_FOR_PREPARE)
        return get_accent()

    @app.get("/api/prepare/clips/{name}", dependencies=needs_consent)
    def get_clip(name: ClipName) -> FileResponse:
        path = job.clip(name)
        if path is None:
            raise HTTPException(status_code=404, detail="Not prepared yet. Click Prepare first.")
        # no-cache: preparing again replaces it under the same address.
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(path, media_type="video/mp4", headers=headers)

    @app.get("/api/review", dependencies=needs_consent)
    def get_review() -> dict[str, object]:
        return asdict(load_review(data_home, job.status()))

    @app.post("/api/review", dependencies=needs_consent)
    def post_review(body: ReviewRequest) -> dict[str, object]:
        if body.decision != "accept":
            return asdict(withdraw(data_home, body.decision))
        try:
            return asdict(accept(data_home, job.status()))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    llm = llm or LlmSettings()
    logger.info(
        "Chat LLM", extra={"url": llm.url, "model": llm.model, "context_tokens": llm.context_tokens}
    )
    if ask_llm is None:
        client = LlmClient(llm)
        conversation = Conversation(client.ask, client.context_tokens, client.count)
    else:
        conversation = Conversation(ask_llm, lambda: llm.context_tokens)

    @app.get("/api/chat", dependencies=needs_consent)
    def get_chat() -> dict[str, object]:
        return {"turns": [asdict(t) for t in conversation.turns()]}

    @app.post("/api/chat", dependencies=needs_consent)
    def post_chat(body: ChatRequest) -> dict[str, str]:
        if not load_review(data_home, job.status()).accepted:
            raise HTTPException(status_code=403, detail=CHAT_LOCKED)
        try:
            return asdict(conversation.send(body.prompt))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except LlmError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    # Last, so /health and /api routes win over the static files.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
