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

export async function getPrepare(): Promise<PrepareStatus> {
  return json<PrepareStatus>(await fetch("/api/prepare"));
}

// Starts the job, or reports on it while it runs. Throws an Error saying what is missing.
export async function startPrepare(): Promise<PrepareStatus> {
  const response = await fetch("/api/prepare", { method: "POST" });
  if (!response.ok) throw new Error(await refusal(response));
  return (await response.json()) as PrepareStatus;
}
