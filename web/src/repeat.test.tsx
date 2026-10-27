// Repeat: the latest reply said again, with no LLM call (roadmap R156).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Turn } from "./api";
import { App } from "./App";

const TURNS: Turn[] = [
  { role: "user", content: "Why does rain fall?" },
  { role: "assistant", content: "It falls from clouds." },
];

// A fake server with the sample accepted, the conversation `turns`, and POST /api/chat/repeat
// answering with `repeated`; the repeat's clips are one clip, all made.
function server(turns: Turn[], repeated: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/review") return Response.json({ accepted: true, accepted_at: null });
    if (url === "/api/chat") {
      if (init?.method === "POST") throw new Error("Repeat must not ask the LLM");
      return Response.json({ turns });
    }
    if (url === "/api/chat/repeat") return repeated();
    if (url.endsWith("/stop")) return Response.json({ stopped: true });
    if (url.startsWith("/api/chat/clips/")) {
      const clip = { url: "/api/chat/clips/r/1", sentence_at: 995, ready_at: 995.3 };
      return Response.json({ clips: [clip], done: true, error: null, now: 1000 });
    }
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function shownVideo(): HTMLVideoElement | null {
  return document.querySelector("video.reply-video");
}

async function openChat(text: string) {
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText(text);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("Repeat says the latest reply again from its clips, without asking the LLM", async () => {
  const fetchMock = server(TURNS, () => Response.json({ turn: 1, streamed: true }));
  await openChat("It falls from clouds.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Repeat" }));
  });
  const asked = fetchMock.mock.calls.find(([url]) => url === "/api/chat/repeat");
  expect(asked?.[1]?.body).toMatch(/^\{"reply_id":"[0-9a-f]{32}"\}$/);
  const replyId = JSON.parse(String(asked?.[1]?.body)).reply_id;
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe("/api/chat/clips/r/1"));
  expect(fetchMock).toHaveBeenCalledWith(`/api/chat/clips/${replyId}?known=0&wait=10`);
  expect(console.info).toHaveBeenCalledWith("Repeating the latest reply");
  // The conversation is as it was: no prompt and no second reply.
  expect(screen.getAllByText("It falls from clouds.").length).toBe(1);
});

test("Repeat shows only once there is a reply, and waits while one is said", async () => {
  server([TURNS[0]], () => Response.json({ turn: 1, streamed: true }));
  await openChat("Why does rain fall?");
  expect(screen.queryByRole("button", { name: "Repeat" })).toBeNull();
  cleanup();
  let answer: (r: Response) => void = () => {};
  server(TURNS, () => new Promise<Response>((resolve) => (answer = resolve)));
  await openChat("It falls from clouds.");
  const repeat = screen.getByRole("button", { name: "Repeat" }) as HTMLButtonElement;
  fireEvent.click(repeat);
  await waitFor(() => expect(repeat.disabled).toBe(true));
  await act(async () => answer(Response.json({ turn: 1, streamed: true })));
  await waitFor(() => expect(repeat.disabled).toBe(false));
});

test("a repeat that fails says the reply couldn't be said aloud", async () => {
  server(TURNS, () => Response.json({ detail: "The reply couldn't be repeated." }, { status: 500 }));
  await openChat("It falls from clouds.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Repeat" }));
  });
  expect(await screen.findByText(/couldn't say this one aloud/)).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not repeat the reply", expect.anything());
});

test("Stop before the server begins a repeat ends it quietly", async () => {
  let answer: (r: Response) => void = () => {};
  const fetchMock = server(TURNS, () => new Promise<Response>((resolve) => (answer = resolve)));
  await openChat("It falls from clouds.");
  fireEvent.click(screen.getByRole("button", { name: "Repeat" }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith("/api/chat/repeat", expect.anything()),
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  });
  expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/stop$/), expect.anything());
  await act(async () => answer(Response.json({ detail: "Stopped." }, { status: 409 })));
  const repeat = screen.getByRole("button", { name: "Repeat" }) as HTMLButtonElement;
  await waitFor(() => expect(repeat.disabled).toBe(false));
  expect(screen.queryByText(/couldn't say this one aloud/)).toBeNull();
  expect(console.error).not.toHaveBeenCalledWith("Could not repeat the reply", expect.anything());
});
