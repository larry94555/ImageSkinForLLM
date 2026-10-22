// Leaving setup with a sample neither accepted nor rejected asks first (Larry's test of PR #131).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AvatarVoicePage } from "./avatar-voice";
import { LEAVE_CANCEL, LEAVE_PROCEED, LEAVE_TITLE } from "./leave-guard";
import { SetupPage } from "./pages";
import { useHash } from "./router";

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
      if (url === "/api/ready-voice") return Response.json({ voice: "af_heart", in_use: false, voices: [] });
      if (url === "/api/voice-sample") return Response.json({ recordings: 1, seconds: 30, speech: 30 });
      if (url === "/api/uploads/photos/chosen") return Response.json({ id: "p1", automatic: true });
      if (url.startsWith("/api/uploads/")) return Response.json([]);
      return new Response("", { status: 404 });
    }),
  );
}

// To `hash`, once its hashchange has landed, as in the app, where a page opens only after it.
async function go(hash: string) {
  if (window.location.hash === hash) return;
  const landed = new Promise<void>((resolve) => {
    const done = (e: HashChangeEvent) => {
      if (!e.newURL.endsWith(hash)) return;
      window.removeEventListener("hashchange", done);
      resolve();
    };
    window.addEventListener("hashchange", done);
  });
  window.location.hash = hash;
  await landed;
}

// The address the app's router routes by.
function Routed() {
  return <output aria-label="Routed">{useHash()}</output>;
}

// The page, with a top-bar link to the chat beside it.
async function page(which: "setup" | "avatar") {
  await go(which === "setup" ? "#/setup" : "#/avatar-voice");
  render(
    <>
      <Routed />
      <a href="#/chat">Chat</a>
      <a href="#/setup/photos">Change photos</a>
      {which === "setup" ? <SetupPage /> : <AvatarVoicePage />}
    </>,
  );
}

// Until the page knows its sample is waiting: the review it asks for can come after its buttons.
async function waiting() {
  await waitFor(() => {
    const leave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leave);
    expect(leave.defaultPrevented).toBe(true);
  });
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
  await page("avatar");
  await waiting();
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
  await page("avatar");
  await waiting();
  await click("Chat");
  await click(LEAVE_PROCEED, "button");
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(fetch).not.toHaveBeenCalledWith("/api/review", expect.objectContaining({ method: "POST" }));
});

// The browser's Back, with no link clicked (Codex's review of PR #131). Returns the address the
// app's router then routes by.
async function back() {
  // jsdom goes back a little later; its hashchange says when.
  const went = new Promise((resolve) => window.addEventListener("hashchange", resolve, { once: true }));
  await act(async () => {
    history.back();
    await went;
  });
  return screen.getByRole("status", { name: "Routed" }).textContent;
}

test("Back with the sample not accepted asks first; Cancel stays on the page", async () => {
  server({ avatar: true });
  await go("#/chat");
  await page("avatar");
  await waiting();
  const routed = await back();
  expect(await screen.findByRole("alertdialog", { name: LEAVE_TITLE })).toBeTruthy();
  expect(routed).toBe("#/avatar-voice"); // the app never routed away
  expect(window.location.hash).toBe("#/avatar-voice");
  await click(LEAVE_CANCEL, "button");
  expect(window.location.hash).toBe("#/avatar-voice");
  expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy();
  // Back still works, and asks again.
  expect(await back()).toBe("#/avatar-voice");
  expect(await screen.findByRole("alertdialog", { name: LEAVE_TITLE })).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith(
    "Leaving setup for #/chat with the sample neither accepted nor rejected",
  );
});

test("Back, then Proceed, goes where Back was going, asking once", async () => {
  server({ avatar: true });
  await go("#/chat");
  await page("avatar");
  await waiting();
  await back();
  await click(LEAVE_PROCEED, "button");
  await waitFor(() => expect(screen.getByRole("status", { name: "Routed" }).textContent).toBe("#/chat"));
  expect(window.location.hash).toBe("#/chat");
  await settled();
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("Back with nothing waiting doesn't ask", async () => {
  server({ accepted: true, avatar: true });
  await go("#/chat");
  await page("avatar");
  await screen.findByText(/You accepted this sample/);
  const routed = await back();
  expect(routed).toBe("#/chat");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("setup for your own photo asks too", async () => {
  server();
  await page("setup");
  await waiting();
  await click("Chat");
  expect(await screen.findByText(/The chat keeps the person and voice it has now/)).toBeTruthy();
});

test("a link within setup doesn't ask", async () => {
  server();
  await page("setup");
  await waiting();
  await click("Change photos");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("an accepted sample doesn't ask", async () => {
  server({ accepted: true, avatar: true });
  await page("avatar");
  await screen.findByText(/You accepted this sample/);
  await click("Chat");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("a rejected sample doesn't ask", async () => {
  server();
  await page("setup");
  await click("Reject voice", "button");
  await screen.findByText(/You rejected the voice/);
  await click("Chat");
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("closing the tab gets the browser's warning only while a sample is waiting", async () => {
  server();
  await page("setup");
  await screen.findByRole("button", { name: "Accept" });
  await waiting(); // the browser's warning is on
  await click("Accept", "button");
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  await settled();
  const done = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(done);
  expect(done.defaultPrevented).toBe(false);
});
