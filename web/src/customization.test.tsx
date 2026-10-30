import { cleanup, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const MAYA = {
  identity: {
    name: "Maya",
    speaks_as: "the person seen in the video",
    purpose: "to teach astronomy",
    audience: "",
    helps_with: "the planets",
  },
  goals: ["Make every answer exam-ready."],
  guidelines: {},
  shipped: false,
};

// A server with consent given and, when `host`, a signed-in host; `customization` null fails.
function server(host: boolean, customization: object | null = MAYA) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") {
        return Response.json({ view: host ? "host" : "participant", general_prompts: false });
      }
      if (url === "/api/host/session") {
        return Response.json({ signed_in: host, email: host ? "host@example.com" : null });
      }
      if (url === "/api/settings/access") return Response.json({ shown: true, as: null });
      if (url.startsWith("/api/customization")) {
        asked.push(url);
        return customization ? Response.json(customization) : new Response("", { status: 500 });
      }
      return new Response("", { status: 404 });
    }),
  );
  return { asked };
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

test("a signed-in host finds Customization at the bottom of Settings' Chat section", async () => {
  server(true);
  window.location.hash = "#/settings";
  render(<App />);
  const chat = (await screen.findByRole("heading", { name: "Chat" })).closest("section");
  const link = await within(chat as HTMLElement).findByRole("link", { name: "Customization" });
  expect(link).toHaveProperty("hash", "#/customization");
  const parts = Array.from((chat as HTMLElement).querySelectorAll(".switch"));
  expect(parts[parts.length - 1].contains(link)).toBe(true);
});

test("anyone not signed in as a host has no Customization link in Settings", async () => {
  server(false);
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Chat" });
  expect(screen.queryByRole("link", { name: "Customization" })).toBeNull();
});

test("the Customization page shows the identity and goals", async () => {
  const { asked } = server(true);
  window.location.hash = "#/customization";
  render(<App />);
  const identity = within(await screen.findByRole("region", { name: "Identity" }));
  const values = identity.getAllByRole("definition").map((d) => d.textContent);
  expect(values).toEqual([
    "Maya",
    "the person seen in the video",
    "to teach astronomy",
    "Not set",
    "the planets",
  ]);
  const goals = within(screen.getByRole("region", { name: "Goals" }));
  expect(goals.getByText("Make every answer exam-ready.")).toBeTruthy();
  expect(screen.queryByText(/As shipped/)).toBeNull();
  expect(asked).toEqual(["/api/customization?opened=true"]);
  expect(console.info).toHaveBeenCalledWith("Customization page opened: shipped=false");
});

test("the shipped customization says so, and no goals says none", async () => {
  server(true, { ...MAYA, goals: [], shipped: true });
  window.location.hash = "#/customization";
  render(<App />);
  expect(await screen.findByText(/^As shipped\./)).toBeTruthy();
  expect(within(screen.getByRole("region", { name: "Goals" })).getByText("None")).toBeTruthy();
});

test("the Customization page is for the host only", async () => {
  const { asked } = server(false);
  window.location.hash = "#/customization";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "For the host only" })).toBeTruthy();
  expect(asked).toEqual([]);
});

test("a customization that can't be read says so", async () => {
  server(true, null);
  window.location.hash = "#/customization";
  render(<App />);
  expect(
    await screen.findByText("The customization could not be read. Reload to try again."),
  ).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not read the customization",
    expect.anything(),
  );
});
