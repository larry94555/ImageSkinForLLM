import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { ChangeSetup } from "./change-setup";
import { CHANGE_NOTICE } from "./pages";
import { openSettings } from "./settings.test.util";

// A server with consent given, the view saved as `view` and the sample accepted or not; anything
// else isn't there. review is null when it can't be read.
function server(accepted: boolean | null, view = "host", defaultPerson = false) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({ view });
    if (url === "/api/review" && accepted !== null) {
      const at = accepted && !defaultPerson ? "2026-10-17T10:00:00+00:00" : null;
      return Response.json({ accepted, accepted_at: at, default_person: defaultPerson });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

test("each change opens setup at its part", async () => {
  server(true);
  render(<ChangeSetup />);
  const href = (name: string) => screen.getByRole("link", { name }).getAttribute("href");
  expect(href("Change photos")).toBe("#/setup/photos");
  expect(href("Change recordings")).toBe("#/setup/sounds");
  expect(href("Change accent")).toBe("#/setup/accent");
  await screen.findByText("The chat is open with the sample you accepted.");
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Sample accepted: true, avatar in use: own \(\d+ ms\)$/),
  );
  fireEvent.click(screen.getByRole("link", { name: "Change accent" }));
  expect(console.info).toHaveBeenCalledWith("Changing the accent from Settings");
});

test("Avatar Choice shows your own and a ready-made avatar side by side (R32a)", async () => {
  server(true);
  render(<ChangeSetup />);
  await screen.findByText("The chat is open with the sample you accepted.");
  const own = screen.getByRole("heading", { name: /Your own photo and voice/ });
  expect(within(own).getByText("In use")).toBeTruthy();
  expect(within(screen.getByRole("heading", { name: /Ready-made avatar/ })).queryByText("In use")).toBeNull();
  const ready = screen.getByRole("link", { name: "Use a ready-made avatar" });
  expect(ready.getAttribute("href")).toBe("#/start-now");
  fireEvent.click(ready);
  expect(console.info).toHaveBeenCalledWith("Choosing a ready-made avatar from Settings");
});

test("with a ready-made avatar in use, your own is one click away (R32a)", async () => {
  server(true, "host", true);
  render(<ChangeSetup />);
  const own = await screen.findByRole("link", { name: "Use your own photo and voice" });
  expect(own.getAttribute("href")).toBe("#/setup");
  const ready = screen.getByRole("heading", { name: /Ready-made avatar/ });
  expect(within(ready).getByText("In use")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Choose another avatar" }).getAttribute("href")).toBe("#/start-now");
  expect(screen.queryByRole("link", { name: "Change photos" })).toBeNull();
  expect(screen.queryByText(/The chat is (open|locked)/)).toBeNull();
  fireEvent.click(own);
  expect(console.info).toHaveBeenCalledWith("Switching to your own photo and voice from Settings");
});

test("a locked chat says a new sample needs accepting", async () => {
  server(false);
  render(<ChangeSetup />);
  const locked = await screen.findByText(/The chat is locked until you accept a sample video/);
  expect(within(locked).getByRole("link", { name: "Setup" }).getAttribute("href")).toBe("#/setup");
});

test("a review that can't be read shows neither state", async () => {
  server(null);
  render(<ChangeSetup />);
  await waitFor(() => expect(console.error).toHaveBeenCalledWith("Could not get the review", expect.anything()));
  expect(screen.queryByText(/The chat is (open|locked)/)).toBeNull();
  expect(screen.getByRole("link", { name: "Change photos" })).toBeTruthy();
});

test("from Settings, setup opens at the part to change with what to do there", async () => {
  server(true);
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  for (const [name, part] of [
    ["Change accent", "accent"],
    ["Change photos", "photos"],
    ["Change recordings", "sounds"],
  ] as const) {
    await act(async () => {
      window.location.hash = screen.getByRole("link", { name }).getAttribute("href") ?? "";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    await screen.findByRole("heading", { name: "Setup", level: 1 });
    const notice = await screen.findByText(CHANGE_NOTICE[part]);
    expect(notice.closest("section")?.id).toBe(part);
    expect(console.info).toHaveBeenCalledWith(`Setup opened to change the ${part}`);
    await openSettings();
  }
});

test("the participant view has no way to change them", async () => {
  server(true, "participant");
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  expect(screen.queryByRole("heading", { name: "Photo, voice and accent" })).toBeNull();
});
