// Leaving setup with a sample neither accepted nor rejected asks first (Larry's test of PR #131).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AvatarVoicePage } from "./avatar-voice";
import { LEAVE_CANCEL, LEAVE_PROCEED, LEAVE_TITLE } from "./leave-guard";
import { SetupPage } from "./pages";

const DONE = {
  state: "done",
  photo_id: "p1",
  percent: 100,
  steps: [],
  error: null,
  started_at: "2026-10-21T08:00:00+00:00",
  finished_at: "2026-10-21T08:20:00+00:00",
};

// `accepted` says whether the sample ready now is accepted; `avatar` puts a ready-made avatar
// in use, to speak in the user's voice.
function server({ accepted = false, avatar = false } = {}) {
  const state = { accepted };
  const review = () =>
    avatar
      ? {
          accepted: true,
          accepted_at: null,
          default_person: true,
          own_sample_accepted: false,
          own_voice: true,
          voice_accepted: state.accepted,
        }
      : { accepted: state.accepted, accepted_at: null };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/review" && init?.method === "POST") {
        const { decision } = JSON.parse(String(init.body)) as { decision: string };
        state.accepted = decision === "accept";
        return Response.json(review());
      }
      if (url === "/api/review") return Response.json(review());
      if (url === "/api/prepare") return Response.json(DONE);
      if (url === "/api/accent") return Response.json({ accent: "own", available: true });
      if (url === "/api/ready-voice") return Response.json({ voice: "af_heart", in_use: false });
      if (url === "/api/voice-sample") return Response.json({ recordings: 1, seconds: 30, speech: 30 });
      if (url === "/api/uploads/photos/chosen") return Response.json({ id: "p1", automatic: true });
      if (url.startsWith("/api/uploads/")) return Response.json([]);
      return new Response("", { status: 404 });
    }),
  );
}

// The page, with a top-bar link to the chat beside it.
function page(which: "setup" | "avatar") {
  window.location.hash = which === "setup" ? "#/setup" : "#/avatar-voice";
  render(
    <>
      <a href="#/chat">Chat</a>
      <a href="#/setup/photos">Change photos</a>
      {which === "setup" ? <SetupPage /> : <AvatarVoicePage />}
    </>,
  );
}

// Until every request the page made has been answered.
async function settled() {
  for (let i = 0; i < 5; i++) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

async function click(name: string, role: "link" | "button" = "link") {
  const target = await screen.findByRole(role, { name });
  await act(async () => {
    fireEvent.click(target);
  });
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

test("leaving with the avatar's sample not accepted asks first; Cancel stays", async () => {
  server({ avatar: true });
  page("avatar");
  await screen.findByRole("button", { name: "Accept" });
  await settled();
  await click("Chat");
  expect(await screen.findByRole("alertdialog", { name: LEAVE_TITLE })).toBeTruthy();
  expect(screen.getByText(/The avatar keeps the voice it has now/)).toBeTruthy();
  expect(window.location.hash).toBe("#/avatar-voice");
  await click(LEAVE_CANCEL, "button");
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(window.location.hash).toBe("#/avatar-voice");
  expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy(); // still to choose
  expect(console.info).toHaveBeenCalledWith(
    "Leaving setup for #/chat with the sample neither accepted nor rejected",
  );
});

test("Proceed leaves with nothing changed", async () => {
  server({ avatar: true });
  page("avatar");
  await screen.findByRole("button", { name: "Accept" });
  await settled();
  await click("Chat");
  await click(LEAVE_PROCEED, "button");
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(fetch).not.toHaveBeenCalledWith("/api/review", expect.objectContaining({ method: "POST" }));
});

test("setup for your own photo asks too", async () => {
  server();
  page("setup");
  await screen.findByRole("button", { name: "Accept" });
  await settled();
  await click("Chat");
  expect(await screen.findByText(/The chat keeps the person and voice it has now/)).toBeTruthy();
});

test("a link within setup doesn't ask", async () => {
  server();
  page("setup");
  await screen.findByRole("button", { name: "Accept" });
  await settled();
  await click("Change photos");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("an accepted sample doesn't ask", async () => {
  server({ accepted: true, avatar: true });
  page("avatar");
  await screen.findByText(/You accepted this sample/);
  await click("Chat");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("a rejected sample doesn't ask", async () => {
  server();
  page("setup");
  await click("Reject voice", "button");
  await screen.findByText(/You rejected the voice/);
  await click("Chat");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("closing the tab gets the browser's warning only while a sample is waiting", async () => {
  server();
  page("setup");
  await screen.findByRole("button", { name: "Accept" });
  await settled();
  const waiting = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(waiting);
  expect(waiting.defaultPrevented).toBe(true);
  await click("Accept", "button");
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  await settled();
  const done = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(done);
  expect(done.defaultPrevented).toBe(false);
});
