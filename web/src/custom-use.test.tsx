// Hiding a host's own photo and voice where the administrator turned them off (roadmap R240b).

import { act, cleanup, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { getCustomUse } from "./api";
import { App } from "./App";
import { ChangeSetup } from "./change-setup";
import { ALLOWED, CustomUseProvider, useCustomUseOf } from "./custom-use";
import { choices, HomePage, setupLink } from "./home";
import { ChatPage, SetupPage } from "./pages";
import { resolve } from "./router";
import { StartNowPage } from "./start-now";

const NONE = { image: false, voice: false };
const PHOTO_ONLY = { image: true, voice: false };

// A host's server with consent given; the review, and whatever else isn't listed, as asked.
function server(review: object = { accepted: true, accepted_at: null }) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({ view: "host" });
    if (url === "/api/review") return Response.json(review);
    if (url === "/api/start-now") {
      return Response.json({ state: "idle", person: null, percent: 0, error: null, chosen: null });
    }
    if (url === "/api/start-now/faces") return Response.json([]);
    if (url === "/api/prepare") return Response.json({ state: "idle", steps: null, percent: 0 });
    if (url === "/api/ready-voice") {
      return Response.json({
        voice: "bf_emma",
        in_use: true,
        voices: [{ voice: "bf_emma", label: "British woman 1" }],
      });
    }
    if (url === "/api/accent") return Response.json({ accent: "own", available: false });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: null, automatic: true });
    if (url.startsWith("/api/uploads/")) return Response.json([]);
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function within(use: typeof NONE, page: preact.ComponentChildren) {
  return render(<CustomUseProvider value={use}>{page}</CustomUseProvider>);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.mocked(getCustomUse).mockResolvedValue(ALLOWED);
  window.location.hash = "";
});

test("without their own photo, setup, the wizard and choosing their own go to Start now", () => {
  for (const hash of ["#/setup", "#/setup/photos", "#/setup/wizard", "#/consent/own"]) {
    expect(resolve(hash, true, false, false, NONE)).toEqual({ page: "start-now", redirect: "#/start-now" });
    expect(resolve(hash, true, false, false, { image: false, voice: true }).redirect).toBe("#/start-now");
  }
  expect(resolve("#/consent", false, false, false, NONE)).toEqual({ page: "consent" });
  expect(resolve("#/start-now", true, false, false, NONE)).toEqual({ page: "start-now" });
  // The participant view never had them, and goes to the chat as before.
  expect(resolve("#/setup", true, true, false, NONE)).toEqual({ page: "chat", redirect: "#/chat" });
});

test("without their own voice, the wizard opens Setup and the avatar's voice Start now", () => {
  expect(resolve("#/setup/wizard", true, false, false, PHOTO_ONLY)).toEqual({ page: "setup", redirect: "#/setup" });
  expect(resolve("#/setup/wizard", false, false, false, PHOTO_ONLY)).toEqual({ page: "consent", redirect: "#/consent" });
  expect(resolve("#/avatar-voice", true, false, false, PHOTO_ONLY).redirect).toBe("#/start-now");
  expect(resolve("#/setup", true, false, false, PHOTO_ONLY)).toEqual({ page: "setup" });
  expect(resolve("#/avatar-voice", true, false, false, ALLOWED)).toEqual({ page: "avatar-voice" });
});

test("without their own photo, home offers only the ready-made avatars", async () => {
  expect(choices(false, true, false, false).map((c) => c.title)).toEqual(["Start now"]);
  expect(choices(true, true, false, false)[2]).toEqual({
    href: "#/start-now",
    title: "Setup",
    text: "Choose another ready-made avatar.",
  });
  expect(setupLink(true, false, false)).toBe("#/start-now");
  expect(setupLink(false, false, false)).toBe("#/start-now");

  server({ accepted: false, accepted_at: null });
  within(NONE, <HomePage consented />);
  expect(await screen.findByText("Welcome")).toBeTruthy();
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    expect.stringContaining("Start now"),
  ]);
  expect(screen.queryByRole("link", { name: "Set up with your own photo and voice" })).toBeNull();
});

test("the wizard link needs both their own photo and voice", async () => {
  server({ accepted: false, accepted_at: null });
  within(PHOTO_ONLY, <HomePage consented />);
  expect(await screen.findByText("Welcome")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Start setup/ })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Set up with your own photo and voice" })).toBeNull();
});

test("Start now has no way to their own photo and voice where it is off", async () => {
  server();
  within(NONE, <StartNowPage />);
  await screen.findByRole("heading", { name: /a ready-made avatar/ });
  expect(screen.queryByRole("link", { name: /use your own/i })).toBeNull();
  expect(screen.queryByText(/switch to your own photo and voice/)).toBeNull();
  cleanup();
  within(ALLOWED, <StartNowPage />);
  expect(screen.getAllByRole("link", { name: /use your own/i })).toHaveLength(2);
});

test("Setup without their own voice: photos and Prepare only, as two steps", async () => {
  server();
  within(PHOTO_ONLY, <SetupPage />);
  expect(await screen.findByRole("heading", { name: "Photos" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Voice recordings" })).toBeNull();
  expect(screen.queryByText(/accent/i, { selector: "h2" })).toBeNull();
  expect(screen.queryByRole("link", { name: /one step at a time/ })).toBeNull();
  expect(screen.getByText(/Using your own voice is turned off for this site/)).toBeTruthy();
  expect(screen.getAllByText(/^Step \d of \d$/).map((p) => p.textContent)).toEqual([
    "Step 1 of 2",
    "Step 2 of 2",
  ]);
  expect(await screen.findByRole("heading", { name: "The voice" })).toBeTruthy();
  expect(screen.queryByText(/In use now: no recording/)).toBeNull();
});

test("Settings' Avatar Choice offers only what the host may use", async () => {
  server({ accepted: true, accepted_at: null, default_person: true, own_voice: false });
  within(NONE, <ChangeSetup />);
  expect(await screen.findByRole("link", { name: "Choose another avatar" })).toBeTruthy();
  expect(screen.getByText(/Using your own photo is turned off for this site/)).toBeTruthy();
  expect(screen.queryByRole("heading", { name: /Your own photo and voice/ })).toBeNull();
  expect(screen.queryByRole("link", { name: "Use my own voice" })).toBeNull();
  cleanup();

  server({ accepted: true, accepted_at: null, default_person: false });
  within(PHOTO_ONLY, <ChangeSetup />);
  await screen.findByText("The chat is open with the sample you accepted.");
  expect(screen.getByRole("link", { name: "Change photos" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Change recordings" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Change accent" })).toBeNull();
});

test("the chat goes to Start now when the server says it needs a default person", async () => {
  server({ accepted: false, accepted_at: null, own_turned_off: true });
  render(<ChatPage />);
  await waitFor(() => expect(window.location.hash).toBe("#/start-now"));
  expect(console.info).toHaveBeenCalledWith("The chat needs a ready-made avatar: going to Start now");
});

test("the chat's Avatar Choice leaves out their own photo where it is off", async () => {
  server({ accepted: true, accepted_at: null, default_person: true });
  within(NONE, <ChatPage />);
  expect(await screen.findByRole("link", { name: "Choose another avatar" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Use your own photo and voice" })).toBeNull();
});

// What the host may use is asked again on each page, so an Admin settings change shows on the
// next page, with no sign-out.
function Probe({ hash, signedIn }: { hash: string; signedIn: boolean | undefined }) {
  const { use, fresh } = useCustomUseOf(hash, signedIn);
  if (use === null) return <p>unknown</p>;
  return <p>{`image ${use.image}, voice ${use.voice}${fresh ? "" : " (from the last page)"}`}</p>;
}

test("it is read again on each page change while signed in", async () => {
  vi.mocked(getCustomUse).mockResolvedValue(NONE);
  const { rerender } = render(<Probe hash="#/" signedIn={undefined} />);
  expect(screen.getByText("unknown")).toBeTruthy();
  rerender(<Probe hash="#/" signedIn />);
  expect(await screen.findByText("image false, voice false")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Own photo allowed: false, own voice allowed: false");

  vi.mocked(getCustomUse).mockResolvedValue(PHOTO_ONLY);
  rerender(<Probe hash="#/setup" signedIn />);
  expect(screen.getByText("image false, voice false (from the last page)")).toBeTruthy();
  expect(await screen.findByText("image true, voice false")).toBeTruthy();
  expect(getCustomUse).toHaveBeenCalledTimes(2);
});

test("signed out, or when it can't be read, nothing is hidden", async () => {
  const { rerender } = render(<Probe hash="#/" signedIn={false} />);
  expect(await screen.findByText("image true, voice true")).toBeTruthy();
  expect(getCustomUse).not.toHaveBeenCalled();

  vi.mocked(getCustomUse).mockRejectedValue(new Error("503 Service Unavailable"));
  rerender(<Probe hash="#/chat" signedIn />);
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith(
      "Could not read whether your own photo and voice may be used",
      expect.any(Error),
    ),
  );
  expect(screen.getByText("image true, voice true")).toBeTruthy();
});

test("in the app, a host without their own photo is taken from Setup to Start now", async () => {
  vi.mocked(getCustomUse).mockResolvedValue(NONE);
  server();
  window.location.hash = "#/setup";
  render(<App />);
  await waitFor(() => expect(window.location.hash).toBe("#/start-now"));
  await act(async () => {
    window.dispatchEvent(new HashChangeEvent("hashchange")); // as the browser does after replace()
  });
  expect(await screen.findByRole("heading", { name: /a ready-made avatar/ })).toBeTruthy();
  await act(async () => {
    window.dispatchEvent(new HashChangeEvent("hashchange")); // as the browser does after replace()
  });
  expect(await screen.findByRole("heading", { name: /a ready-made avatar/ })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Setup" }).getAttribute("href")).toBe("#/start-now");

  // The administrator allows it: the next page shows Setup again.
  vi.mocked(getCustomUse).mockResolvedValue(ALLOWED);
  await act(async () => {
    window.location.hash = "#/setup";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(await screen.findByRole("heading", { name: "Setup", level: 1 })).toBeTruthy();
  expect(window.location.hash).toBe("#/setup");
});
