// Exit and Start again (roadmap R29).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { PrepareStatus, Turn } from "./api";
import { App } from "./App";
import { LINE_TIMEOUT_MS } from "./pages";

const PREPARED: PrepareStatus = {
  state: "done",
  photo_id: "p1",
  percent: 100,
  steps: null,
  error: null,
  started_at: "2026-10-18T09:00:00+00:00",
  finished_at: "2026-10-18T09:20:00+00:00",
};
const AT = encodeURIComponent(PREPARED.finished_at!);
const GOODBYE = `/api/prepare/clips/goodbye?v=${AT}`;
const WELCOME_BACK = `/api/prepare/clips/welcome-back?v=${AT}`;

const TURNS: Turn[] = [
  { role: "user", content: "My name is Larry." },
  { role: "assistant", content: "Nice to meet you, Larry!" },
];

// A fake server with the sample accepted, the conversation `TURNS`, the prepare job's status
// `prepared`, and a reply that is spoken in clips the test sends when it chooses.
function server(prepared: PrepareStatus | Response = PREPARED) {
  let answer: (r: Response) => void = () => {};
  const recorded: Turn[] = []; // what the server added to the conversation since
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/review") return Response.json({ accepted: true, accepted_at: null });
    if (url === "/api/prepare") {
      return prepared instanceof Response ? prepared : Response.json(prepared);
    }
    if (url === "/api/chat") {
      if (init?.method !== "POST") return Response.json({ turns: [...TURNS, ...recorded] });
      return new Promise<Response>((resolve) => (answer = resolve));
    }
    if (url.endsWith("/stop")) return Response.json({ stopped: true });
    if (url.startsWith("/api/chat/clips/")) {
      const clip = { url: "/api/chat/clips/x/1", sentence_at: 995, ready_at: 995.3 };
      return Response.json({ clips: [clip], done: false, error: null, now: 1000 });
    }
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, answer: (r: Response) => answer(r), recorded };
}

function shownVideo(): HTMLVideoElement {
  return document.querySelector("video.reply-video") as HTMLVideoElement;
}

function button(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

async function openChat() {
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("Nice to meet you, Larry!");
}

let info: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  info = vi.spyOn(console, "info").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("Exit says Goodbye, then Start again says Welcome back with the conversation kept", async () => {
  vi.stubGlobal("webkitSpeechRecognition", class {}); // so Hold to talk is shown (R24)
  server();
  await openChat();
  expect(document.querySelector(".sound-controls button:last-child")).toBe(button("Exit"));
  fireEvent.click(button("Exit"));
  // The person says "Goodbye.", and nothing can be sent or exited meanwhile.
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(GOODBYE));
  expect(button("Exit").disabled).toBe(true);
  fireEvent.input(screen.getByRole("textbox", { name: "Your message" }), {
    target: { value: "Hello" },
  });
  expect(button("Send").disabled).toBe(true);
  fireEvent.playing(shownVideo());
  fireEvent.ended(shownVideo());
  expect(await screen.findByRole("heading", { name: "Goodbye" })).toBeTruthy();
  expect(screen.queryByText("Nice to meet you, Larry!")).toBeNull();
  expect(info).toHaveBeenCalledWith("Exit");
  expect(info).toHaveBeenCalledWith(expect.stringMatching(/^Said Goodbye \(\d+ ms\)$/));
  expect(info).toHaveBeenCalledWith("Exit screen shown");

  fireEvent.click(button("Start again"));
  // Back in the chat with the conversation, while the person says "Welcome back."
  expect(await screen.findByText("Nice to meet you, Larry!")).toBeTruthy();
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(WELCOME_BACK));
  fireEvent.input(screen.getByRole("textbox", { name: "Your message" }), {
    target: { value: "Hello" },
  });
  expect(button("Send").disabled).toBe(true);
  expect(screen.getByRole("button", { name: "Hold to talk" })).toHaveProperty("disabled", true);
  fireEvent.ended(shownVideo());
  // Then the prompt and the microphone are ready.
  await waitFor(() => expect(button("Send").disabled).toBe(false));
  expect(screen.getByRole("button", { name: "Hold to talk" })).toHaveProperty("disabled", false);
  expect(button("Exit").disabled).toBe(false);
  expect(shownVideo()).toBeNull(); // back to the idle video
  expect(info).toHaveBeenCalledWith("Start again");
  expect(info).toHaveBeenCalledWith(expect.stringMatching(/^Said Welcome back \(\d+ ms\)$/));
});

test("Exit stops a reply being spoken before saying Goodbye", async () => {
  const { fetchMock, answer } = server();
  await openChat();
  fireEvent.input(screen.getByRole("textbox", { name: "Your message" }), {
    target: { value: "Tell me a story" },
  });
  fireEvent.click(button("Send"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe("/api/chat/clips/x/1"));
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  fireEvent.click(button("Exit"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(GOODBYE));
  expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/stop"))).toHaveLength(1);
  expect(shownVideo().autoplay).toBe(true); // Goodbye plays, though the reply was stopped
  await act(async () => {
    answer(Response.json({ role: "assistant", content: "Once upon a time.", streamed: true }));
  });
  fireEvent.ended(shownVideo());
  expect(await screen.findByRole("heading", { name: "Goodbye" })).toBeTruthy();
});

test("without a Goodbye video, Exit goes straight to the exit screen", async () => {
  server({ ...PREPARED, state: "idle", finished_at: null });
  await openChat();
  fireEvent.click(button("Exit"));
  expect(await screen.findByRole("heading", { name: "Goodbye" })).toBeTruthy();
  expect(console.warn).toHaveBeenCalledWith("No Goodbye video, so it isn't said");
});

test("when the prepare job can't be asked, Exit still reaches the exit screen", async () => {
  server(new Response("", { status: 500 }));
  await openChat();
  fireEvent.click(button("Exit"));
  expect(await screen.findByRole("heading", { name: "Goodbye" })).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not find the Goodbye video",
    expect.any(Error),
  );
});

test("a Goodbye video that can't be played is passed over", async () => {
  server();
  await openChat();
  fireEvent.click(button("Exit"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(GOODBYE));
  fireEvent.error(shownVideo());
  expect(await screen.findByRole("heading", { name: "Goodbye" })).toBeTruthy();
});

test("a Welcome back that never ends frees the chat after a while", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  server();
  await openChat();
  fireEvent.click(button("Exit"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(GOODBYE));
  fireEvent.ended(shownVideo());
  fireEvent.click(await screen.findByRole("button", { name: "Start again" }));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(WELCOME_BACK));
  fireEvent.input(screen.getByRole("textbox", { name: "Your message" }), {
    target: { value: "Hello" },
  });
  expect(button("Send").disabled).toBe(true);
  await act(async () => {
    vi.advanceTimersByTime(LINE_TIMEOUT_MS);
  });
  expect(button("Send").disabled).toBe(false);
  expect(console.warn).toHaveBeenCalledWith(
    "Welcome back didn't finish playing in time, so the chat went on",
  );
});

test("Start again waits for a prompt asked before Exit, then shows it (review on PR #106)", async () => {
  const { answer, recorded } = server();
  await openChat();
  fireEvent.input(screen.getByRole("textbox", { name: "Your message" }), {
    target: { value: "Tell me a story" },
  });
  fireEvent.click(button("Send"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe("/api/chat/clips/x/1"));
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  fireEvent.click(button("Exit"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(GOODBYE));
  fireEvent.ended(shownVideo());
  fireEvent.click(await screen.findByRole("button", { name: "Start again" }));
  // The prompt is still being answered: the conversation isn't read until it is.
  await waitFor(() => expect(info).toHaveBeenCalledWith("Waiting for the prompt asked before Exit"));
  expect(screen.queryByText("Nice to meet you, Larry!")).toBeNull();
  // The server records the exchange as it answers, then the answer comes.
  recorded.push(
    { role: "user", content: "Tell me a story" },
    { role: "assistant", content: "Once upon a time." },
  );
  await act(async () => {
    answer(Response.json({ role: "assistant", content: "Once upon a time.", streamed: true }));
  });
  // The latest exchange is the one asked before Exit.
  expect(await screen.findByText("Once upon a time.")).toBeTruthy();
  expect(screen.getByText("Tell me a story")).toBeTruthy();
});

test("Start again still opens the chat when the prompt asked before Exit fails", async () => {
  const { answer } = server();
  await openChat();
  fireEvent.input(screen.getByRole("textbox", { name: "Your message" }), {
    target: { value: "Tell me a story" },
  });
  fireEvent.click(button("Send"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe("/api/chat/clips/x/1"));
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  fireEvent.click(button("Exit"));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe(GOODBYE));
  fireEvent.ended(shownVideo());
  fireEvent.click(await screen.findByRole("button", { name: "Start again" }));
  await act(async () => {
    answer(new Response("", { status: 502 }));
  });
  expect(await screen.findByText("Nice to meet you, Larry!")).toBeTruthy();
});
