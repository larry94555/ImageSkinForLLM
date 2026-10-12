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
async function refusal(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON; fall through to the generic message.
  }
  return `The server refused it (${response.status}).`;
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

// Runs the checks on an upload stored before they were on; returns it with the result.
export async function checkUpload(kind: Kind, id: string): Promise<Upload> {
  const response = await fetch(`${uploadUrl(kind, id)}/check`, { method: "POST" });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as Upload;
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
}

// Sends a prompt and returns the LLM's reply. Throws an Error saying why when it fails.
// `replyId` names the reply, so its clips can be asked for while the LLM writes (roadmap R22).
export async function sendPrompt(prompt: string, replyId?: string): Promise<Reply> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(replyId ? { prompt, reply_id: replyId } : { prompt }),
  });
  if (!response.ok) throw new Error(await refusal(response));
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
