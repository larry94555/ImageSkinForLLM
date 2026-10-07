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
}

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

export async function removeUpload(kind: Kind, id: string): Promise<void> {
  const response = await fetch(uploadUrl(kind, id), { method: "DELETE" });
  if (!response.ok) throw new Error(await refusal(response));
}
