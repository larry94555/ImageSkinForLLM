// Calls to the server's JSON API.

export interface Consent {
  agreed: boolean;
  agreed_at: string | null;
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function getConsent(): Promise<Consent> {
  return json<Consent>(await fetch("/api/consent"));
}

export async function confirmConsent(): Promise<Consent> {
  return json<Consent>(
    await fetch("/api/consent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agreed: true }),
    }),
  );
}

export type Kind = "photos" | "sounds";

export interface Upload {
  id: string;
  kind: Kind;
  name: string;
  format: string;
  size: number;
  uploaded_at: string;
  seconds: number | null;
  // What the photo or sound checks found ([] when it passed), or null when not checked.
  problems: string[] | null;
  // Photos that passed the checks: 0 to 100, higher is better.
  score: number | null;
  // Checked recordings: seconds of speech, pauses not counted.
  speech: number | null;
}

// The photo the video will be made from (id null until a photo passes the checks): the best
// scoring one, picked by the app, or the one the user chose.
export interface PhotoChoice {
  id: string | null;
  chosen_by: "app" | "you";
}

// The recordings that passed the sound checks, joined into one. problem says what is missing
// while there is not enough speech for the voice.
export interface VoiceSample {
  recordings: number;
  seconds: number;
  speech: number;
  problem: string | null;
}

export const voiceSampleAudioUrl = "/api/voice-sample/audio";

// The server's explanation for a refused request, meant for the person using the app.
// A request the server refused, with its status: 400 when what was sent can't be used, as
// the message says; anything else is the server's own trouble.
export class ServerRefusal extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function refusal(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON; fall through to the generic message.
  }
  console.error(`Refused with ${response.status} and no reason`);
  return "That didn't work. Please try again.";
}

export function uploadUrl(kind: Kind, id: string): string {
  return `/api/uploads/${kind}/${id}`;
}

export async function listUploads(kind: Kind): Promise<Upload[]> {
  return json<Upload[]>(await fetch(`/api/uploads/${kind}`));
}

// Uploads one file. Throws an Error whose message says why when the server refuses it.
export async function uploadFile(kind: Kind, file: File): Promise<Upload> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/uploads/${kind}`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as Upload;
}

// Runs the checks on an upload again; returns it with the result. Throws a ServerRefusal, with
// status 503 when no check could run because the checks are off or failed.
export async function checkUpload(kind: Kind, id: string): Promise<Upload> {
  const response = await fetch(`${uploadUrl(kind, id)}/check`, { method: "POST" });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  return (await response.json()) as Upload;
}

// Renders the sample video again from what was prepared (roadmap R27b); returns its address.
// Throws a ServerRefusal saying why, such as nothing prepared yet.
export async function runVideoTestAgain(): Promise<string> {
  const response = await fetch("/api/prepare/clips/sample/again", { method: "POST" });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  return ((await response.json()) as { video: string }).video;
}

// Clears the whole conversation (roadmap R27b); returns how many turns were cleared.
export async function clearChat(): Promise<number> {
  const response = await fetch("/api/chat", { method: "DELETE" });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  return ((await response.json()) as { cleared: number }).cleared;
}

export interface Deleted {
  files: number;
  bytes: number;
  left: string[]; // files that could not be removed, such as one open in another program
}

// Deletes the photos, recordings, prepared face and voice, videos and conversation (roadmap R31).
// Throws a ServerRefusal saying why, such as setup still preparing.
export async function deleteMyData(): Promise<Deleted> {
  const response = await fetch("/api/data", { method: "DELETE" });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  return (await response.json()) as Deleted;
}

export async function getVoiceSample(): Promise<VoiceSample> {
  return json<VoiceSample>(await fetch("/api/voice-sample"));
}

export async function getPhotoChoice(): Promise<PhotoChoice> {
  return json<PhotoChoice>(await fetch("/api/uploads/photos/chosen"));
}

export async function choosePhoto(id: string): Promise<PhotoChoice> {
  const response = await fetch("/api/uploads/photos/chosen", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as PhotoChoice;
}

export async function removeUpload(kind: Kind, id: string): Promise<void> {
  const response = await fetch(uploadUrl(kind, id), { method: "DELETE" });
  if (!response.ok) throw new Error(await refusal(response));
}

// The accent the person's voice speaks with (roadmap R26). available is false when the person's
// own voice is not installed: a ready-made voice then speaks, in its own accent.
export type Accent = "own" | "american" | "british";

export interface AccentChoice {
  accent: Accent;
  available: boolean;
}

export async function getAccent(): Promise<AccentChoice> {
  return json<AccentChoice>(await fetch("/api/accent"));
}

// Saves the accent. When a sample was ready, the server starts making it again in this accent.
export async function chooseAccent(accent: Accent): Promise<AccentChoice> {
  const response = await fetch("/api/accent", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accent }),
  });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as AccentChoice;
}

// One step of the prepare job (roadmap R12), such as rendering the idle video.
export interface PrepareStep {
  key: string;
  label: string;
  done: number;
  total: number;
  seconds: number | null; // how long it took, once finished
  left_s: number | null; // while it runs: about how many seconds are left
}

// How far the prepare job has got. It runs on the server, and carries on after a restart.
export interface PrepareStatus {
  state: "idle" | "running" | "done" | "failed";
  photo_id: string | null;
  percent: number;
  steps: PrepareStep[] | null;
  error: string | null; // why it failed
  started_at: string | null;
  finished_at: string | null;
}

// A video the prepare job rendered (roadmap R13). The finish time is added so that the browser
// fetches it afresh after preparing again, which replaces it under the same address.
export function clipUrl(name: "sample" | "goodbye" | "welcome-back", status: PrepareStatus) {
  return `/api/prepare/clips/${name}?v=${encodeURIComponent(status.finished_at ?? "")}`;
}

export async function getPrepare(): Promise<PrepareStatus> {
  return json<PrepareStatus>(await fetch("/api/prepare"));
}

// Where the video of the person saying "Goodbye." or "Welcome back." is, which Prepare made with
// the sample (roadmap R29), or null when it hasn't been made. A default person (R24c) says them
// in their own voice.
export async function lineUrl(name: "goodbye" | "welcome-back"): Promise<string | null> {
  const start = await getStartNow();
  if (start.chosen) {
    const { gender, accent, realism, role } = start.chosen;
    const who = encodeURIComponent([gender, accent, realism, role].join("-"));
    return `/api/start-now/lines/${name}?v=${who}`;
  }
  const status = await getPrepare();
  return status.state === "done" ? clipUrl(name, status) : null;
}

// Start now with a default person (roadmap R24c): the four choices.
export type Gender = "female" | "male";
export type Realism = "photoreal" | "animated";
export interface PersonChoice {
  gender: Gender;
  accent: "American" | "British";
  realism: Realism;
  role: string;
  face?: number; // R24c2: which of the choice's faces, 1 when not given
}

// One default person, to show as one of their choice's faces (R24c2).
export interface Face {
  gender: Gender;
  realism: Realism;
  role: string;
  face: number;
  name: string;
}

export async function getFaces(): Promise<Face[]> {
  return json<Face[]>(await fetch("/api/start-now/faces"));
}

// The face's thumbnail, which ships with the app (R24b2 made them).
export function faceUrl(name: string): string {
  return `/faces/${name}.jpg`;
}

// Getting the chosen person ready: their download, then their Goodbye and Welcome back.
export interface StartNowStatus {
  state: "idle" | "downloading" | "unpacking" | "getting-ready" | "ready" | "failed";
  person: string | null;
  percent: number; // of the download
  error: string | null; // in plain words
  chosen?: PersonChoice | null; // the person the chat uses now, if a default one
  // Ready, and the chat would show this person: their idle video is made, or can't be.
  chat_ready?: boolean;
}

export async function getStartNow(): Promise<StartNowStatus> {
  return json<StartNowStatus>(await fetch("/api/start-now"));
}

// Starts getting the person ready, or reports on the one being got ready.
export async function startNow(choice: PersonChoice): Promise<StartNowStatus> {
  const response = await fetch("/api/start-now", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(choice),
  });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as StartNowStatus;
}

export const DEFAULT_PICTURE = "/api/start-now/picture";

// Starts the job, or reports on it while it runs. Throws an Error saying what is missing.
export async function startPrepare(): Promise<PrepareStatus> {
  const response = await fetch("/api/prepare", { method: "POST" });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as PrepareStatus;
}

// The user's review of the sample video (roadmap R14). Chat stays locked until it is accepted;
// a sample made again needs accepting again.
export interface Review {
  accepted: boolean;
  accepted_at: string | null;
  default_person?: boolean; // a ready-made avatar is in use (R24c)
}

export type Decision = "accept" | "reject-image" | "reject-voice" | "change-accent";

export async function getReview(): Promise<Review> {
  return json<Review>(await fetch("/api/review"));
}

// Accept the sample, or withdraw an acceptance. Throws an Error saying why when refused.
export async function review(decision: Decision): Promise<Review> {
  const response = await fetch("/api/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as Review;
}

// One turn of the chat with the LLM (roadmap R15): the user's prompt or the LLM's reply.
export interface Turn {
  role: "user" | "assistant";
  content: string;
}

// The conversation so far. The server keeps it until it stops.
export async function getChat(): Promise<Turn[]> {
  return (await json<{ turns: Turn[] }>(await fetch("/api/chat"))).turns;
}

// A reply, with its place in the conversation (from 0) as the server counted it.
export interface Reply extends Turn {
  turn: number;
  // Its clips are made sentence by sentence (roadmap R22); otherwise speakReply makes its whole
  // video. A streamed reply whose clips went away is not spoken again: a newer prompt, perhaps
  // from another tab, took them, and that one is the reply to hear.
  streamed: boolean;
  // The lesson after this prompt (roadmap R41h), null when there is none or it is over, and
  // choices to show as buttons, such as which topic to learn.
  lesson?: Lesson | null;
  choices?: Choice[];
  quiz?: Quiz | null; // the quiz after this prompt (R41i), null when there is none or it is over
  assessment?: Assessment | null; // the assessment after this prompt (R41j), the same way
  // A spoken prompt as it was answered, with any misheard names or terms put back (R24).
  prompt?: string;
}

// Where a lesson is (roadmap R41h): its topic, the part being taught (from 0; the part after
// the last is the topic's summary) and, from the server, how many parts the topic has. The
// browser keeps it, so a participant who stops picks up where they left off.
export interface Lesson {
  topic: string;
  part: number;
  active: boolean;
  parts?: number;
}

// Where a quiz is (roadmap R41i): its topic, the question being asked (from 1), the part of
// the topic it was written from, the questions asked so far, the answers right and partly right
// so far and the parts to go over again, and, from the server, how many questions a quiz has.
// The browser keeps it and sends it back with the next prompt, the answer.
export interface Quiz {
  topic: string;
  number: number;
  question: string;
  part: number;
  asked: string[];
  right: number;
  partly: number;
  review: string[];
  // What the question was written from (its material's fingerprint), so the answer is judged
  // from the same (review on PR #88).
  source: string;
  questions?: number;
}

// An answer in an assessment (roadmap R41j): its question's topic and level (0 recall, 1 explain,
// 2 apply), how it was judged and the correct answer, kept for the evaluation at the end.
export interface AssessmentAnswer {
  topic: string;
  level: number;
  question: string;
  verdict: string;
  correct: string;
}

// Where an assessment is (roadmap R41j): how many questions it has, the question being asked
// (from 1), its topic, level and part, the fingerprint of the part's material, the fingerprint of
// the topics in order, and the answers so far. The browser keeps it and sends it back with the
// next prompt, the answer.
export interface Assessment {
  total: number;
  number: number;
  topic: string;
  level: number;
  part: number;
  question: string;
  source: string;
  plan: string;
  answers: AssessmentAnswer[];
}

// A button offered with a reply, which sends `prompt` when clicked.
export interface Choice {
  label: string;
  prompt: string;
}

// Sends a prompt and returns the LLM's reply. Throws an Error saying why when it fails.
// `replyId` names the reply, so its clips can be asked for while the LLM writes (roadmap R22).
// `lesson`, `quiz` and `assessment` are the ones this browser has, if any (R41h, R41i, R41j).
export async function sendPrompt(
  prompt: string,
  replyId?: string,
  lesson?: Lesson | null,
  quiz?: Quiz | null,
  assessment?: Assessment | null,
  spoken?: boolean, // said with Hold to talk (R24)
): Promise<Reply> {
  const body: Record<string, unknown> = { prompt };
  if (spoken) body.spoken = true;
  if (replyId) body.reply_id = replyId;
  if (lesson) body.lesson = { topic: lesson.topic, part: lesson.part, active: lesson.active };
  if (quiz) {
    const { questions: _, ...kept } = quiz; // the server's own count, not sent back
    body.quiz = kept;
  }
  if (assessment) body.assessment = assessment;
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  return (await response.json()) as Reply;
}

// Speaks a reply in the person's voice on their photo (roadmap R17); turn is its place in the
// conversation. Returns the video's address, or null when the reply has nothing to say aloud.
// Throws an Error saying why when the voice or the video fails.
// `replyId`, the reply's id from sendPrompt, lets Stop stop the video being made (roadmap R19).
export async function speakReply(turn: number, replyId?: string): Promise<string | null> {
  const response = await fetch("/api/chat/video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(replyId ? { turn, reply_id: replyId } : { turn }),
  });
  if (!response.ok) throw new Error(await refusal(response));
  return ((await response.json()) as { video: string | null }).video;
}

// One sentence's clip (roadmap R22), with when its sentence arrived from the LLM and when the
// clip was ready, in seconds on the server's clock (the clock `Clips.now` reads), for the
// timing readout (roadmap R22a).
export interface Clip {
  url: string;
  sentence_at: number;
  ready_at: number;
}

// A reply's clips so far, one per sentence, in order (roadmap R22). done: no more will come;
// error: why a clip failed; now: the server's clock when it answered. null when the server has
// none for it: not yet, the reply wasn't streamed, or a newer prompt took them.
export interface Clips {
  clips: Clip[];
  done: boolean;
  error: string | null;
  now: number;
}

// With `known`, the clips this page has so far: the server answers as soon as there is more to
// tell (a new clip, a failure or the end), or after 10 seconds, so a clip is known the moment
// it is ready.
export async function getClips(replyId: string, known?: number): Promise<Clips | null> {
  const query = known === undefined ? "" : `?known=${known}&wait=10`;
  const response = await fetch(`/api/chat/clips/${replyId}${query}`);
  if (response.status === 404) return null;
  return json<Clips>(response);
}

// Stops a reply's clips (roadmap R19): the server makes no more and removes those it made. The
// reply's text still comes. True when there were clips to stop.
export async function stopReply(replyId: string): Promise<boolean> {
  const response = await fetch(`/api/chat/clips/${replyId}/stop`, { method: "POST" });
  return (await json<{ stopped: boolean }>(response)).stopped;
}

// The photo the chat's videos are made from, with its size as shown (roadmap R41d); url null
// when there is none, and width and height null when its size couldn't be read.
export interface ChatPhoto {
  url: string | null;
  width: number | null;
  height: number | null;
  // The idle video's address for this photo, so a new person's isn't the old one's from the
  // browser's cache (Larry's test of R32a); IDLE_VIDEO_URL when the server doesn't say.
  idle?: string | null;
}

export async function getChatPhoto(): Promise<ChatPhoto> {
  return json<ChatPhoto>(await fetch("/api/chat/photo"));
}

// What the chat shows under the prompt box (roadmap R41g): a line naming a few of the topics,
// null before any PDF is added, and a few example questions to send with a click.
export interface ChatHints {
  line: string | null;
  examples: string[];
}

export async function getChatHints(): Promise<ChatHints> {
  const hints = await json<Partial<ChatHints> | null>(await fetch("/api/chat/hints"));
  return {
    line: typeof hints?.line === "string" ? hints.line : null,
    examples: Array.isArray(hints?.examples) ? hints.examples : [],
  };
}

// The person at rest, blinking and moving slightly, played on a loop between replies (roadmap
// R23). The server answers once its warm-up has made it, and 404 when there is none.
export const IDLE_VIDEO_URL = "/api/chat/idle";

// A PDF on the Manage Content page (roadmap R34, R35). name is the name it was uploaded with,
// for display only; replacing it keeps the id.
export interface Pdf {
  id: string;
  name: string;
  size: number; // bytes
  added_at: string;
  replaced_at: string | null;
}

export function pdfUrl(id: string): string {
  return `/api/content/${id}`;
}

export async function listPdfs(): Promise<Pdf[]> {
  return json<Pdf[]>(await fetch("/api/content"));
}

// Adds a PDF, or with `id` replaces that one's file. Throws an Error saying why when refused.
export async function sendPdf(file: File, id?: string): Promise<Pdf> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(id ? pdfUrl(id) : "/api/content", {
    method: id ? "PUT" : "POST",
    body: form,
  });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as Pdf;
}

export async function removePdf(id: string): Promise<void> {
  const response = await fetch(pdfUrl(id), { method: "DELETE" });
  if (!response.ok) throw new Error(await refusal(response));
}

// How far the server has got reading a PDF's text, slides and tables (roadmap R36).
export interface Reading {
  state: "waiting" | "reading" | "done" | "failed";
  page: number; // pages read so far
  pages: number; // pages in all, once known
  kind: "text" | "slides" | "tables" | null; // once done
  counts: { paragraph: number; slide: number; table: number } | null; // once done
  pages_without_text: number[] | null; // once done: maybe scanned, so not read
  error: string | null;
}

// The reading progress of each PDF, by its id. A PDF not read yet may be missing.
export async function listReadings(): Promise<Record<string, Reading>> {
  return json<Record<string, Reading>>(await fetch("/api/content/readings"));
}

// How far the server has got building a PDF's wiki pages with the LLM (roadmap R37).
export interface WikiBuild {
  state: "waiting" | "building" | "done" | "failed";
  part: number; // parts done so far
  parts: number; // parts in all, once known
  pages: number | null; // once done: wiki pages built
  skipped_parts: number[] | null; // once done: parts the LLM gave no usable answer for
  error: string | null; // why it failed, or what it is waiting for
  stage: "topics" | "outline"; // while building: finding the topics, then building the outline
  steps: number; // outline requests made to the LLM so far
  steps_planned: number; // outline requests planned so far; more as long parts are found
  detail_pages: number | null; // once done: the outline's detail pages
  elapsed_s: number | null; // how long the build has taken so far, or took once done
  remaining_s: number | null; // about how long this stage has left, once a step is done
}

// One entry of a PDF's wiki outline (roadmap R37a): a section, topic or part, with its summary
// and the PDF pages it came from. A detail entry has its own page too.
export interface WikiEntry {
  id: string;
  title: string;
  summary: string;
  pages: number[];
  detail: boolean;
  entries: WikiEntry[];
  edited: boolean; // the user's own title and summary (roadmap R38)
  review: boolean; // edited, then the wiki was rebuilt: to be checked
  built?: { title: string; summary: string }; // while to be checked: what the rebuild says
}

// A PDF's table of contents, as the Wiki page shows it (roadmap R37b): every level of it.
export interface WikiContents {
  pdf_id: string;
  pdf_name: string;
  entries: WikiEntry[];
  // Edits whose entries a rebuild no longer has, until the user discards them.
  lost_edits: { id: string; title: string; summary: string }[];
}

// A detail page: its entry with its parts down to the next detail pages, whose own parts are on
// those pages, and the detail pages above it, from the top down.
export interface WikiDetail extends WikiEntry {
  pdf_id: string;
  pdf_name: string;
  trail: { id: string; title: string }[];
}

// Every PDF's table of contents, or one PDF's. A PDF whose wiki isn't built yet is missing.
export async function listWikiContents(pdf?: string): Promise<WikiContents[]> {
  const query = pdf ? `?pdf=${encodeURIComponent(pdf)}` : "";
  return json<WikiContents[]>(await fetch(`/api/wiki/contents${query}`));
}

// A detail page, or null when there is no such page (404). Throws when it can't be loaded.
export async function getWikiPage(id: string): Promise<WikiDetail | null> {
  const response = await fetch(`/api/wiki/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  return json<WikiDetail>(response);
}

// The user's edits (roadmap R38). Each throws an Error saying why when refused.
export async function saveWikiEdit(
  id: string,
  title: string,
  summary: string,
): Promise<WikiDetail> {
  const response = await fetch(`/api/wiki/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, summary }),
  });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as WikiDetail;
}

// Back to what the LLM built, or a lost edit discarded.
export async function undoWikiEdit(id: string): Promise<void> {
  const response = await fetch(`/api/wiki/${encodeURIComponent(id)}/edit`, { method: "DELETE" });
  if (!response.ok) throw new Error(await refusal(response));
}

// The user has checked an edit after a rebuild.
export async function markWikiReviewed(id: string): Promise<void> {
  const response = await fetch(`/api/wiki/${encodeURIComponent(id)}/reviewed`, { method: "POST" });
  if (!response.ok) throw new Error(await refusal(response));
}

// Builds a PDF's wiki again with the LLM, keeping the user's edits.
export async function rebuildWiki(pdf: string): Promise<WikiBuild> {
  const response = await fetch(`/api/content/${pdf}/wiki/rebuild`, { method: "POST" });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as WikiBuild;
}

// The wiki's history (roadmap R38a): every change keeps a version of the whole wiki.
export interface WikiChange {
  kind:
    | "start"
    | "built"
    | "rebuilt"
    | "edited"
    | "undone"
    | "kept"
    | "discarded"
    | "restored"
    | "loaded";
  title?: string; // the entry edited
  restored_at?: string; // when the restored version was kept
}

export interface WikiVersion {
  id: string;
  at: string;
  change: WikiChange;
}

// A version as the Wiki page shows it, to read.
export interface WikiVersionContents extends WikiContents, WikiVersion {}

// Thrown when the server asks first (412): the version or file was built from an earlier copy
// of the PDF. The message says so; the same call with `force` goes ahead.
export class AskFirst extends Error {}

async function refused(response: Response): Promise<never> {
  const message = await refusal(response);
  throw response.status === 412 ? new AskFirst(message) : new Error(message);
}

// A PDF's versions, newest first: the first is the wiki as it is now.
export async function listWikiVersions(pdf: string): Promise<WikiVersion[]> {
  const response = await fetch(`/api/content/${pdf}/wiki/history`);
  if (!response.ok) return refused(response);
  return (await response.json()) as WikiVersion[];
}

export async function getWikiVersion(pdf: string, id: string): Promise<WikiVersionContents> {
  const response = await fetch(`/api/content/${pdf}/wiki/history/${encodeURIComponent(id)}`);
  if (!response.ok) return refused(response);
  return (await response.json()) as WikiVersionContents;
}

// Makes a version the wiki again, as a new version, so it can be undone too.
export async function restoreWikiVersion(pdf: string, id: string, force = false): Promise<void> {
  const query = force ? "?force=true" : "";
  const response = await fetch(
    `/api/content/${pdf}/wiki/history/${encodeURIComponent(id)}/restore${query}`,
    { method: "POST" },
  );
  if (!response.ok) await refused(response);
}

// Downloads the wiki as it is now, with its whole history.
export function wikiFileUrl(pdf: string): string {
  return `/api/content/${pdf}/wiki/file`;
}

// Loads a file saved from wikiFileUrl: it becomes the wiki, and its history joins this one's.
// How many versions the history didn't have yet.
export async function loadWikiFile(pdf: string, file: File, force = false): Promise<number> {
  const body = new FormData();
  body.append("file", file);
  const query = force ? "?force=true" : "";
  const response = await fetch(`/api/content/${pdf}/wiki/file${query}`, { method: "POST", body });
  if (!response.ok) return refused(response);
  return ((await response.json()) as { versions_added: number }).versions_added;
}

// Where the Wiki page shows a PDF's table of contents, and a detail page (roadmap R37b).
export function wikiHref(pdf?: string): string {
  return pdf ? `#/wiki/${pdf}` : "#/wiki";
}

export function wikiPageHref(id: string): string {
  return `#/wiki/page/${id}`;
}

// A page of a PDF, opened in the browser's PDF viewer.
export function pdfPageUrl(id: string, page: number): string {
  return `${pdfUrl(id)}#page=${page}`;
}

// The wiki progress of each PDF, by its id. A PDF not read yet is missing.
export async function listWikiBuilds(): Promise<Record<string, WikiBuild>> {
  return json<Record<string, WikiBuild>>(await fetch("/api/wiki/builds"));
}

// The Settings menu's settings (roadmap R41a), saved on the server for every browser.
export type View = "host" | "participant";

export interface UiSettings {
  show_metrics: boolean; // the timing readout under the video and the other timings
  // Every page and option, or the chat and a read-only wiki with its PDFs (R41b).
  view: View;
  teach_me: boolean; // the Teach me button and lessons in the chat (R41h); off by default
  quiz_me: boolean; // the Quiz me button and quizzes in the chat (R41i); off by default
  assessment: boolean; // the Assessment button and assessments in the chat (R41j); off by default
  debug: boolean; // tools for looking into problems, such as Copy chat; off by default
  // Whether prompts the content doesn't cover are answered (R41); the config file's setting
  // until changed on the Settings page (R27).
  general_prompts: boolean;
}

export const DEFAULT_SETTINGS: UiSettings = {
  show_metrics: false,
  view: "host",
  teach_me: false,
  quiz_me: false,
  assessment: false,
  debug: false,
  general_prompts: false,
};

// Any value the server didn't send as one the setting can take is the default.
function settings(data: Partial<UiSettings>): UiSettings {
  return {
    show_metrics: data.show_metrics === true,
    view: data.view === "participant" ? "participant" : "host",
    teach_me: data.teach_me === true,
    quiz_me: data.quiz_me === true,
    assessment: data.assessment === true,
    debug: data.debug === true,
    general_prompts: data.general_prompts === true,
  };
}

export async function getSettings(): Promise<UiSettings> {
  return settings(await json<Partial<UiSettings>>(await fetch("/api/settings")));
}

export async function changeSettings(changes: Partial<UiSettings>): Promise<UiSettings> {
  const response = await fetch("/api/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
  return settings(await json<Partial<UiSettings>>(response));
}

// The LLM setting (roadmap R42): which LLM answers. The keys stay on the server: it only says
// which providers have one.
export interface LlmProvider {
  id: string;
  label: string;
  keys_at: string; // where to get a key; "" for the local model
  model: string; // entered on the Settings page; "" for the default
  default_model: string;
  has_key: boolean;
  lists_freely: boolean; // its models can be listed before a key is entered (OpenRouter)
  // Answers through the ChatGPT account signed in on the Settings page, with no key (R43a);
  // `has_key` is then whether one is signed in that allowed use of its plan.
  signs_in?: boolean;
}

export interface LlmSetting {
  provider: string;
  providers: LlmProvider[];
}

export async function getLlm(): Promise<LlmSetting> {
  return json<LlmSetting>(await fetch("/api/llm"));
}

// Makes `provider` the LLM. A key or model left out keeps the one saved; a blank model is the
// provider's default. Throws a ServerRefusal saying what is wrong.
export async function chooseLlm(choice: {
  provider: string;
  api_key?: string;
  model?: string;
}): Promise<LlmSetting> {
  const response = await fetch("/api/llm", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(choice),
  });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  return (await response.json()) as LlmSetting;
}

// The models a provider offers to the key given, or to the saved one (R42). Throws a
// ServerRefusal saying why when they can't be listed.
// The models a provider lists; the ChatGPT plan's come with the names it shows (`names`, by
// model, where they differ from the model's id).
export interface ModelList {
  ids: string[];
  names: Record<string, string>;
}

export async function listModels(provider: string, apiKey?: string): Promise<ModelList> {
  const response = await fetch("/api/llm/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(apiKey ? { provider, api_key: apiKey } : { provider }),
  });
  if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
  const listed = (await response.json()) as { models: string[]; names?: Record<string, string> };
  return { ids: listed.models, names: listed.names ?? {} };
}

// Said by the ChatGPT plan section when the account in use changes, so the LLM setting reads its
// models again for the new account (a review on PR #118).
export const CHATGPT_ACCOUNT_CHANGED = "chatgpt-account-changed";

// Sign in with ChatGPT (roadmap R43): the account connected, never its tokens, and whether it
// allowed this app to use the ChatGPT plan.
export interface ChatGptStatus {
  connected: boolean;
  email: string;
  name: string;
  plan_usage: boolean;
  registered_email: string; // the account signing in again uses; "" before the first sign-in
  label: string; // that account as shown: distinct even when two accounts share an email
  // The other accounts registered here; a connected one is switched to with no sign-in.
  accounts: { id: string; email: string; label: string; connected: boolean }[];
  revoked?: boolean; // after Disconnect: false when ChatGPT couldn't confirm it ended the sign-in
}

export async function getChatGpt(): Promise<ChatGptStatus> {
  return json<ChatGptStatus>(await fetch("/api/chatgpt"));
}

export async function useChatGptAccount(account: string): Promise<ChatGptStatus> {
  return json<ChatGptStatus>(
    await fetch("/api/chatgpt/use", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account }),
    }),
  );
}

export async function signOutChatGpt(): Promise<ChatGptStatus> {
  return json<ChatGptStatus>(await fetch("/api/chatgpt/sign-out", { method: "POST" }));
}
