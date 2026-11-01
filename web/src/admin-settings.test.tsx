import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AdminSettings } from "./api";

const RECOMMENDED = { blue_above: 60, orange_below: 30, red_below: 15 };
const ORDER = "Red must be below orange, and orange below blue, all from 1 to 99.";

// A server with an administrator signed in, keeping the admin settings as the real one does.
function server() {
  const state = {
    signedIn: true,
    timeout_minutes: 30,
    thresholds: { ...RECOMMENDED },
    disable_custom_image: true,
    disable_custom_voice: true,
    refuse: null as number | null,
  };
  const settings = (): AdminSettings => ({
    timeout_minutes: state.timeout_minutes,
    thresholds: { ...state.thresholds },
    disable_custom_image: state.disable_custom_image,
    disable_custom_voice: state.disable_custom_voice,
    recommended: {
      timeout_minutes: 30,
      thresholds: RECOMMENDED,
      disable_custom_image: true,
      disable_custom_voice: true,
    },
  });
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/admin/laptop") return Response.json({ listed: true });
    if (url === "/api/admin/session") {
      return Response.json({
        signed_in: state.signedIn,
        password_set: true,
        timeout_minutes: state.timeout_minutes,
        ended: state.signedIn ? null : "inactive",
      });
    }
    if (url === "/api/admin/resources") {
      return Response.json({ read_at: "", thresholds: state.thresholds, resources: [] });
    }
    if (url === "/api/admin/settings") {
      if (state.refuse) {
        if (state.refuse === 401) state.signedIn = false;
        return Response.json({ detail: ORDER }, { status: state.refuse });
      }
      if (init?.method === "PUT") {
        const changes = JSON.parse(String(init.body)) as Partial<AdminSettings>;
        state.timeout_minutes = changes.timeout_minutes ?? state.timeout_minutes;
        state.thresholds = changes.thresholds ?? state.thresholds;
        state.disable_custom_image = changes.disable_custom_image ?? state.disable_custom_image;
        state.disable_custom_voice = changes.disable_custom_voice ?? state.disable_custom_voice;
      }
      return Response.json(settings());
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const puts = () =>
    fetchMock.mock.calls
      .filter(([u, init]) => u === "/api/admin/settings" && init?.method === "PUT")
      .map(([, init]) => JSON.parse(String(init?.body)));
  return { state, puts };
}

async function openSettings() {
  window.location.hash = "#/admin/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Colours on the dashboard" });
}

function field(label: RegExp): HTMLInputElement {
  return screen.getByLabelText(label);
}

async function type(label: RegExp, value: string) {
  await act(async () => {
    fireEvent.input(field(label), { target: { value } });
  });
}

async function save() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
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
});

test("the settings show the minutes and the thresholds, with the recommended ones", async () => {
  server();
  await openSettings();
  expect(field(/Minutes without activity/).value).toBe("30");
  expect(field(/Blue/).value).toBe("60");
  expect(field(/Orange/).value).toBe("30");
  expect(field(/Red/).value).toBe("15");
  expect(screen.getByText(/blue above 60%, orange below 30%, red below 15%/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Admin settings" }).getAttribute("aria-current")).toBe(
    "page",
  );
  expect(console.info).toHaveBeenCalledWith("Admin settings shown");
});

test("saving changes them and the sign-out minutes shown elsewhere", async () => {
  const { puts } = server();
  await openSettings();
  await type(/Minutes without activity/, "5");
  await type(/Blue/, "70");
  await type(/Orange/, "40");
  await type(/Red/, "20");
  await save();
  expect(puts()).toEqual([
    {
      timeout_minutes: 5,
      thresholds: { blue_above: 70, orange_below: 40, red_below: 20 },
      disable_custom_image: true,
      disable_custom_voice: true,
    },
  ]);
  expect((await screen.findByRole("status")).textContent).toContain("Saved.");
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Admin settings saved \(\d+ ms\)$/));

  // The Settings page now says 5 minutes.
  await act(async () => {
    window.location.hash = "#/settings";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(await screen.findByText(/signed out after 5 minutes/)).toBeTruthy();
});

test("a change the server refuses says why and keeps what was typed", async () => {
  const { state } = server();
  await openSettings();
  await type(/Red/, "50");
  state.refuse = 400;
  await save();
  expect(await screen.findByText(ORDER)).toBeTruthy();
  expect(field(/Red/).value).toBe("50");
  expect(screen.queryByText(/Saved\./)).toBeNull();
});

test("the recommended thresholds are put back at once", async () => {
  const { state, puts } = server();
  state.thresholds = { blue_above: 90, orange_below: 50, red_below: 40 };
  state.timeout_minutes = 45;
  await openSettings();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Use the recommended thresholds" }));
  });
  expect(puts()).toEqual([
    { timeout_minutes: 45, thresholds: RECOMMENDED, disable_custom_image: true, disable_custom_voice: true },
  ]);
  await screen.findByRole("status");
  expect(field(/Blue/).value).toBe("60");
  expect(field(/Minutes without activity/).value).toBe("45"); // only the thresholds
});

test("the recommended thresholds keep the minutes as typed, not as last saved", async () => {
  const { puts } = server();
  await openSettings();
  await type(/Minutes without activity/, "5");
  await type(/Red/, "20");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Use the recommended thresholds" }));
  });
  expect(puts()).toEqual([
    { timeout_minutes: 5, thresholds: RECOMMENDED, disable_custom_image: true, disable_custom_voice: true },
  ]);
  await screen.findByRole("status");
  expect(field(/Minutes without activity/).value).toBe("5");
  expect(field(/Red/).value).toBe("15");
});

test("signed out while saving, the sign-in comes back", async () => {
  const { state } = server();
  await openSettings();
  state.refuse = 401;
  await save();
  await screen.findByLabelText("Administrator password");
  expect(screen.queryByRole("heading", { name: "Colours on the dashboard" })).toBeNull();
});

test("settings that can't be read say so", async () => {
  const { state } = server();
  state.refuse = 500;
  window.location.hash = "#/admin/settings";
  render(<App />);
  expect(await screen.findByText(/could not be read/)).toBeTruthy();
});

test("the tabs move between the resources and the settings", async () => {
  server();
  window.location.hash = "#/admin";
  render(<App />);
  await screen.findByRole("heading", { name: "Resources" });
  expect(screen.getByRole("link", { name: "Admin settings" }).getAttribute("href")).toBe(
    "#/admin/settings",
  );
  await act(async () => {
    window.location.hash = "#/admin/settings";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await screen.findByRole("heading", { name: "Automatic sign-out" });
  expect(screen.queryByRole("heading", { name: "Resources" })).toBeNull();
});

test("Hosts has the two checkboxes, checked by default, saved as ticked", async () => {
  const { state, puts } = server();
  await openSettings();
  expect(screen.getByRole("heading", { name: "Hosts" })).toBeTruthy();
  expect(field(/Disable custom image/).checked).toBe(true);
  expect(field(/Disable custom voice/).checked).toBe(true);
  await act(async () => {
    fireEvent.click(field(/Disable custom voice/));
  });
  expect(field(/Disable custom voice/).checked).toBe(false);
  await save();
  expect(puts()[0]).toMatchObject({ disable_custom_image: true, disable_custom_voice: false });
  expect(state.disable_custom_voice).toBe(false);
  await screen.findByRole("status");
  expect(field(/Disable custom voice/).checked).toBe(false);
  expect(field(/Disable custom image/).checked).toBe(true);
});
