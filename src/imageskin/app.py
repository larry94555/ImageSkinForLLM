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

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from imageskin import __version__
from imageskin.accent import Accent, load_accent, save_accent
from imageskin.chat import AskLlm, Conversation, LlmClient, LlmError, LlmSettings, StreamLlm
from imageskin.config import default_home
from imageskin.consent import load_consent, save_consent
from imageskin.cores import CoreShare
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
from imageskin.reply_video import ReplyVideos, SentenceClips, VoiceReady
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
    # Chosen by the browser, so it can ask for the reply's clips while the LLM is still writing
    # (roadmap R22).
    reply_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{8,64}$")


class ReplyVideoRequest(BaseModel):
    turn: int  # the reply's place in the conversation, from 0


CHAT_LOCKED = "The chat is locked until you accept a sample video at the end of setup."
NO_SUCH_REPLY = "There is no such reply in the conversation."
# The longest the clips request waits for the next clip before answering with none new.
CLIPS_WAIT_S = 10.0


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
    stream_llm: StreamLlm | None = None,
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
    # The voice is prepared again for replies after the server restarts (roadmap R17).
    voice_ready = VoiceReady(prepare_voice or voice_step, lambda: job.voice_id())
    render = render_clip or photoreal_clip(data_home, voice_engine, voice)
    job = PrepareJob(
        data_home,
        store,
        voice_ready,
        prepare_face or photoreal_face(data_home),
        render,
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
    # While the LLM is busy, the voice and video engines leave it half the cores (R22a).
    core_share = CoreShare()
    core_share.llm_done()
    if ask_llm is None:
        client = LlmClient(llm)
        conversation = Conversation(
            client.ask,
            client.context_tokens,
            client.count,
            client.stream,
            client.warm_up,
            llm_busy=core_share.llm,
        )
    else:
        conversation = Conversation(
            ask_llm, lambda: llm.context_tokens, stream=stream_llm, llm_busy=core_share.llm
        )

    @app.get("/api/chat", dependencies=needs_consent)
    def get_chat() -> dict[str, object]:
        return {"turns": [asdict(t) for t in conversation.turns()]}

    def require_accepted() -> None:
        if not load_review(data_home, job.status()).accepted:
            raise HTTPException(status_code=403, detail=CHAT_LOCKED)

    replies = ReplyVideos(data_home, render, voice_ready, before_engines=core_share.apply_here)
    # The latest streamed reply's clips, rendered sentence by sentence (roadmap R21), by its id.
    sentence_clips: dict[str, SentenceClips] = {}
    clips_lock = threading.Lock()  # guards sentence_clips, used by several request threads
    # One prompt at a time, from dropping the last reply's clips to keeping this one's, so a
    # prompt waiting on another always drops that one's clips.
    chat_lock = threading.Lock()

    def chosen_photo() -> Path | None:
        return store.path("photos", job.status().photo_id or "")

    @app.post("/api/chat", dependencies=[*needs_consent, Depends(require_accepted)])
    def post_chat(body: ChatRequest) -> dict[str, str | int]:
        """The reply, with its place in the conversation to ask for its video by."""
        with chat_lock, core_share.llm():
            return chat(body)

    def chat(body: ChatRequest) -> dict[str, str | int]:
        with clips_lock:
            unasked = list(sentence_clips.values())  # only the latest reply is played
            sentence_clips.clear()
        for old in unasked:
            old.cancel()
        photo = chosen_photo()
        clips = None
        if photo is not None and body.reply_id is not None:
            clips = replies.sentence_clips(photo, body.reply_id)
            with clips_lock:
                sentence_clips[body.reply_id] = clips  # asked for while the LLM writes
        try:
            reply, turn = conversation.send(body.prompt, clips)
        except (ValueError, LlmError) as e:
            if clips is not None:
                with clips_lock:
                    sentence_clips.pop(body.reply_id or "", None)
                clips.cancel()
            status = 400 if isinstance(e, ValueError) else 502
            raise HTTPException(status_code=status, detail=str(e)) from e
        if clips is not None:
            clips.close()
            if not clips.sentences:  # not streamed: the browser asks for the whole video
                with clips_lock:
                    sentence_clips.pop(body.reply_id or "", None)
        return {**asdict(reply), "turn": turn}

    @app.get("/api/chat/clips/{reply_id}", dependencies=needs_consent)
    def get_clips(
        reply_id: str,
        # With `known`, the browser's count so far: the answer waits (up to `wait` seconds)
        # until there is more to tell, so each clip is known the moment it is ready (R22a).
        known: int | None = Query(default=None, ge=0),
        wait: float = Query(default=CLIPS_WAIT_S, ge=0, le=CLIPS_WAIT_S),
    ) -> dict[str, object]:
        """The reply's clips so far, in order, each with when its sentence arrived from the LLM
        and when the clip was ready (seconds on the server's clock, like `now`); done once
        there will be no more."""
        with clips_lock:
            clips = sentence_clips.get(reply_id)
        if clips is None:
            raise HTTPException(status_code=404, detail="No clips for that reply.")
        if known is not None:
            clips.wait_for_change(known, wait)
        made = [
            {
                "url": f"/api/chat/clips/{reply_id}/{n}",
                "sentence_at": t.sentence_at,
                "ready_at": t.ready_at,
            }
            for n, t in enumerate(clips.times[: len(clips.clips)], 1)
        ]
        return {
            "clips": made,
            "done": clips.done,
            "error": clips.error,
            "now": time.perf_counter(),
        }

    @app.get("/api/chat/clips/{reply_id}/{n}", dependencies=needs_consent)
    def get_clip_file(reply_id: str, n: int) -> FileResponse:
        with clips_lock:
            clips = sentence_clips.get(reply_id)
        if clips is None or not 1 <= n <= len(clips.clips):
            raise HTTPException(status_code=404, detail="No such clip.")
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(clips.clips[n - 1], media_type="video/mp4", headers=headers)

    def warm_up_replies() -> None:
        # Only once a sample is accepted: before that the chat is locked and Prepare loads them.
        status = job.status()
        photo = store.path("photos", status.photo_id or "")
        if photo is not None and load_review(data_home, status).accepted:
            logger.info("Warming up replies")
            # On its own thread: an LLM that accepts the request but doesn't answer would
            # otherwise hold the engines' warm-up back for its whole timeout.
            llm = threading.Thread(target=conversation.warm_up, name="llm-warm-up", daemon=True)
            llm.start()
            replies.warm_up(photo)
            llm.join()

    app.state.reply_warm_up = threading.Thread(
        target=warm_up_replies, name="reply-warm-up", daemon=True
    )
    app.state.reply_warm_up.start()

    @app.post("/api/chat/video", dependencies=[*needs_consent, Depends(require_accepted)])
    def post_reply_video(body: ReplyVideoRequest) -> dict[str, str | None]:
        """Speak a reply in the person's voice and render it on their photo, for an LLM that
        doesn't stream. The video's address, or null when the reply has nothing to say aloud."""
        turns = conversation.turns()
        if not 0 <= body.turn < len(turns) or turns[body.turn].role != "assistant":
            raise HTTPException(status_code=404, detail=NO_SUCH_REPLY)
        photo = chosen_photo()
        if photo is None:
            raise HTTPException(status_code=409, detail="The photo was removed. Choose another.")
        try:
            path = replies.render(photo, body.turn, turns[body.turn].content)
        except Exception as e:
            # The voice and video engines' errors say what went wrong; the reply is still shown.
            raise HTTPException(status_code=502, detail=str(e)) from e
        return {"video": None if path is None else f"/api/chat/videos/{body.turn}"}

    @app.get("/api/chat/videos/{turn}", dependencies=needs_consent)
    def get_reply_video(turn: int) -> FileResponse:
        path = replies.path(turn)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="No video for that reply.")
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(path, media_type="video/mp4", headers=headers)

    # Last, so /health and /api routes win over the static files.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
