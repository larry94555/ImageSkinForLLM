"""FastAPI application: the JSON API under /api and the browser app at /."""

import functools
import html
import importlib.util
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi import Path as PathParam
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from imageskin import __version__, pdf_reading, reply_times, server_timing
from imageskin.accent import Accent, load_accent, save_accent
from imageskin.admin import FILENAME as ADMIN_FILENAME
from imageskin.admin import AdminSignIns
from imageskin.admin_api import admin_router
from imageskin.assess import MOST_QUESTIONS, Answer, Assessment, Assessor
from imageskin.chat import (
    AskLlm,
    ChatLlm,
    ClearFailed,
    Conversation,
    Count,
    LlmCancelled,
    LlmError,
    LlmSettings,
    Message,
    PromptStop,
    StreamLlm,
    Teach,
    Turn,
    ask_stop,
    estimate,
)
from imageskin.chatgpt_signin import CALLBACK_PATH, ChatGptSignIn, SignInError
from imageskin.config import default_home
from imageskin.consent import load_consent, save_consent
from imageskin.content import ContentStore, Pdf
from imageskin.cores import CoreShare, cores, use_performance_cores
from imageskin.default_people import page_order
from imageskin.default_people import people as default_people
from imageskin.delete_data import Deleted, delete_my_data
from imageskin.failure import report
from imageskin.lessons_ahead import LessonsAhead
from imageskin.llm_choice import (
    PROVIDERS,
    ModelListError,
    ModelLists,
    SwitchableLlm,
    described,
    load_choice,
    pinned,
    save_choice,
)
from imageskin.lookup import ContentLookup, as_passages
from imageskin.network import NetworkMonth
from imageskin.prepare_job import (
    CLONES,
    NOT_PREPARED,
    REPLY_SIDE,
    ClipName,
    ClipSteps,
    PrepareError,
    PrepareFace,
    PrepareJob,
    PrepareStatus,
    PrepareVoice,
    RenderClip,
    clip_voice,
    photoreal_face,
    photoreal_steps,
    steps_clip,
)
from imageskin.quiz import QUESTIONS, Judge, Quiz, Quizzer, Said
from imageskin.reading_job import ReadingJob, ReadingStatus, ReadPdf
from imageskin.ready_voice import LANGS as READY_VOICES
from imageskin.ready_voice import load_ready_voice, ready_voices, save_ready_voice
from imageskin.ready_voice import preset as ready_preset
from imageskin.replies_first import RepliesFirst
from imageskin.reply_times import ReplyTimes
from imageskin.reply_video import ReplyVideos, SentenceClips, VoiceReady, ms_since
from imageskin.resources import ResourceReader
from imageskin.review import accept, load_review, withdraw
from imageskin.speaker_checks import SpeakerChecker
from imageskin.speech_text import math_in_words
from imageskin.spoken import corrected, vocabulary
from imageskin.start_now import Choice as PersonChoice
from imageskin.start_now import KokoroVoices, PresetVoice, StartNow, StartStatus
from imageskin.startup import StartupTimes
from imageskin.teach import Choice, Explain, Lesson, Say, Tutor, lesson_topics
from imageskin.topic_replies import TopicReplies, context_of
from imageskin.topics import hint_line, main_entries
from imageskin.ui_settings import UiSettings, load_ui_settings, save_ui_settings
from imageskin.uploads import (
    MEDIA_TYPE,
    NO_VOICE,
    Kind,
    PhotoCheck,
    PhotoChoice,
    SoundCheck,
    Upload,
    UploadError,
    UploadStore,
    VoiceSample,
    shown_size,
)
from imageskin.wiki import (
    TOPICS_SCHEMA,
    WIKI_REPLY_TOKENS,
    AskForTopics,
    WaitForLlm,
    Wiki,
    WikiPage,
    build_wiki,
)
from imageskin.wiki import Progress as WikiProgress
from imageskin.wiki_edits import EditError
from imageskin.wiki_history import HistoryError
from imageskin.wiki_job import BuildOutline, BuildWiki, WikiJob, WikiStatus
from imageskin.wiki_outline import (
    OUTLINE_REPLY_TOKENS,
    AskForJson,
    Entry,
    OutlineProgress,
    Outliner,
)

logger = logging.getLogger(__name__)

# Built from web/ (React + TypeScript) by `npm run build`; the built files are committed.
STATIC_DIR = Path(__file__).parent / "static"


class ChatGptAccount(BaseModel):
    account: str  # a registration's client ID, from the ChatGPT status's accounts


class ConsentRequest(BaseModel):
    agreed: bool


class ReadyVoiceRequest(BaseModel):
    voice: str  # one of Kokoro's ready-made voices (item 59)


class PhotoChoiceRequest(BaseModel):
    id: str


class AccentRequest(BaseModel):
    accent: Accent


class LlmRequest(BaseModel):
    provider: str
    api_key: str | None = None  # kept from before when left out
    model: str | None = None  # blank for the provider's default; kept when left out


class ModelsRequest(BaseModel):
    provider: str
    api_key: str | None = None  # the saved key when left out


class StartNowRequest(BaseModel):
    gender: str
    accent: str
    realism: str
    role: str
    face: int = 1  # R24c2


# How long Delete my data waits for a PDF being read to stop at its next page (R31a).
READING_STOP_S = 10.0
# A request that waited for Delete my data (roadmap R31) and would write the person's data again.
DELETED_MEANWHILE = "Your data was deleted while this was waiting. Start setup again."
OWN_NOT_ACCEPTED = "Accept the sample video of your own photo and voice at the end of setup first."
# R24d: a ready-made avatar in the user's own voice.
VOICE_CONSENT_NEEDED = "Tick the box to confirm the person in the recordings agreed."
NO_AVATAR = "Choose a ready-made avatar first."
WAIT_FOR_PREPARE_AVATAR = "Wait until Prepare finishes, then try again."
WAIT_FOR_AVATAR = "Wait until the ready-made avatar is ready, then switch to your own photo."
REPLY_ID_PATTERN = r"^[0-9a-f]{8,64}$"
# The conversation is saved in the data folder, so it is still there after a restart (R30).
CONVERSATION_FILE = "conversation.json"
# A prompt stopped while it was answered: it is dropped, with the reply it would have had.
PROMPT_STOPPED = "Stopped."
# At most this many replies stopped before their prompt came are remembered (roadmap R19).
STOPPED_EARLY_MAX = 64


class WikiEditRequest(BaseModel):
    title: str
    summary: str


class LessonState(BaseModel):
    """Where a lesson is (R41h), kept by the browser and sent with each prompt."""

    topic: str = Field(max_length=500)
    part: int = Field(ge=0)
    active: bool = True


class QuizState(BaseModel):
    """Where a quiz is (R41i), kept by the browser and sent with each prompt."""

    topic: str = Field(max_length=500)
    number: int = Field(ge=1, le=QUESTIONS)
    question: str = Field(max_length=2000)
    part: int = Field(ge=0)
    asked: list[str] = Field(default=[], max_length=QUESTIONS)
    right: int = Field(default=0, ge=0, le=QUESTIONS)
    partly: int = Field(default=0, ge=0, le=QUESTIONS)
    review: list[str] = Field(default=[], max_length=QUESTIONS)
    source: str = Field(default="", max_length=100)


class AnswerState(BaseModel):
    """An answer in an assessment (R41j), kept by the browser for the evaluation at the end."""

    topic: str = Field(max_length=500)
    level: int = Field(ge=0, le=2)
    question: str = Field(max_length=2000)
    verdict: str = Field(pattern="^(right|partly right|wrong)$")
    correct: str = Field(max_length=2000)


class AssessmentState(BaseModel):
    """Where an assessment is (R41j), kept by the browser and sent with each prompt."""

    total: int = Field(ge=1, le=MOST_QUESTIONS)
    number: int = Field(ge=1, le=MOST_QUESTIONS)
    topic: str = Field(max_length=500)
    level: int = Field(ge=0, le=2)
    part: int = Field(ge=0)
    question: str = Field(max_length=2000)
    source: str = Field(default="", max_length=100)
    plan: str = Field(default="", max_length=100)  # the topics' fingerprint (review on PR #90)
    answers: list[AnswerState] = Field(default=[], max_length=MOST_QUESTIONS)

    @model_validator(mode="after")
    def answered_so_far(self) -> "AssessmentState":
        if self.number > self.total or len(self.answers) != self.number - 1:
            raise ValueError("an answer for each question before this one")
        return self


class ChatRequest(BaseModel):
    prompt: str
    # Chosen by the browser, so it can ask for the reply's clips while the LLM is still writing
    # (roadmap R22).
    reply_id: str | None = Field(default=None, pattern=REPLY_ID_PATTERN)
    lesson: LessonState | None = None
    quiz: QuizState | None = None
    assessment: AssessmentState | None = None
    # Said with Hold to talk (R24): misheard names and terms are put back before it is answered.
    spoken: bool = False


class ReplyVideoRequest(BaseModel):
    turn: int  # the reply's place in the conversation, from 0
    # The reply's id from POST /api/chat, so Stop can stop its video (roadmap R19).
    reply_id: str | None = Field(default=None, pattern=REPLY_ID_PATTERN)


CHAT_LOCKED = "The chat is locked until you accept a sample video at the end of setup."
NO_SUCH_REPLY = "There is no such reply in the conversation."
# The longest the clips request waits for the next clip before answering with none new.
CLIPS_WAIT_S = 10.0


class ReviewRequest(BaseModel):
    # The four choices under the sample video (feature item 7).
    decision: Literal["accept", "reject-image", "reject-voice", "change-accent"]


NEEDS_CLONE = "Another accent needs the voice add-on, which isn't installed on this computer yet."
WAIT_FOR_PREPARE = "Wait until Prepare finishes, then choose the accent."
WAIT_FOR_PREPARE_VOICE = "Wait until Prepare finishes, then choose the voice."


class AccentChoice(BaseModel):
    accent: Accent
    # False when the person's own voice is not installed: Kokoro then speaks, in its own accent.
    available: bool


# What `imageskin serve` logs once the app can take input: the models below and the replies'
# warm-up have loaded (the FAQ quotes it; Larry, 2026-10-15).
READY_MESSAGE = "Loading has completed. The application is ready for use."


def face_checker(
    home: Path,
    loading: list[threading.Thread] | None = None,
    startup: StartupTimes | None = None,
) -> PhotoCheck | None:
    """The face checks when MediaPipe is installed; photos are then checked as they arrive.
    The thread loading their models is added to `loading`, and timed in `startup`."""
    if importlib.util.find_spec("mediapipe") is None:
        logger.warning(
            'Face checks are off: MediaPipe is not installed. Run: pip install -e ".[faces]"'
        )
        return None
    from imageskin.face_checks import FaceChecker

    logger.info("Face checks are on")
    checker = FaceChecker(home / "models" / "faces")
    # Download the models now, so the first photo isn't held up by it.
    load = checker.prepare if startup is None else startup.timed("face models", checker.prepare)
    thread = threading.Thread(target=load, name="face-models", daemon=True)
    thread.start()
    if loading is not None:
        loading.append(thread)
    return checker.check


def sound_checker(
    speakers: SpeakerChecker,
    loading: list[threading.Thread] | None = None,
    startup: StartupTimes | None = None,
) -> SoundCheck:
    """The sound checks, with the check for a second voice (roadmap R11). The thread loading
    the speaker model is added to `loading`, and timed in `startup`."""
    from imageskin import sound_checks

    # Download the model now, so the first recording isn't held up by it.
    load = speakers.prepare if startup is None else startup.timed("speaker model", speakers.prepare)
    thread = threading.Thread(target=load, name="speaker-model", daemon=True)
    thread.start()
    if loading is not None:
        loading.append(thread)
    return functools.partial(sound_checks.check, voices=speakers.check)


MAX_WIKI_FILE_BYTES = 50 * 1024 * 1024


def wiki_file_name(saved: dict[str, Any]) -> str:
    """The name a saved wiki file downloads as: the PDF's, with -wiki.json for .pdf."""
    stem = Path(saved["pdf_name"]).stem or "wiki"
    kept = (c if (c.isascii() and c.isalnum()) or c in " ._-" else "_" for c in stem)
    safe = "".join(kept).strip() or "wiki"
    return f"{safe}-wiki.json"


def wiki_builder(
    llm: LlmSettings,
    client: ChatLlm | None,
    ask_llm: AskLlm | None,
    replies_first: RepliesFirst | None = None,
) -> BuildWiki:
    """Builds wiki pages with the chat's LLM: llama-server's, or `ask_llm` (tests). With
    `replies_first`, its requests wait while a chat reply is written (R99)."""
    ask: AskForTopics
    count: Count
    if client is not None:
        ask = functools.partial(client.ask, max_tokens=WIKI_REPLY_TOKENS, schema=TOPICS_SCHEMA)
        count, window = client.count, client.context_tokens
    else:
        assert ask_llm is not None
        ask, count, window = ask_llm, estimate, lambda: llm.context_tokens
    if replies_first is not None:
        ask = replies_first.wiki(ask)

    def build(
        pdf_id: str, pieces: list[dict[str, Any]], progress: WikiProgress, wait: WaitForLlm
    ) -> Wiki:
        with pinned(client):  # one LLM builds every part (a review on PR #115)
            return build_wiki(pdf_id, pieces, ask, count, window(), progress, wait)

    return build


def outline_builder(
    llm: LlmSettings,
    client: ChatLlm | None,
    ask_llm: AskLlm | None,
    replies_first: RepliesFirst | None = None,
) -> BuildOutline:
    """Builds the wiki's outline with the chat's LLM: llama-server's, or `ask_llm` (tests). With
    `replies_first`, its requests wait while a chat reply is written (R99)."""
    ask: AskForJson
    count: Count
    if client is not None:
        llama = client

        def ask(messages: list[Message], schema: dict[str, Any]) -> str:
            return llama.ask(messages, max_tokens=OUTLINE_REPLY_TOKENS, schema=schema)

        count, window = client.count, client.context_tokens
    else:
        assert ask_llm is not None
        test_ask = ask_llm

        def ask(messages: list[Message], schema: dict[str, Any]) -> str:
            return test_ask(messages)

        count, window = estimate, lambda: llm.context_tokens
    if replies_first is not None:
        ask = replies_first.wiki(ask)

    def build(
        pdf_id: str,
        topics: list[WikiPage],
        pieces: list[dict[str, Any]],
        progress: OutlineProgress,
        wait: WaitForLlm,
    ) -> list[Entry]:
        with pinned(client):
            return Outliner(pdf_id, ask, count, window(), progress, wait).outline(topics, pieces)

    return build


def wait_until_loaded(app: FastAPI) -> None:
    """Wait for what the app loads in the background at the start: the face and speaker models
    and, once a sample is accepted, the replies' warm-up (the voice, the video and the LLM)."""
    for thread in app.state.loading:
        thread.join()


def signed_in_page(error: str, status: int) -> HTMLResponse:
    """A plain page saying why signing in with ChatGPT failed, with the way back."""
    return HTMLResponse(
        "<!doctype html><meta charset=utf-8><title>Sign in with ChatGPT</title>"
        f"<p>Couldn't sign in with ChatGPT: {html.escape(error)}</p>"
        '<p><a href="/#/settings">Back to Settings</a></p>',
        status_code=status,
    )


def create_app(
    home: Path | None = None,
    check_photo: PhotoCheck | None = None,
    check_sound: SoundCheck | None = None,
    prepare_voice: PrepareVoice | None = None,
    prepare_face: PrepareFace | None = None,
    render_clip: RenderClip | None = None,
    clip_steps: ClipSteps | None = None,  # or the clip's two steps, for pipelined clips
    llm: LlmSettings | None = None,
    ask_llm: AskLlm | None = None,
    stream_llm: StreamLlm | None = None,
    warm_up_llm: Callable[[], None] | None = None,  # with ask_llm: readies the LLM (tests)
    read_pdf: ReadPdf | None = None,
    build_wiki: BuildWiki | None = None,
    # The wiki's outline; with build_wiki alone, the topics as they are (tests).
    build_outline: BuildOutline | None = None,
    # Whether prompts the content has nothing on are answered too, or declined (R41).
    general_prompts: bool = False,
    # Sign in with ChatGPT (R43); one that asks auth.openai.com when left out.
    chatgpt: ChatGptSignIn | None = None,
    # When each part of the start began and ended (R96c); `imageskin serve` passes its own.
    startup: StartupTimes | None = None,
    # Whether each topic's first lesson part is written ahead (R98a); left out, it is with the
    # app's own LLM and not with a test's `ask_llm`, whose replies the tests count.
    lessons_ahead: bool | None = None,
    # The administrator's password file (R149); left out, admin.toml in the home folder.
    admin_file: Path | None = None,
) -> FastAPI:
    startup = startup or StartupTimes()
    startup.begin("app made")
    app = FastAPI(title="ImageSkinForLLM", version=__version__)
    app.state.startup = startup
    data_home = home or default_home()
    # First, before any thread starts, so every later thread inherits the pin (R22g).
    performance_cores = use_performance_cores()
    # The built browser files are committed unminified so they stay readable; compressing
    # responses here makes them small on the wire instead (less than half the size).
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # How many times Delete my data has run (R31). Each write of the person's data checks it is
    # the same as when its request arrived, so one that waited for a delete never writes after
    # it. Read here, as the request arrives, before any dependency can wait on a lock.
    deletes = [0]

    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        request.state.deletes_seen = deletes[0]
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

    @app.get("/api/startup")
    def get_startup() -> dict[str, Any]:
        """When each part of the start began and ended, for `imageskin time-startup` (R96c)."""
        return startup.snapshot()

    # Signing in as the administrator (R149). Every admin route later depends on require_admin.
    admin_sign_ins = AdminSignIns(admin_file or data_home / ADMIN_FILENAME)
    admin_routes, app.state.require_admin = admin_router(admin_sign_ins)
    app.include_router(admin_routes)

    # The machine's resources for the admin dashboard (R152), for the administrator only.
    # The network's month is sampled each minute by `imageskin serve` (R153), and at each read.
    app.state.network_month = NetworkMonth(data_home)
    resource_reader = ResourceReader(data_home, network=app.state.network_month)

    @app.get("/api/admin/resources", dependencies=[Depends(app.state.require_admin)])
    def get_resources() -> dict[str, Any]:
        return resource_reader.read()

    @app.get("/api/consent")
    def get_consent() -> dict[str, object]:
        return asdict(load_consent(data_home))

    # Held by Delete my data (R31) and by every request that writes the person's files, so none
    # writes while they are deleted and leaves something behind (review on PR #109).
    data_lock = threading.Lock()

    def arrived_after(request: Request) -> int:
        return int(request.state.deletes_seen)

    DeletesSeen = Annotated[int, Depends(arrived_after)]

    def not_deleted_since(seen: int) -> None:
        """Refuse a request that arrived before a Delete my data that has run since."""
        if deletes[0] != seen:
            logger.warning("Request arrived before Delete my data; refused")
            raise HTTPException(status_code=409, detail=DELETED_MEANWHILE)

    @app.post("/api/consent")
    def post_consent(body: ConsentRequest, seen: DeletesSeen) -> dict[str, object]:
        if not body.agreed:
            raise HTTPException(status_code=400, detail="Tick the box to confirm consent.")
        with data_lock:
            not_deleted_since(seen)
            return asdict(save_consent(data_home))

    # The Settings page's settings (R41a, R27): anyone can read and change them for now. The
    # question scope follows the config file until it is changed there.
    ui_defaults = UiSettings(general_prompts=general_prompts)

    @app.get("/api/settings")
    def get_settings() -> dict[str, object]:
        return asdict(load_ui_settings(data_home, ui_defaults))

    @app.patch("/api/settings")
    def patch_settings(changes: Annotated[dict[str, Any], Body()]) -> dict[str, object]:
        try:
            saved = asdict(save_ui_settings(data_home, changes, ui_defaults))
            if "teach_me" in changes and app.state.lessons is not None:
                # Turned on, its lessons are written; turned off, a round writing them stops
                # after the lesson under way (R98a).
                app.state.lessons.refresh()
            return saved
        except ValueError as e:
            logger.warning("Settings change refused", extra={"error": str(e)})
            raise HTTPException(status_code=400, detail=str(e)) from e
        except OSError as e:
            logger.error("Could not save the settings", extra={"error": str(e)})
            raise HTTPException(status_code=500, detail="The settings could not be saved.") from e

    def require_consent() -> None:
        if not load_consent(data_home).agreed:
            logger.warning("Upload API used before consent")
            raise HTTPException(
                status_code=403,
                detail="Consent is needed before uploading. Open the app's setup page"
                " (/#/consent), tick the box, then try again.",
            )

    @contextmanager
    def personal_write(seen: int) -> Iterator[None]:
        """Write the person's files, unless Delete my data is running: then once it is done,
        and only for a request that arrived after it, with consent given again (R31)."""
        with data_lock:
            not_deleted_since(seen)
            require_consent()
            yield

    @contextmanager
    def content_write(seen: int) -> Iterator[None]:
        """Change the PDFs or their wiki, unless Delete my data is running: then once it is
        done, and only for a request that arrived after it (R31a, Codex's review). No consent
        is needed: the content is the host's to manage."""
        with data_lock:
            not_deleted_since(seen)
            yield

    # One speaker model for the one-speaker check and for picking an accent's base voice.
    speakers = SpeakerChecker(data_home / "models" / "speakers")
    # What loads in the background at the start; wait_until_loaded waits for it.
    app.state.loading = []
    store = UploadStore(
        data_home,
        check_photo or face_checker(data_home, app.state.loading, startup),
        check_sound or sound_checker(speakers, app.state.loading, startup),
    )
    uploads_api = "/api/uploads/{kind}"
    needs_consent = [Depends(require_consent)]

    # A default person (roadmap R24c) is chosen without consent: the chat needs consent only
    # for the person's own photo and voice (item 58).
    def require_person() -> None:
        if start_now.chosen() is None:
            require_consent()

    needs_person = [Depends(require_person)]

    @app.post(uploads_api, dependencies=needs_consent)
    def upload(kind: Kind, file: UploadFile, seen: DeletesSeen, response: Response) -> Upload:
        try:
            # Each step's time goes back in the Server-Timing header (R96b). FastAPI has received
            # and parsed the upload before this runs, so `endpoint` leaves that out; the time
            # until the answer, seen by the client, has it.
            with server_timing.collecting() as steps, server_timing.step("endpoint"):
                with personal_write(seen):
                    saved = store.save(kind, file.filename, file.file)
        except UploadError as e:
            raise HTTPException(status_code=e.status, detail=str(e)) from e
        response.headers["Server-Timing"] = server_timing.header(steps)
        return saved

    @app.get(uploads_api, dependencies=needs_consent)
    def list_uploads(kind: Kind) -> list[Upload]:
        return store.list(kind)

    @app.post(uploads_api + "/{upload_id}/check", dependencies=needs_consent)
    def check_upload_now(kind: Kind, upload_id: str, seen: DeletesSeen) -> Upload:
        start = time.perf_counter()
        try:
            with personal_write(seen):
                checked = store.check(kind, upload_id)
        except UploadError as e:
            logger.error(
                "Upload could not be checked",
                extra={
                    "kind": kind,
                    "upload": upload_id,
                    "error": str(e),
                    "check_ms": ms_since(start),
                },
            )
            raise HTTPException(status_code=e.status, detail=str(e)) from e
        if checked is None:
            logger.warning("Upload to check not found", extra={"kind": kind, "upload": upload_id})
            raise HTTPException(status_code=404, detail="No such file.")
        # Setup checks old uploads with this; the Settings page's Check again too (R27a).
        logger.info(
            "Upload checked",
            extra={
                "kind": kind,
                "upload": upload_id,
                "problems": None if checked.problems is None else len(checked.problems),
                "check_ms": ms_since(start),
            },
        )
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
    def put_photo_choice(body: PhotoChoiceRequest, seen: DeletesSeen) -> PhotoChoice:
        try:
            with personal_write(seen):
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
    def remove_upload(kind: Kind, upload_id: str, seen: DeletesSeen) -> dict[str, bool]:
        with personal_write(seen):
            removed = store.remove(kind, upload_id)
        if not removed:
            raise HTTPException(status_code=404, detail="No such file.")
        return {"removed": True}

    # PDF content (R34): kept apart from the photos and sounds. It is the administrator's
    # material, not the person's likeness, so it needs no consent; sign-on comes with R44.
    content = ContentStore(data_home)
    content_api = "/api/content"
    # Each PDF is read when it is added or replaced (R36); on start, any not read yet.
    readings = ReadingJob(content, read_pdf or pdf_reading.read_pdf)
    # Then the wiki is built from what was read (R37), with the chat's LLM.
    llm = llm or LlmSettings()
    # The LLM picked on the Settings page (R42), with llama-server's address from the config.
    # Sign in with ChatGPT (R43), whose plan can answer (R43a).
    signin = chatgpt or ChatGptSignIn(data_home)
    switchable = SwitchableLlm(llm, load_choice(data_home), signin.plan_session)
    client = switchable if ask_llm is None else None
    # A chat reply goes before the wiki's requests to the LLM (R99).
    replies_first = RepliesFirst()
    if build_wiki is None:
        build_wiki = wiki_builder(llm, client, ask_llm, replies_first)
        build_outline = build_outline or outline_builder(llm, client, ask_llm, replies_first)
    wiki = WikiJob(content, readings, build_wiki, build_outline)
    readings.on_read = wiki.read
    readings.catch_up()
    wiki.catch_up()
    app.state.readings = readings
    app.state.wiki = wiki

    @app.get(content_api)
    def list_pdfs() -> list[Pdf]:
        return content.list()

    @app.post(content_api)
    def add_pdf(file: UploadFile, seen: DeletesSeen) -> Pdf:
        with content_write(seen):
            try:
                pdf = content.add(file.filename, file.file)
            except UploadError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
            readings.queue(pdf)
        return pdf

    @app.put(content_api + "/{pdf_id}")
    def replace_pdf(pdf_id: str, file: UploadFile, seen: DeletesSeen) -> Pdf:
        with content_write(seen):
            try:
                pdf = content.replace(pdf_id, file.filename, file.file)
            except UploadError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
            wiki.reset(pdf_id)
            readings.queue(pdf)
        return pdf

    # Before /{pdf_id}, which would take "readings" as an id.
    @app.get(content_api + "/readings")
    def reading_statuses() -> dict[str, ReadingStatus]:
        return readings.statuses()

    @app.get(content_api + "/{pdf_id}/reading")
    def get_reading(pdf_id: str) -> dict[str, Any]:
        reading = readings.reading(pdf_id)
        if reading is None:
            raise HTTPException(status_code=404, detail="Not read yet.")
        return reading

    @app.get(content_api + "/{pdf_id}/wiki")
    def get_pdf_wiki(pdf_id: str) -> dict[str, Any]:
        built = wiki.built(pdf_id)
        if built is None:
            raise HTTPException(status_code=404, detail="No wiki pages yet.")
        return built

    @app.get(content_api + "/{pdf_id}")
    def get_pdf(pdf_id: str) -> FileResponse:
        path = content.path(pdf_id)
        pdf = content.get(pdf_id)
        if path is None or pdf is None:
            raise HTTPException(status_code=404, detail="No such PDF.")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=pdf.name,
            content_disposition_type="inline",
            # no-cache: replacing a PDF keeps its address, so the browser must check for a new one.
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"},
        )

    @app.delete(content_api + "/{pdf_id}")
    def remove_pdf(pdf_id: str, seen: DeletesSeen) -> dict[str, bool]:
        with content_write(seen):
            try:
                removed = content.remove(pdf_id)
            except UploadError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
            if not removed:
                raise HTTPException(status_code=404, detail="No such PDF.")
            readings.forget(pdf_id)
            wiki.forget(pdf_id)
        return {"removed": True}

    @app.get("/api/wiki")
    def list_wiki_pages(pdf: str | None = None) -> list[dict[str, Any]]:
        return wiki.pages(pdf)

    # Before /{page_id}, which would take these as ids.
    @app.get("/api/wiki/contents")
    def wiki_contents(pdf: str | None = None) -> list[dict[str, Any]]:
        return wiki.contents(pdf)

    @app.get("/api/wiki/builds")
    def wiki_statuses() -> dict[str, WikiStatus]:
        return wiki.statuses()

    @app.get("/api/wiki/{page_id}")
    def get_wiki_page(page_id: str) -> dict[str, Any]:
        page = wiki.page(page_id)
        if page is None:
            raise HTTPException(status_code=404, detail="No such wiki page.")
        return page

    # The user's edits (roadmap R38).
    @app.put("/api/wiki/{page_id}")
    def edit_wiki_page(page_id: str, request: WikiEditRequest, seen: DeletesSeen) -> dict[str, Any]:
        with content_write(seen):
            try:
                return wiki.edit(page_id, request.title, request.summary)
            except EditError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e

    @app.delete("/api/wiki/{page_id}/edit")
    def undo_wiki_edit(page_id: str, seen: DeletesSeen) -> dict[str, bool]:
        with content_write(seen):
            try:
                undone = wiki.undo_edit(page_id)
            except EditError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
        if not undone:
            raise HTTPException(status_code=404, detail="That wiki entry has no edit.")
        return {"undone": True}

    @app.post("/api/wiki/{page_id}/reviewed")
    def wiki_edit_reviewed(page_id: str, seen: DeletesSeen) -> dict[str, bool]:
        with content_write(seen):
            try:
                checked = wiki.reviewed(page_id)
            except EditError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
        if not checked:
            raise HTTPException(status_code=404, detail="That wiki entry has no edit.")
        return {"reviewed": True}

    @app.post(content_api + "/{pdf_id}/wiki/rebuild")
    def rebuild_wiki(pdf_id: str, seen: DeletesSeen) -> WikiStatus:
        with content_write(seen):
            if content.get(pdf_id) is None:
                raise HTTPException(status_code=404, detail="No such PDF.")
            if not wiki.rebuild(pdf_id):
                raise HTTPException(status_code=409, detail="The PDF hasn't been read yet.")
        return wiki.statuses()[pdf_id]

    # The wiki's history, and saving it to a file and loading it back (roadmap R38a).
    @app.get(content_api + "/{pdf_id}/wiki/history")
    def wiki_history(pdf_id: str) -> list[dict[str, Any]]:
        versions = wiki.versions(pdf_id)
        if versions is None:
            raise HTTPException(status_code=404, detail="No wiki pages yet.")
        return versions

    @app.get(content_api + "/{pdf_id}/wiki/history/{version_id}")
    def wiki_version(pdf_id: str, version_id: str) -> dict[str, Any]:
        found = wiki.version(pdf_id, version_id)
        if found is None:
            raise HTTPException(status_code=404, detail="No such version of the wiki.")
        return found

    @app.post(content_api + "/{pdf_id}/wiki/history/{version_id}/restore")
    def restore_wiki_version(
        pdf_id: str, version_id: str, seen: DeletesSeen, force: bool = False
    ) -> dict[str, bool]:
        with content_write(seen):
            try:
                wiki.restore(pdf_id, version_id, force)
            except HistoryError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
        return {"restored": True}

    @app.get(content_api + "/{pdf_id}/wiki/file")
    def save_wiki_file(pdf_id: str) -> JSONResponse:
        saved = wiki.export(pdf_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="No wiki pages yet.")
        return JSONResponse(
            saved,
            headers={"Content-Disposition": f'attachment; filename="{wiki_file_name(saved)}"'},
        )

    @app.post(content_api + "/{pdf_id}/wiki/file")
    def load_wiki_file(
        pdf_id: str, file: UploadFile, seen: DeletesSeen, force: bool = False
    ) -> dict[str, int]:
        data = file.file.read(MAX_WIKI_FILE_BYTES + 1)
        if len(data) > MAX_WIKI_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"A wiki file can be at most {MAX_WIKI_FILE_BYTES // 2**20} MB.",
            )
        with content_write(seen):
            try:
                added = wiki.load(pdf_id, data, force)
            except HistoryError as e:
                raise HTTPException(status_code=e.status, detail=str(e)) from e
        return {"versions_added": added}

    # One voice engine for the job, so Prepare loads the voice model once.
    def accent() -> Accent:
        return load_accent(data_home)

    voice_step, own_engine, voice, voice_kind = clip_voice(
        store.voice_sample_file, accent, speakers
    )
    # While a default person is chosen, replies speak in their ready-made Kokoro voice (R24c).
    # Prepare's clips are always the person's own, except the default person's own lines, which
    # Start now renders with Prepare's engines while no Prepare runs (review on PR #113).
    kokoro_voices = KokoroVoices()
    voice_engine = PresetVoice(own_engine, lambda: reply_preset(), kokoro_voices)
    prepare_engine = PresetVoice(
        own_engine, lambda: start_now.rendering_voice() or no_sample(), kokoro_voices
    )

    def no_sample() -> tuple[str, str] | None:
        """The ready-made voice the user's own photo speaks in while no recording has passed the
        checks (item 59): none were added, or they were all rejected or removed."""
        if store.voice_sample().problem != NO_VOICE:
            return None
        return ready_preset(load_ready_voice(data_home))

    def avatar_in_own_voice() -> bool:
        """Whether the ready-made avatar speaks in the user's own voice now (R24d): it was asked
        to, and its sample in that voice is accepted."""
        return start_now.own_voice() and load_review(data_home, job.peek()).accepted

    def reply_preset() -> tuple[str, str] | None:
        """The ready-made voice the replies speak in, or None for the user's own."""
        if avatar_in_own_voice():
            return None
        return start_now.voice() or no_sample()

    def kept_voice() -> str | None:
        """The ready-made voice Prepare keeps (item 59), but never for an avatar that is to speak
        in the user's voice (R24d): that needs recordings."""
        kept = None if start_now.own_voice() else no_sample()
        return None if kept is None else kept[1]

    def prepare_own_voice() -> None:
        (prepare_voice or voice_step)()

    # The voice is prepared again for replies after the server restarts (roadmap R17).
    voice_ready = VoiceReady(
        prepare_own_voice,
        lambda: job.voice_id(),
        lambda: reply_preset() is not None,
    )
    # The sample keeps the photo's own size and reply clips are scaled down (roadmap R22c).
    # Each has its own engine, so a prepare and a reply never share one.
    # Both render with the face movement the prepare job was made with (R128a).
    steps = clip_steps or photoreal_steps(
        data_home, prepare_engine, voice, face_movement=lambda: job.prepared_face_movement()
    )
    render = render_clip or steps_clip(steps)
    reply_steps = clip_steps or photoreal_steps(
        data_home,
        voice_engine,
        voice,
        max_side=REPLY_SIDE,
        progressive=True,
        face_movement=lambda: job.prepared_face_movement(),
    )
    reply_render = render_clip or steps_clip(reply_steps)
    job = PrepareJob(
        data_home,
        store,
        voice_ready,
        prepare_face or photoreal_face(data_home),
        render,
        voice_kind,
        accent,
        kept_voice=kept_voice,
        avatar=lambda: start_now.picture() if start_now.own_voice() else None,
    )
    app.state.prepare_job = job

    @app.get("/api/ready-voice", dependencies=needs_consent)
    def get_ready_voice() -> dict[str, object]:
        """The ready-made voice used while there are no recordings, and whether it is in use."""
        return {
            "voice": load_ready_voice(data_home),
            "in_use": no_sample() is not None,
            "voices": ready_voices(),  # every default person's voice (R24e)
        }

    @app.put("/api/ready-voice", dependencies=needs_consent)
    def put_ready_voice(body: ReadyVoiceRequest, seen: DeletesSeen) -> dict[str, object]:
        if body.voice not in READY_VOICES:
            raise HTTPException(
                status_code=400, detail=f"{body.voice!r} is not a ready-made voice."
            )
        # Guarded as the accent is: refused while Prepare runs, and the sample is made again in
        # the new voice when one was ready (Codex's review of PR #128).
        try:
            with personal_write(seen):
                changed = job.change_voice(lambda: save_ready_voice(data_home, body.voice))
        except PrepareError as e:  # the sample is being made again (R27b)
            raise HTTPException(status_code=409, detail=str(e)) from e
        if not changed:
            raise HTTPException(status_code=409, detail=WAIT_FOR_PREPARE_VOICE)
        return get_ready_voice()

    job.resume()  # a job the server was stopped in the middle of carries on

    def with_replies_paused(choose: Callable[[], None]) -> None:
        # A reply being rendered finishes in the voice and face it started with.
        with replies.paused():
            choose()

    start_now = StartNow(
        data_home,
        render,
        on_ready=lambda: start_reply_warm_up(),
        claim=job.claim,
        release=job.release,
        activate=with_replies_paused,
    )
    app.state.start_now = start_now

    @app.get("/api/start-now")
    def get_start_now() -> dict[str, object]:
        chosen = start_now.chosen()
        status = start_now.status()
        return {
            **asdict(status),
            "chosen": None if chosen is None else asdict(chosen),
            "chat_ready": status.state == "ready" and chat_shows_person(),
        }

    def chat_shows_person() -> bool:
        """Whether the chat would show the person chosen now: their idle video is made, or the
        warm-up that makes it has ended (an engine that can't make one, say). Start now waits
        for this, so the chat doesn't open on the person chosen before (Larry's test of R32a)."""
        if not warming_up():
            return True
        photo = chosen_photo()
        return photo is not None and replies.idle(photo) is not None

    @app.post("/api/start-now")
    def post_start_now(body: StartNowRequest, seen: DeletesSeen) -> StartStatus:
        choice = PersonChoice(body.gender, body.accent, body.realism, body.role, body.face)
        problem = choice.problem()
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        with data_lock:
            not_deleted_since(seen)
            try:
                return start_now.start(choice)
            except PrepareError as e:  # setup is preparing the person's own video
                raise HTTPException(status_code=409, detail=str(e)) from e

    @app.get("/api/start-now/faces")
    def get_start_now_faces() -> list[dict[str, object]]:
        """Every default person, so the page can show the faces of a look as the thumbnails
        that ship with it (R24c2), with no label. They come in the order the page shows them,
        which stays the same: by role, then face, then gender (Codex's review of PR #124), so
        women and men take turns rather than one after the other (Larry, 2026-10-21)."""
        return [
            {
                "gender": p.gender,
                "realism": p.realism,
                "role": p.role,
                "face": p.face,
                "name": p.name,
            }
            for p in page_order(default_people())
        ]

    @app.get("/api/start-now/picture")
    def get_start_now_picture() -> FileResponse:
        picture = start_now.picture()
        if picture is None:
            raise HTTPException(status_code=404, detail="No default person is chosen.")
        # The same address for every person: checked each time, so a new one shows at once.
        return FileResponse(picture, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/api/start-now/lines/{name}")
    def get_start_now_line(name: Literal["goodbye", "welcome-back"]) -> FileResponse:
        # In the user's own voice, the avatar's lines are Prepare's (R24d).
        path = job.clip(name) if avatar_in_own_voice() else start_now.clip(name)
        if path is None:
            raise HTTPException(status_code=404, detail="Not ready yet.")
        logger.info("Serving a fixed line", extra={"clip": name, "default_person": True})
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(path, media_type="video/mp4", headers=headers)

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
        available = voice_kind in CLONES
        return AccentChoice(accent=accent() if available else "own", available=available)

    @app.put("/api/accent", dependencies=needs_consent)
    def put_accent(body: AccentRequest, seen: DeletesSeen) -> AccentChoice:
        if body.accent != "own" and voice_kind not in CLONES:
            raise HTTPException(status_code=409, detail=NEEDS_CLONE)
        try:
            with personal_write(seen):
                changed = job.change_voice(lambda: save_accent(data_home, body.accent))
        except PrepareError as e:  # the sample is being made again (R27b)
            raise HTTPException(status_code=409, detail=str(e)) from e
        if not changed:
            # The running job would finish in the old accent; it is chosen before or after it.
            raise HTTPException(status_code=409, detail=WAIT_FOR_PREPARE)
        return get_accent()

    @app.get("/api/prepare/clips/{name}", dependencies=needs_consent)
    def get_clip(name: ClipName) -> FileResponse:
        path = job.clip(name)
        if path is None:
            raise HTTPException(status_code=404, detail="Not prepared yet. Click Prepare first.")
        if name != "sample":  # said on Exit and on Start again (roadmap R29)
            logger.info("Serving a fixed line", extra={"clip": name})
        # no-cache: preparing again replaces it under the same address.
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(path, media_type="video/mp4", headers=headers)

    def accepted() -> bool:
        """Whether the chat is open: a default person is chosen (R24c), or a sample accepted."""
        if start_now.chosen() is not None:
            return True
        return load_review(data_home, job.status()).accepted

    @app.get("/api/review", dependencies=needs_person)
    def get_review() -> dict[str, object]:
        if start_now.chosen() is not None:
            # Whether the user's own sample is accepted too, so setup can switch to it at once.
            # While the avatar is to speak in the user's voice (R24d), the sample is the avatar's.
            sample = load_review(data_home, job.status()).accepted
            own_voice = start_now.own_voice()
            return {
                "accepted": True,
                "accepted_at": None,
                "default_person": True,
                "own_sample_accepted": sample and not own_voice,
                "own_voice": own_voice,
                "voice_accepted": sample and own_voice,
            }
        return asdict(load_review(data_home, job.status()))

    @app.delete("/api/start-now", dependencies=needs_consent)
    def use_own_person(seen: DeletesSeen) -> dict[str, object]:
        """Use your own photo and voice again, from a ready-made avatar, when their sample is
        already accepted: the avatar is no longer chosen, and nothing needs preparing again."""
        start = time.perf_counter()
        with personal_write(seen):
            # While the avatar is to speak in the user's voice, the sample is the avatar's (R24d).
            if start_now.own_voice() or not load_review(data_home, job.status()).accepted:
                logger.warning("Own photo and voice asked for before their sample is accepted")
                raise HTTPException(status_code=409, detail=OWN_NOT_ACCEPTED)
            # A reply being rendered keeps its face and voice.
            if not start_now.forget_unless_busy():
                raise HTTPException(status_code=409, detail=WAIT_FOR_AVATAR)
        start_reply_warm_up()  # the chat now shows the person's own: ready their idle video
        logger.info("Switched to your own photo and voice", extra={"duration_ms": ms_since(start)})
        return asdict(load_review(data_home, job.status()))

    @app.put("/api/start-now/own-voice")
    def use_own_voice(body: ConsentRequest, seen: DeletesSeen) -> dict[str, object]:
        """The ready-made avatar is to speak in the user's own recorded voice (R24d): consent for
        the person in the recordings, then the recordings, Prepare and review as in setup. Until
        the sample is accepted, the avatar keeps its ready-made voice."""
        if not body.agreed:
            raise HTTPException(status_code=400, detail=VOICE_CONSENT_NEEDED)

        def change() -> None:
            save_consent(data_home)  # opens the recordings, Prepare and review
            start_now.set_own_voice(True)

        with data_lock:
            not_deleted_since(seen)
            if start_now.chosen() is None:
                raise HTTPException(status_code=409, detail=NO_AVATAR)
            change_avatar_voice(change)
        return get_review()

    def change_avatar_voice(change: Callable[[], None]) -> None:
        """Under the prepare job's lock, as the accent is: refused while Prepare runs, which
        would finish for the picture and voice from before (Codex's review of PR #131), and
        while the sample is made again or an avatar is got ready."""
        try:
            changed = job.change_voice(change, prepare_again=False)
        except PrepareError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        if not changed:
            logger.warning("Avatar's voice not changed while Prepare runs")
            raise HTTPException(status_code=409, detail=WAIT_FOR_PREPARE_AVATAR)

    @app.delete("/api/start-now/own-voice", dependencies=needs_consent)
    def use_ready_voice(seen: DeletesSeen) -> dict[str, object]:
        """The ready-made avatar speaks in its ready-made voice again (R24d)."""
        with personal_write(seen):
            if start_now.chosen() is not None:
                change_avatar_voice(lambda: start_now.set_own_voice(False))
        return get_review()

    @app.post("/api/review", dependencies=needs_consent)
    def post_review(body: ReviewRequest, seen: DeletesSeen) -> dict[str, object]:
        with personal_write(seen):
            if body.decision != "accept":
                return asdict(withdraw(data_home, body.decision))
            try:
                review = accept(data_home, job.status())
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
            if start_now.own_voice():
                logger.info("The avatar speaks in your own voice now")  # R24d
            else:
                start_now.forget()  # the person is the user's own now
        start_reply_warm_up()  # the chat opens now: ready the LLM and the engines (R22a)
        return asdict(review)

    logger.info(
        "Chat LLM",
        extra={
            "provider": switchable.settings.provider,
            "url": switchable.settings.url,
            "model": switchable.settings.model,
            "context_tokens": llm.context_tokens,
        },
    )
    # While the LLM is busy, the voice and video engines leave it half the cores (R22a), of the
    # performance cores on a CPU that also has efficiency cores (R22g).
    core_share = CoreShare(cores(performance_cores))
    core_share.llm_done()

    # Claude and the other providers run elsewhere, so the engines keep every core while they
    # write (review on PR #111). Asked at each request, as the LLM can be changed (R42).
    def llm_busy() -> AbstractContextManager[object]:
        return core_share.llm() if switchable.local else nullcontext()

    # The chat's requests to the local LLM go before the wiki's (R99): only the requests
    # themselves, so a reply made without the LLM, such as the topics, leaves the wiki alone.
    def local() -> bool:
        return switchable.local

    # Each prompt is looked up in the wiki and PDFs, and the LLM answers from what is found (R40).
    content_lookup = ContentLookup(wiki, readings)

    # Formulas go to the LLM in words, so it says them in full and only one way (Larry,
    # 2026-10-15): "1 divided by the quantity 1 minus the fraction 1 over p to the power of s".
    def find_content(prompt: str) -> list[str]:
        return [math_in_words(p) for p in as_passages(content_lookup.find(prompt))]

    # Prompts are limited to the content only once there is some: before any PDF is added,
    # every prompt is answered. The setting is read each time, so a change on the Settings page
    # (R27) holds from the next prompt.
    def content_only() -> bool:
        allowed = load_ui_settings(data_home, ui_defaults).general_prompts
        return not allowed and bool(wiki.store.list())

    logger.info(
        "Question scope",
        extra={
            "general_prompts": load_ui_settings(data_home, ui_defaults).general_prompts,
            "config_general_prompts": general_prompts,
        },
    )

    # The topics (R41f): the wiki's main entries, read each time, so they follow the PDFs.
    def content_topics() -> list[str]:
        return main_entries(wiki.contents())

    # Whether every PDF has been read and its wiki built, or failed, so the topics are all of
    # them (review on PR #85).
    def topics_complete() -> bool:
        wikis = wiki.statuses()
        reads = readings.statuses()
        for pdf in wiki.store.list():
            built = wikis.get(pdf.id)
            read = reads.get(pdf.id)
            if built is not None and built.state in ("done", "failed"):
                continue
            if read is not None and read.state == "failed":
                continue
            return False
        return True

    if client is not None:
        conversation = Conversation(
            replies_first.asking(client.ask, local),
            client.context_tokens,
            client.count,
            replies_first.streaming(client.stream, local),
            client.warm_up,
            llm_busy=llm_busy,
            find=find_content,
            content_only=content_only,
            topics=content_topics,
            topics_complete=topics_complete,
            saved=data_home / CONVERSATION_FILE,
        )
    else:
        assert ask_llm is not None
        conversation = Conversation(
            replies_first.asking(ask_llm, local),
            lambda: llm.context_tokens,
            stream=stream_llm and replies_first.streaming(stream_llm, local),
            warm_up=warm_up_llm,
            llm_busy=llm_busy,
            find=find_content,
            content_only=content_only,
            topics=content_topics,
            topics_complete=topics_complete,
            saved=data_home / CONVERSATION_FILE,
        )

    # The LLM setting (R42): which LLM answers, with the user's API key for a provider.
    @app.get("/api/llm")
    def get_llm() -> dict[str, Any]:
        return described(load_choice(data_home), plan_ready())

    def plan_ready() -> bool:
        """Whether a ChatGPT account is signed in that allowed use of its plan (R43a)."""
        status = signin.status()
        return bool(status["connected"] and status["plan_usage"])

    def need_plan_sign_in() -> None:
        """400 saying why when there is no ChatGPT sign-in to use for its plan."""
        try:
            signin.access_token()
        except SignInError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    def plan_list() -> tuple[list[str], dict[str, str]]:
        """The models in the ChatGPT plan's list, fetched with the sign-in held until the list
        has come, so Disconnect, a switch or a sign-in waits for it and none is fetched with a
        token after Disconnect (a review on PR #118). LlmError, in plain words, when there is no
        sign-in to use."""
        with signin.plan_session() as token:
            return model_lists.named_models("chatgpt", token)

    def plan_model(model: str | None) -> str | None:
        """The model to save for the ChatGPT plan: the one entered, the one saved when none is
        entered, or else the first in the plan's list (R43a), since no model is right for every
        plan."""
        need_plan_sign_in()  # a model entered is saved only with a sign-in to use it
        if model and model.strip():
            return model
        if model is None and load_choice(data_home).models.get("chatgpt"):
            return None
        try:
            return plan_list()[0][0]
        except LlmError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ModelListError as e:
            raise HTTPException(
                status_code=400 if e.refused else 502,
                detail=f"{e} Type a model's name to use the plan without the list.",
            ) from e

    model_lists = ModelLists()
    # A change is saved and made live as one step, so two made together can't leave the file
    # saying one LLM while the other answers (a review on PR #115).
    changing_llm = threading.Lock()

    @app.put("/api/llm")
    def put_llm(body: LlmRequest) -> dict[str, Any]:
        start = time.perf_counter()
        key = (body.api_key or "").strip()
        model = body.model
        if body.provider == "chatgpt":
            model = plan_model(model)  # needs the sign-in, not a key
        elif key and body.provider in PROVIDERS and body.provider != "local":
            # A new key is checked first by listing the provider's models (Larry, 2026-10-19),
            # so a key the provider refuses isn't saved; if the provider can't be reached, the
            # key is saved unchecked, and the chat says so if it's wrong.
            try:
                model_lists.models(body.provider, key)
            except ModelListError as e:
                if e.refused:
                    raise HTTPException(
                        status_code=400, detail=f"{e} Check it and paste it again."
                    ) from e
                logger.warning(
                    "Could not check the API key; saving it unchecked",
                    extra={"provider": body.provider, "reason": str(e)},
                )
        with changing_llm:
            try:
                choice = save_choice(data_home, body.provider, body.api_key, model)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            switchable.use(choice)
        # From the next request; llama-server reads the system prompt again now (R22a).
        threading.Thread(target=conversation.warm_up, name="llm-warm-up", daemon=True).start()
        logger.info(
            "LLM setting changed",
            extra={"provider": choice.provider, "duration_ms": ms_since(start)},
        )
        return described(choice, plan_ready())

    # The models a provider offers to the key just entered, or the saved one (R42); OpenRouter's
    # before any key. 400 when the key is missing or refused, 502 when the provider can't be
    # reached, so the page offers a typed model name only then.
    @app.post("/api/llm/models")
    def post_llm_models(body: ModelsRequest) -> dict[str, Any]:
        if body.provider not in PROVIDERS:
            raise HTTPException(status_code=400, detail=f"There is no LLM called {body.provider}.")
        key = ""
        if body.provider != "chatgpt":
            key = (body.api_key or "").strip() or load_choice(data_home).keys.get(body.provider, "")
        try:
            if body.provider == "chatgpt":
                # The plan's own list, with the signed-in account's token, shown by the names
                # the plan gives them (R43a).
                try:
                    ids, names = plan_list()
                except LlmError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e
                return {"models": ids, "names": names}
            ids = model_lists.models(body.provider, key)
            return {"models": ids}
        except ModelListError as e:
            p = PROVIDERS[body.provider]
            asked = body.provider == "chatgpt" or (
                body.provider != "local" and bool(key or p.lists_freely)
            )
            status = 502 if asked and not e.refused else 400
            raise HTTPException(status_code=status, detail=str(e)) from e

    # Sign in with ChatGPT (R43): the browser is sent to OpenAI to sign in, and comes back to
    # this app's own address on 127.0.0.1, where the server swaps the code for the tokens.

    @app.get("/api/chatgpt")
    def get_chatgpt() -> dict[str, Any]:
        return signin.status()

    @app.get("/api/chatgpt/sign-in", response_model=None)
    def chatgpt_sign_in(
        request: Request, consent: bool = False, another: bool = False, account: str = ""
    ) -> Response:
        # OpenAI sends the browser back to the loopback address, on the port the app is on.
        # `consent` asks again for plan use; `another` registers another ChatGPT account;
        # `account` signs in again as one registered before.
        redirect_uri = f"http://127.0.0.1:{request.url.port or 80}{CALLBACK_PATH}"
        try:
            location = signin.start(redirect_uri, consent, another, account)
            return RedirectResponse(location, status_code=303)
        except SignInError as e:
            return signed_in_page(str(e), 502)

    @app.get(CALLBACK_PATH, response_model=None)
    def chatgpt_callback(request: Request) -> Response:
        try:
            signin.finish(dict(request.query_params))
        except SignInError as e:
            return signed_in_page(str(e), 400)
        follow_plan_account()
        return RedirectResponse("/#/settings", status_code=303)

    @app.post("/api/chatgpt/use")
    def chatgpt_use(body: ChatGptAccount) -> dict[str, Any]:
        try:
            status = signin.use(body.account)
        except SignInError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        follow_plan_account()
        return status

    def follow_plan_account() -> None:
        """When the ChatGPT plan answers and another account is now in use, its saved model is
        checked against that account's own list, and the list's first is saved in its place if
        it isn't there, so the next prompt doesn't ask for a model the account can't use (a
        review on PR #118). Nothing changes when the list can't be had; the chat then says
        why."""
        if load_choice(data_home).provider != "chatgpt":
            return
        try:
            models = plan_list()[0]
        except (LlmError, ModelListError) as e:
            logger.warning("Could not check the ChatGPT plan's model", extra={"reason": str(e)})
            return
        with changing_llm:
            choice = load_choice(data_home)
            if choice.provider != "chatgpt" or choice.model("chatgpt") in models:
                return
            was = choice.model("chatgpt")
            choice = save_choice(data_home, "chatgpt", model=models[0])
            switchable.use(choice)
        logger.info(
            "ChatGPT plan model changed for the account in use",
            extra={"was": was, "model": models[0]},
        )

    @app.post("/api/chatgpt/sign-out")
    def chatgpt_sign_out() -> dict[str, Any]:
        return signin.sign_out()

    @app.get("/api/chat", dependencies=needs_person)
    def get_chat() -> dict[str, object]:
        return {"turns": [asdict(t) for t in conversation.turns()]}

    @app.get("/api/chat/summary", dependencies=needs_person)
    def chat_summary() -> dict[str, bool]:
        """Whether the conversation's older turns are being summarized, which the next prompt
        waits for (`imageskin time-pdf` waits for it too, R98a)."""
        return {"summarizing": conversation.summarizing()}

    def require_accepted() -> None:
        if not accepted():
            raise HTTPException(status_code=403, detail=CHAT_LOCKED)

    # The reply clips use the two steps apart (R22b); an engine given as one `render_clip`
    # does both in its video step.
    replies = ReplyVideos(
        data_home,
        reply_render,
        voice_ready,
        clip_steps or (None if render_clip else reply_steps),
        before_engines=core_share.apply_here,
    )
    # The latest streamed reply's clips, rendered sentence by sentence (roadmap R21), by its id.
    sentence_clips: dict[str, SentenceClips] = {}
    clips_lock = threading.Lock()  # guards sentence_clips, used by several request threads
    # Replies stopped in the browser before their prompt reached chat() (roadmap R19): no clips
    # are made for them. Guarded by clips_lock.
    stopped_early: set[str] = set()
    # Replies spoken in one video (not streamed) being made now, each with the event Stop sets
    # (roadmap R19). Guarded by clips_lock.
    whole_videos: dict[str, threading.Event] = {}
    # Prompts being answered, each with the event Stop sets to cut the LLM off (Larry's test of
    # PR #129: Stop left it thinking). Guarded by clips_lock.
    prompts: dict[str, PromptStop] = {}
    # One prompt at a time, from dropping the last reply's clips to keeping this one's, so a
    # prompt waiting on another always drops that one's clips.
    chat_lock = threading.Lock()

    def chosen_photo() -> Path | None:
        if start_now.chosen() is not None:
            return start_now.picture()
        return store.path("photos", job.status().photo_id or "")

    @app.get("/api/chat/hints", dependencies=needs_person)
    def get_chat_hints() -> dict[str, object]:
        """What to show under the prompt box (R41g): a line naming a few of the topics, and a few
        example questions drawn from the wiki, read each time so they follow the PDFs."""
        topics = content_topics()
        examples = content_lookup.examples() if topics else []
        complete = topics_complete()
        line = hint_line(topics, content_only(), complete)
        logger.info(
            "Topic hints",
            extra={"topics": len(topics), "examples": len(examples), "complete": complete},
        )
        return {"line": line, "examples": examples}

    @app.get("/api/chat/photo", dependencies=needs_person)
    def get_chat_photo() -> dict[str, str | int | None]:
        """The photo the videos are made from, with its size as shown, so the chat can give the
        person's frame its shape before anything is drawn (roadmap R41d)."""
        photo_id = job.status().photo_id
        photo = chosen_photo()
        size = None if photo is None else shown_size(photo)
        url = f"/api/uploads/photos/{photo_id}"
        chosen = start_now.chosen()
        if chosen is not None:
            # Each person gets an address of their own: a browser keeps an image it has shown
            # for the page's life, so one address for all would show the person before.
            url = f"/api/start-now/picture?person={chosen.name}"
        return {
            "url": None if photo is None else url,
            "width": size[0] if size else None,
            "height": size[1] if size else None,
            # The same for the idle video, named after the photo it is made from.
            "idle": None if photo is None else f"/api/chat/idle?photo={quote(photo.stem)}",
        }

    @app.post("/api/chat", dependencies=[*needs_person, Depends(require_accepted)])
    def post_chat(body: ChatRequest, seen: DeletesSeen) -> dict[str, Any]:
        """The reply, with its place in the conversation to ask for its video by, and whether it
        was streamed: then its clips are made sentence by sentence (roadmap R22) and the
        browser follows those, even once a newer prompt has taken them, rather than asking for
        the whole video."""
        # Listed before it waits for the warm-up or another prompt, so Stop reaches it there.
        stop = PromptStop()
        if body.reply_id is not None:
            with clips_lock:
                prompts[body.reply_id] = stop
        # Where the time goes, returned with the reply for `imageskin time-reply` (R96).
        times = ReplyTimes(received_at=time.perf_counter())
        timing = reply_times.current.set(times)
        try:
            times.waited_warm_up_ms = wait_for_warm_up()
            asked = time.perf_counter()
            # One LLM answers the whole prompt, even if it is changed meanwhile (review on
            # PR #115).
            with chat_lock, pinned(client), llm_busy():
                times.waited_turn_ms = ms_since(asked)
                not_deleted_since(seen)  # a prompt sent before Delete my data is never kept (R31)
                token = ask_stop.set(stop)  # the LLM is cut off on Stop
                try:
                    answer = chat(body, stop)
                finally:
                    ask_stop.reset(token)
            times.answered_at = time.perf_counter()
            log_reply_times(times)
            return {**answer, "timings": times.as_dict()}
        finally:
            reply_times.current.reset(timing)
            if body.reply_id is not None:
                with clips_lock:
                    if prompts.get(body.reply_id) is stop:
                        del prompts[body.reply_id]

    def wait_for_warm_up(what: str = "Prompt") -> float:
        """A prompt sent right after the sample was accepted waits for the warm-up to finish,
        so it doesn't reach the LLM while the LLM is still reading the system prompt, or the
        engines while they render their first word (a review finding on R22a). The wait has
        no cap of its own: the LLM's timeout and ffmpeg's bound the warm-up's steps. Returns
        how long it waited, in milliseconds."""
        thread = app.state.reply_warm_up
        if not thread.is_alive():
            return 0.0
        start = time.perf_counter()
        thread.join()
        waited = ms_since(start)
        logger.info(f"{what} waited for the warm-up", extra={"wait_ms": waited})
        return waited

    def log_reply_times(times: ReplyTimes) -> None:
        """The reply's times in the log, in milliseconds from the prompt's arrival (R96)."""

        def since(at: float | None) -> float | None:
            return None if at is None else round((at - times.received_at) * 1000, 1)

        logger.info(
            "Reply timings",
            extra={
                "waited_warm_up_ms": times.waited_warm_up_ms,
                "waited_turn_ms": times.waited_turn_ms,
                "history_tokens": times.history_tokens,
                "first_token_ms": since(times.first_token_at),
                "first_sentence_ms": since(times.first_sentence_at),
                "last_token_ms": since(times.last_token_at),
                "duration_ms": since(times.answered_at),
                **{f"llm_{k}": v for k, v in (times.llm or {}).items()},
            },
        )

    tutor = Tutor(wiki.contents, find_content, topics_complete)

    # Each topic's first lesson part, written ahead once the wiki is built (R98a), after the
    # chat's requests to the LLM (R99).
    plain_ask = client.ask if client is not None else ask_llm
    assert plain_ask is not None
    lesson_ask = replies_first.wiki(plain_ask)

    def write_lesson(teach: Teach) -> str:
        # The engines leave a local LLM its share of the cores, as for a reply (R22a): a
        # topic said from its saved part is spoken while the next one is written.
        with pinned(client), llm_busy():
            return lesson_ask(conversation.asked_alone(teach))

    lessons = None
    if lessons_ahead or (lessons_ahead is None and ask_llm is None):
        lessons = LessonsAhead(
            wiki.folder,
            tutor.first_parts,
            write_lesson,
            lambda: load_ui_settings(data_home, ui_defaults).teach_me,
            wiki.building,
        )
    app.state.lessons = lessons

    def when_wiki_idle() -> None:
        # Wiki builds use the LLM too, which can push the chat's system prompt out of
        # llama-server's memory; it is read again once they are done, then the lessons are
        # written.
        conversation.warm_up()
        if lessons is not None:
            lessons.refresh()

    # Before the first round, so a build already under way (from catch_up) that ends before
    # that round's check still starts a round after it.
    wiki.when_idle = when_wiki_idle
    if lessons is not None:
        wiki.when_changed = lessons.refresh
        lessons.refresh()  # those missing since the last start

    @app.get("/api/lessons")
    def lessons_status() -> dict[str, Any]:
        """Whether the lessons are being written ahead, and the topics saved (R98a)."""
        if lessons is None:
            return {"wanted": False, "writing": False, "ready": False, "saved": []}
        return lessons.status()

    quizzer = Quizzer(wiki.contents, find_content, conversation.write, topics_complete)
    assessor = Assessor(wiki.contents, find_content, conversation.write, topics_complete)

    def lesson_parts(lesson: Lesson) -> int:
        """How many parts the lesson's topic has, its summary not counted."""
        return len(lesson_topics(wiki.contents()).get(lesson.topic, []))

    # The replies to the example questions under the prompt box, kept once made (R130a).
    topic_replies = TopicReplies(replies.folder / "topics")

    def example_context(prompt: str) -> str | None:
        """What a reply to this prompt is made with, when it is one of the example questions
        shown now; None otherwise."""
        if not content_topics():
            return None
        if prompt.strip() not in content_lookup.examples():
            return None
        photo = chosen_photo()
        status = job.status()
        voice = reply_preset() or job.voice_id()
        person = None if photo is None else replies.idle_name(photo)
        return context_of(person, voice, status.finished_at, wiki.contents(), content_only())

    def answer_example(prompt: str, context: str, clips: SentenceClips) -> tuple[Turn, int]:
        """An example question's reply: the one kept, said at once, or the LLM's, kept once its
        clips are all rendered."""
        start = time.perf_counter()
        kept = topic_replies.get(prompt, context)
        if kept is None:
            epoch = topic_replies.epoch  # not kept if the conversation is cleared meanwhile
            reply, turn = conversation.send(prompt, clips)
            text = reply.content
            clips.on_complete = lambda made: topic_replies.keep(prompt, context, text, made, epoch)
            logger.info("Topic reply not kept yet", extra={"question": prompt})
            return reply, turn
        reply, turn = conversation.say(prompt, [kept.text])
        try:
            clips.replay(kept.clips)
        except OSError as e:  # the reply stands; the browser asks for its whole video
            logger.error("Could not play a kept topic reply", extra={"error": str(e)})
        logger.info(
            "Topic reply from the kept one",
            extra={"question": prompt, "clips": len(kept.clips), "duration_ms": ms_since(start)},
        )
        return reply, turn

    def chat(body: ChatRequest, stop: PromptStop) -> dict[str, Any]:
        with clips_lock:
            unasked = list(sentence_clips.values())  # only the latest reply is played
            sentence_clips.clear()
            if body.reply_id in stopped_early:  # stopped before it came: it isn't answered
                stopped_early.discard(body.reply_id)
                stop.stop()
        for old in unasked:
            old.cancel()
        if stop.is_set():
            logger.info("Prompt stopped before it was answered", extra={"reply_id": body.reply_id})
            raise HTTPException(status_code=409, detail=PROMPT_STOPPED)
        photo = chosen_photo()
        clips = None
        if photo is not None and body.reply_id is not None:
            clips = replies.sentence_clips(photo, body.reply_id)
            with clips_lock:
                if stop.is_set():  # stopped meanwhile: no clips
                    clips = None
                else:
                    sentence_clips[body.reply_id] = clips  # asked for while the LLM writes
        start = time.perf_counter()
        try:
            if body.spoken:
                # Checked and the summary waited for before the correction asks the LLM, as
                # for a lesson, quiz or assessment (review on PR #91).
                conversation.check(body.prompt)
                meant = corrected(body.prompt, vocabulary(wiki.contents()), conversation.write)
                body = body.model_copy(update={"prompt": meant})
            lesson = None if body.lesson is None else Lesson(**body.lesson.model_dump())
            quiz = None
            if body.quiz is not None:
                kept = body.quiz.model_dump()
                quiz = Quiz(
                    **{**kept, "asked": tuple(kept["asked"]), "review": tuple(kept["review"])}
                )
            assessment = None
            if body.assessment is not None:
                kept = body.assessment.model_dump()
                answers = tuple(Answer(**a) for a in kept.pop("answers"))
                assessment = Assessment(**kept, answers=answers)
            # With Teach me, Quiz me or Assessment off in the settings, "Teach me", "Quiz me" or
            # "Assess me" is an ordinary prompt (R41h, R41i, R41j). An assessment going takes the
            # answer before a quiz does, and a quiz before a lesson.
            settings = load_ui_settings(data_home)
            if settings.quiz_me or settings.teach_me or settings.assessment:
                conversation.check(body.prompt)  # before any of them asks the LLM
            assessed = None
            if settings.assessment:
                assessed = assessor.step(body.prompt, assessment)
            asking = None
            if assessed is None and settings.quiz_me:
                asking = quizzer.step(body.prompt, quiz)
            step = None
            if asking is None and settings.teach_me:
                step = tutor.step(body.prompt, lesson)
            choices: list[Choice] = []
            if assessed is not None:
                reply, turn = conversation.say(body.prompt, assessed.sentences, clips)
                assessment = assessed.assessment
                choices = assessed.choices if settings.teach_me else []
            elif isinstance(asking, Said):
                reply, turn = conversation.say(body.prompt, asking.sentences, clips)
                quiz, choices = asking.quiz, asking.choices
            elif isinstance(asking, Judge):
                reply, turn = conversation.send(body.prompt, clips, asking.teach)
                quiz = asking.quiz  # set by the judging, once the reply is in
            elif isinstance(step, Say):
                reply, turn = conversation.say(body.prompt, step.sentences, clips)
                lesson, choices = step.lesson, step.choices
            elif isinstance(step, Explain):
                ahead = None if lessons is None else lessons.saved(step.lesson.topic, step.teach)
                if ahead is not None:  # its first part, written ahead (R98a)
                    logger.info(
                        "Lesson from the saved part",
                        extra={"topic": step.lesson.topic, "sentences": len(ahead)},
                    )
                    reply, turn = conversation.say(body.prompt, ahead, clips)
                else:
                    reply, turn = conversation.send(body.prompt, clips, step.teach)
                lesson = step.lesson
                if step.kind == "summary" and settings.quiz_me:  # a quick quiz on the topic
                    topic = step.lesson.topic
                    choices = [Choice(f"Quiz me on {topic}", f"Quiz me on {topic}")]
            elif clips is not None and (example := example_context(body.prompt)) is not None:
                reply, turn = answer_example(body.prompt, example, clips)
            else:
                reply, turn = conversation.send(body.prompt, clips)
        except (ValueError, LlmError, LlmCancelled) as e:
            if clips is not None:
                with clips_lock:
                    sentence_clips.pop(body.reply_id or "", None)
                clips.cancel()
            if isinstance(e, LlmCancelled):
                logger.info(
                    "Prompt stopped",
                    extra={"reply_id": body.reply_id, "duration_ms": ms_since(start)},
                )
                raise HTTPException(status_code=409, detail=PROMPT_STOPPED) from e
            status = 400 if isinstance(e, ValueError) else 502
            raise HTTPException(status_code=status, detail=str(e)) from e
        if clips is not None:
            clips.close()
            if not clips.sentences:  # not streamed: the browser asks for the whole video
                with clips_lock:
                    sentence_clips.pop(body.reply_id or "", None)
        streamed = clips is not None and clips.sentences > 0
        # The lesson after this prompt, for the browser to keep, with how many parts its topic
        # has, and any choices to show as buttons (R41h).
        return {
            **asdict(reply),
            "turn": turn,
            "streamed": streamed,
            "lesson": None if lesson is None else {**asdict(lesson), "parts": lesson_parts(lesson)},
            "choices": [asdict(c) for c in choices],
            # The quiz after this prompt, for the browser to keep, with how many questions a
            # quiz has (R41i).
            "quiz": None if quiz is None else {**asdict(quiz), "questions": QUESTIONS},
            # The assessment after this prompt, for the browser to keep (R41j).
            "assessment": None if assessment is None else asdict(assessment),
            # A spoken prompt as it was answered, so the browser shows it that way (R24).
            **({"prompt": body.prompt} if body.spoken else {}),
        }

    @app.post("/api/chat/clips/{reply_id}/stop", dependencies=needs_person)
    def stop_clips(reply_id: str = PathParam(pattern=REPLY_ID_PATTERN)) -> dict[str, bool]:
        """Stop a reply (roadmap R19): no more clips are made, the one being made is dropped
        after the step under way, and the files are removed. A prompt still being answered is
        stopped too: the LLM is cut off and the prompt dropped (Larry's test of PR #129); one
        that hasn't come yet is dropped when it does. Answers at once; the step under way
        finishes on a thread of its own."""
        with clips_lock:
            clips = sentence_clips.pop(reply_id, None)
            video = whole_videos.get(reply_id)
            prompt = prompts.get(reply_id)
            # Not once its reply is kept: then only its clips or video are stopped.
            answering = prompt is not None and prompt.stop()
            if video is not None:
                video.set()  # its render stops before its next step
            elif clips is None and not answering:
                if len(stopped_early) >= STOPPED_EARLY_MAX:  # ids that never came: forget them
                    stopped_early.clear()
                stopped_early.add(reply_id)
        logger.info(
            "Reply stopped",
            extra={
                "reply_id": reply_id,
                "clips": None if clips is None else len(clips.clips),
                "whole_video": video is not None,
                "answering": answering,
            },
        )
        if clips is not None:
            threading.Thread(target=cancel_clips, args=(clips,), name="stop-clips").start()
        return {"stopped": clips is not None or video is not None or answering}

    def cancel_clips(clips: SentenceClips) -> None:
        start = time.perf_counter()
        try:
            clips.cancel()
        except Exception:
            logger.exception("Could not stop a reply's clips", extra={"folder": str(clips.folder)})
            return
        logger.info("Reply clips stopped", extra={"duration_ms": ms_since(start)})

    CLIP_FOLLOW_S = 0.05  # how often a clip still being rendered is read for more of it

    @app.get("/api/chat/clips/{reply_id}", dependencies=needs_person)
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
            with clips_lock:
                if sentence_clips.get(reply_id) is not clips:  # a newer prompt took them meanwhile
                    raise HTTPException(status_code=404, detail="No clips for that reply.")
        made = [
            {
                "url": f"/api/chat/clips/{reply_id}/{n}",
                "sentence_at": t.sentence_at,
                "ready_at": t.ready_at,
                # When its voice step began and when its video was whole (R96).
                "started_at": t.started_at,
                "whole_at": clips.whole_at[n - 1] if n <= len(clips.whole_at) else None,
            }
            for n, t in enumerate(clips.times[: len(clips.clips)], 1)
        ]
        return {
            "clips": made,
            "done": clips.done,
            "error": clips.error,
            "now": time.perf_counter(),
        }

    @app.get("/api/chat/clips/{reply_id}/{n}", dependencies=needs_person)
    def get_clip_file(reply_id: str, n: int) -> Response:
        """The clip, whole once it is rendered; while it is still being rendered, as much of it
        as there is and then the rest as it is written (roadmap R22d), so the browser can start
        playing it meanwhile."""
        with clips_lock:
            clips = sentence_clips.get(reply_id)
        # Its file and whether it is whole, taken at once: a clip whose video fails meanwhile
        # is unlisted, and its stream then ends with what there was.
        found = None if clips is None else clips.clip(n)
        if clips is None or found is None:
            raise HTTPException(status_code=404, detail="No such clip.")
        path, whole = found
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        if whole:
            return FileResponse(path, media_type="video/mp4", headers=headers)
        return StreamingResponse(
            clips.follow(n, path, CLIP_FOLLOW_S), media_type="video/mp4", headers=headers
        )

    def warm_up_replies() -> Path | None:
        """The photo warmed up for. Only once a sample is accepted: before that the chat is
        locked and Prepare loads them. Run at the start, and again when a sample is accepted."""
        photo = chosen_photo()
        if photo is not None and accepted():
            logger.info("Warming up replies")
            # On its own thread: an LLM that accepts the request but doesn't answer would
            # otherwise hold the engines' warm-up back for its whole timeout.
            warm_llm = startup.timed("LLM warm-up", conversation.warm_up)
            llm = threading.Thread(target=warm_llm, name="llm-warm-up", daemon=True)
            llm.start()
            startup.timed("voice and video warm-up", lambda: replies.warm_up(photo))()
            llm.join()
        return photo

    # Whether a warm-up worker still has work to do, and whether one was asked for meanwhile:
    # both only read and changed under warm_up_lock. The worker gives up the work under the lock
    # in the same step as it decides to stop, so a request after that starts a worker of its
    # own, even while the old thread is still ending (review on PR #122).
    warm_up_lock = threading.Lock()  # also guards app.state.reply_warm_up
    warm_up = {"running": False, "again": False}

    app.state.warm_up = warm_up

    def warm_up_until_current() -> None:
        startup.begin("reply warm-up")
        while True:
            try:
                photo = warm_up_replies()
            except Exception:
                # Never left running: Start now waits on it before opening the chat.
                logger.exception("Could not warm up replies")
                photo = None
            with warm_up_lock:
                again = warm_up["again"] and chosen_photo() != photo
                warm_up["again"] = False
                if not again:
                    warm_up["running"] = False
                    break
            logger.info("Warming up replies again for the person chosen meanwhile")
        startup.end("reply warm-up")
        logger.info("Reply warm-up done")

    def warming_up() -> bool:
        """Whether replies are being warmed up for the person chosen now."""
        with warm_up_lock:
            return warm_up["running"]

    def start_reply_warm_up() -> None:
        """Warm up replies on a thread of their own. While a warm-up is under way, that thread
        is kept, as the one prompts wait for, so a second accept doesn't put a thread that does
        nothing in its place; if the person changed meanwhile (a default person chosen while
        the last one's warm-up ran, Larry's test of R32a), it runs once more for the new one,
        so they get their own idle video."""
        with warm_up_lock:
            if warm_up["running"]:
                warm_up["again"] = True
                return
            warm_up["running"] = True
            app.state.reply_warm_up = threading.Thread(
                target=warm_up_until_current, name="reply-warm-up", daemon=True
            )
            app.state.reply_warm_up.start()

    start_reply_warm_up()
    app.state.loading.append(app.state.reply_warm_up)
    # A chosen default person whose voice changed (R24e) says Goodbye and Welcome back in it.
    try:
        start_now.refresh()
    except PrepareError as e:  # Prepare carried on from before: they come when chosen again
        logger.warning("Default person's lines not rendered again", extra={"error": str(e)})

    @app.post("/api/chat/video", dependencies=[*needs_person, Depends(require_accepted)])
    def post_reply_video(body: ReplyVideoRequest) -> dict[str, str | None]:
        """Speak a reply in the person's voice and render it on their photo, for an LLM that
        doesn't stream. The video's address, or null when the reply has nothing to say aloud."""
        # Listed before the reply is looked up, so Clear conversation (R27b) stops it whether it
        # comes before or after; one without the browser's id is listed under one of its own.
        stop = threading.Event()
        key = body.reply_id or f"video-{id(stop)}"
        with clips_lock:
            if body.reply_id in stopped_early:  # stopped before it was asked for
                stopped_early.discard(body.reply_id)
                stop.set()
            whole_videos[key] = stop
        try:
            # Read before the turns: a clear after this drops the video (R27b), and the turns
            # read after a clear are the new conversation's.
            generation = replies.generation
            turns = conversation.turns()
            if not 0 <= body.turn < len(turns) or turns[body.turn].role != "assistant":
                raise HTTPException(status_code=404, detail=NO_SUCH_REPLY)
            photo = chosen_photo()
            if photo is None:
                raise HTTPException(
                    status_code=409, detail="The photo was removed. Choose another."
                )
            try:
                path = replies.render(
                    photo, body.turn, turns[body.turn].content, stop.is_set, generation
                )
            except Exception as e:
                # The voice and video engines' errors say what went wrong; the reply is still
                # shown.
                raise HTTPException(status_code=502, detail=str(e)) from e
        finally:
            with clips_lock:
                if whole_videos.get(key) is stop:
                    del whole_videos[key]
        return {"video": None if path is None else f"/api/chat/videos/{body.turn}"}

    @app.post("/api/prepare/clips/sample/again", dependencies=needs_consent)
    def run_video_test_again() -> dict[str, object]:
        """Run the video test again from Settings (roadmap R27b): render the sample video afresh
        from the prepared face and voice. It waits for any prompt being answered and holds the
        engines, so a reply and the sample are never made at once."""
        if job.clip("sample") is None:  # said at once, before the engines are made ready
            raise HTTPException(status_code=409, detail=NOT_PREPARED)
        try:
            with chat_lock, replies.engines():
                seconds = job.render_sample_again()
        except PrepareError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except Exception as e:
            # A reason and a reference for support, the full error in the log (roadmap R134).
            failure = report(e, logger, "Could not run the video test again", data_home)
            detail = f"The sample video couldn't be made again. {failure.summary()}"
            raise HTTPException(status_code=502, detail=detail) from e
        return {"video": "/api/prepare/clips/sample", "seconds": seconds}

    @app.delete("/api/chat", dependencies=needs_person)
    def clear_chat(seen: DeletesSeen) -> dict[str, int]:
        """Clear conversation from Settings (roadmap R27b), once the browser has asked to
        confirm. It waits for a prompt being answered, so that reply is cleared too."""
        with chat_lock:
            # A clear that waited for Delete my data would save an empty conversation again
            # (review on PR #109).
            not_deleted_since(seen)
            # The conversation first, so that if it can't be cleared nothing is (R30). With the
            # lock held no prompt is being answered, so the reply videos still being made are
            # from replies already in it.
            cleared = clear_conversation()
        return {"cleared": cleared}

    def clear_conversation() -> int:
        """Clear the conversation and its videos, with chat_lock held; HTTP 500 if the saved
        conversation can't be emptied, and then nothing is cleared."""
        try:
            cleared = conversation.clear()
        except ClearFailed as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        # The replies' videos go too: those being made are stopped and never published,
        # and those made are removed, so none of what was said can still be played.
        with clips_lock:
            streamed = list(sentence_clips.values())
            sentence_clips.clear()
            for stop in whole_videos.values():
                stop.set()
        for clips in streamed:
            threading.Thread(target=cancel_clips, args=(clips,), name="clear-clips").start()
        # After the conversation: a video asked for after replies.clear() reads it empty.
        videos = replies.clear()
        # The example questions' replies were made with what was said, so they go too (Codex's
        # review of PR #178).
        topic_replies.clear()
        logger.info(
            "Reply videos cleared",
            extra={"videos": videos, "streamed_replies": len(streamed)},
        )
        return cleared

    # No consent needed: a delete that left a file behind removed the consent already, and
    # it is tried again from the same page.
    def forget_person() -> None:
        """Drop what the engines keep in memory of the person (the learned voice and the loaded
        face), with the engines held and no Prepare running (review on PR #109)."""
        voice_ready.forget()
        forget_voice = getattr(voice_engine, "forget_voice", None)
        if forget_voice is not None:
            forget_voice()
        for kept in (steps, reply_steps):
            if kept.forget is not None:
                kept.forget()

    def forget_pdfs() -> None:
        """Remove each PDF as Manage Content's Remove does (R31a), so a reading or wiki build
        of it stops and saves nothing more; what is left in the content folder, such as the
        lessons and the saved versions, goes with the rest of the data."""
        start = time.perf_counter()
        pdfs = content.list()
        for pdf in pdfs:
            try:
                content.remove(pdf.id)
            except UploadError:
                pass  # logged; delete_my_data lists the PDF as left
            readings.forget(pdf.id)
            wiki.forget(pdf.id)
        # A reading under way stops at its next page and lets its private copy go, which
        # Windows couldn't delete while it is open (Codex's review).
        readings.wait(READING_STOP_S)
        # A round of lessons under way, or the one wiki.forget asked for, saves nothing now.
        if lessons is not None:
            lessons.forget()
        logger.info(
            "PDFs forgotten",
            extra={
                "pdfs": len(pdfs),
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )

    @app.delete("/api/data")
    def delete_data() -> dict[str, object]:
        """Delete my data from Settings (roadmap R31), once the browser has asked to confirm:
        the photos, recordings, prepared face and voice, videos and conversation, and the PDFs
        with all made from them (R31a), so setup starts again. Refused while setup is
        preparing; nothing is removed then."""
        wait_for_warm_up("Delete my data")

        def delete() -> Deleted:
            clear_conversation()
            forget_pdfs()
            # Once the streamed clips stopped above have let the engines go, nothing writes
            # a video while the files are removed.
            with replies.paused():
                deleted = delete_my_data(data_home)
                forget_person()
            deletes[0] += 1  # requests that arrived before this write nothing now
            return deleted

        # All of it under the job's lock, which forget() takes before deleting anything: a
        # Prepare started first refuses the delete with nothing cleared, and one started
        # meanwhile waits for it (review on PR #109). data_lock keeps the other writers of these
        # files out. The lock order is chat_lock, data_lock, the job's lock, then the engines;
        # the writers take data_lock before the job's, and nothing holding the engines takes
        # the job's lock.
        with chat_lock, data_lock:
            try:
                deleted = job.forget(delete)
            except PrepareError as e:
                raise HTTPException(status_code=409, detail=str(e)) from e
        return asdict(deleted)

    @app.get("/api/chat/idle", dependencies=needs_person)
    def get_idle_video() -> FileResponse:
        """The person at rest, blinking and moving slightly, shown on a loop between replies
        (roadmap R23). Made by the warm-up, so a request during it waits for it."""
        wait_for_warm_up("Idle video")
        photo = chosen_photo()
        path = None if photo is None else replies.idle(photo)
        if path is None:
            raise HTTPException(status_code=404, detail="No idle video.")
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(path, media_type="video/mp4", headers=headers)

    @app.get("/api/chat/videos/{turn}", dependencies=needs_person)
    def get_reply_video(turn: int) -> FileResponse:
        path = replies.video(turn)
        if path is None:
            raise HTTPException(status_code=404, detail="No video for that reply.")
        headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"}
        return FileResponse(path, media_type="video/mp4", headers=headers)

    # Last, so /health and /api routes win over the static files.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    startup.end("app made")
    return app
