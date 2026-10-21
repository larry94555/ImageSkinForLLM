// Use my own photo with a ready-made avatar's voice (roadmap R24d, feature item 59).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { lineUrl } from "./api";
import { ChangeSetup } from "./change-setup";
import { ConsentPage, SetupPage } from "./pages";

const DONE = {
  state: "done",
  photo_id: "p1",
  percent: 100,
  steps: [],
  error: null,
  started_at: "2026-10-21T08:00:00+00:00",
  finished_at: "2026-10-21T08:20:00+00:00",
};
const CHOSEN = { gender: "female", accent: "British", realism: "animated", role: "Professor", face: 1 };

interface Server {
  ownPhoto?: boolean; // Use my own photo was chosen
  sampleAccepted?: boolean; // its sample is accepted, so the photo is in use
  consent?: { agreed: boolean; photo_only?: boolean };
  putOk?: boolean;
}

// A server with a ready-made avatar chosen; the calls made are kept in `calls`.
function server(opts: Server = {}) {
  const state = { ownPhoto: opts.ownPhoto ?? false };
  const calls: { url: string; body: unknown }[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ url, body });
    if (url === "/api/consent") {
      if (init?.method === "POST") return Response.json({ agreed: true, ...body });
      return Response.json(opts.consent ?? { agreed: true, agreed_at: null });
    }
    if (url === "/api/start-now/own-photo") {
      if (opts.putOk === false) return Response.json({ detail: "No ready-made avatar is chosen." }, { status: 409 });
      state.ownPhoto = body.own;
      return Response.json({ state: "ready", chosen: CHOSEN, own_photo: body.own });
    }
    if (url === "/api/start-now") {
      const inUse = state.ownPhoto && opts.sampleAccepted === true;
      return Response.json({ state: "ready", chosen: CHOSEN, own_photo: state.ownPhoto, own_photo_in_use: inUse });
    }
    if (url === "/api/review") {
      if (init?.method === "POST") {
        return Response.json({ accepted: true, default_person: true, own_photo: true, sample_accepted: true });
      }
      return Response.json({
        accepted: true,
        accepted_at: null,
        default_person: true,
        ...(state.ownPhoto ? { own_photo: true, sample_accepted: opts.sampleAccepted === true } : {}),
      });
    }
    if (url === "/api/prepare") return Response.json(DONE);
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: "p1", automatic: true });
    if (url === "/api/uploads/photos") return Response.json([]);
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, state };
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

test("Use my own photo keeps the avatar's voice and opens setup at the photos", async () => {
  const { calls } = server();
  render(<ChangeSetup />);
  const button = await screen.findByRole("button", { name: "Use my own photo" });
  expect(screen.getByText("Keep this voice and replace the picture with your own photo.")).toBeTruthy();
  await act(async () => {
    fireEvent.click(button);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/setup/photos"));
  expect(calls).toContainEqual({ url: "/api/start-now/own-photo", body: { own: true } });
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Using your own photo with the avatar's voice, from Settings \(\d+ ms\)$/),
  );
});

test("Use my own photo asks for consent first when none was given", async () => {
  server({ consent: { agreed: false } });
  render(<ChangeSetup />);
  const button = await screen.findByRole("button", { name: "Use my own photo" });
  await act(async () => {
    fireEvent.click(button);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/consent"));
});

test("a refused Use my own photo says why", async () => {
  server({ putOk: false });
  render(<ChangeSetup />);
  const button = await screen.findByRole("button", { name: "Use my own photo" });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(await screen.findByText("No ready-made avatar is chosen.")).toBeTruthy();
  expect(window.location.hash).toBe("");
});

test("until its sample is accepted, Settings says the photo is waiting", async () => {
  server({ ownPhoto: true });
  render(<ChangeSetup />);
  expect(await screen.findByText(/Your photo's sample video isn't accepted yet/)).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/avatar in use: ready-made \(\d+ ms\)$/),
  );
});

test("with your own photo in use, Settings changes it or goes back to the avatar's picture", async () => {
  const { calls } = server({ ownPhoto: true, sampleAccepted: true });
  render(<ChangeSetup />);
  expect(await screen.findByText("Your own photo, speaking in the ready-made avatar's voice.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Change your photo" }).getAttribute("href")).toBe("#/setup/photos");
  expect(screen.queryByRole("button", { name: "Use my own photo" })).toBeNull();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Use the avatar's picture again" }));
  });
  expect(calls).toContainEqual({ url: "/api/start-now/own-photo", body: { own: false } });
  await waitFor(() =>
    expect(console.info).toHaveBeenCalledWith("Using the avatar's picture again from Settings"),
  );
  // Read again: the avatar's own picture is in use.
  expect(await screen.findByRole("button", { name: "Use my own photo" })).toBeTruthy();
});

test("from Use my own photo, your own photo and voice leaves the photo-only setup", async () => {
  const { calls } = server({ ownPhoto: true });
  render(<ChangeSetup />);
  const link = await screen.findByRole("link", { name: "Use your own photo and voice" });
  await act(async () => {
    fireEvent.click(link);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/setup"));
  expect(calls).toContainEqual({ url: "/api/start-now/own-photo", body: { own: false } });
});

test("consent for your own photo asks about the photos only", async () => {
  const { calls } = server({ ownPhoto: true, consent: { agreed: false } });
  const confirmed = vi.fn();
  render(<ConsentPage onConfirmed={confirmed} />);
  const box = await screen.findByRole("checkbox", {
    name: "The person in the photos I will upload agreed to have their picture animated by this app.",
  });
  expect(screen.getByText(/The voice stays the ready-made avatar's/)).toBeTruthy();
  fireEvent.click(box);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  });
  await waitFor(() => expect(confirmed).toHaveBeenCalledWith(true));
  expect(calls).toContainEqual({ url: "/api/consent", body: { agreed: true, photo_only: true } });
});

test("consent without Use my own photo asks about the photos and recordings", async () => {
  const { calls } = server({ consent: { agreed: false } });
  const confirmed = vi.fn();
  render(<ConsentPage onConfirmed={confirmed} />);
  fireEvent.click(await screen.findByRole("checkbox", { name: /photos and recordings I will upload/ }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  });
  await waitFor(() => expect(confirmed).toHaveBeenCalledWith(false));
  expect(calls).toContainEqual({ url: "/api/consent", body: { agreed: true, photo_only: false } });
});

test("setup for your own photo asks only for photos, and its review rejects only the image", async () => {
  server({ ownPhoto: true });
  render(<SetupPage change="photos" />);
  expect(await screen.findByRole("heading", { name: "Setup: your own photo" })).toBeTruthy();
  expect(screen.getByText(/the sample video is made with the avatar's voice/)).toBeTruthy();
  expect(screen.getByText("Step 1 of 2")).toBeTruthy();
  expect(screen.getByText("Step 2 of 2")).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "Voice recordings" })).toBeNull();
  expect(screen.queryByRole("heading", { name: /Accent/ })).toBeNull();
  expect(await screen.findByRole("button", { name: "Reject image" })).toBeTruthy();
  expect(screen.getByText("Accept it to see your photo in the chat, or go back and change the photo.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Reject voice" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Change accent" })).toBeNull();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
  });
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
});

test("setup for your own photo can switch to your own photo and voice", async () => {
  const { calls } = server({ ownPhoto: true });
  render(<SetupPage />);
  const button = await screen.findByRole("button", { name: "Use your own photo and voice instead" });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(calls).toContainEqual({ url: "/api/start-now/own-photo", body: { own: false } });
  expect(await screen.findByRole("heading", { name: "Voice recordings" })).toBeTruthy();
});

test("setup after consent for photos only asks for consent for the recordings", async () => {
  server({ consent: { agreed: true, photo_only: true } });
  render(<SetupPage />);
  expect(await screen.findByText(/You confirmed consent for your photos only/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Confirm consent" }).getAttribute("href")).toBe("#/consent");
});

test("your own photo says Goodbye once its sample is accepted", async () => {
  server({ ownPhoto: true, sampleAccepted: true });
  expect(await lineUrl("goodbye")).toBe(
    "/api/start-now/lines/goodbye?v=female-British-animated-Professor-own",
  );
});
