import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CHECK_MS } from "./admin";
import { App } from "./App";

// A server with consent given, the settings as `settings`, and an administrator password
// "secret" unless `passwordSet` is false. `state` is changed by the tests to sign out by itself.
function server(settings: Record<string, unknown> = {}, passwordSet = true) {
  const state = { signedIn: false, ended: null as string | null, activityOk: true };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json(settings);
    if (url === "/api/admin/session") {
      const ended = state.ended;
      state.ended = null;
      return Response.json({
        signed_in: state.signedIn,
        password_set: passwordSet,
        timeout_minutes: 30,
        ended,
      });
    }
    if (url === "/api/admin/sign-in") {
      const { password } = JSON.parse(String(init?.body)) as { password: string };
      if (password !== "secret") {
        return Response.json({ detail: "That isn't the administrator password." }, { status: 401 });
      }
      state.signedIn = true;
      return Response.json({ signed_in: true });
    }
    if (url === "/api/admin/sign-out") {
      state.signedIn = false;
      return Response.json({ signed_in: false });
    }
    if (url === "/api/admin/activity") {
      return new Response(null, { status: state.activityOk ? 204 : 401 });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, state };
}

async function openAt(hash: string) {
  window.location.hash = hash;
  render(<App />);
  await screen.findByRole("link", { name: "Settings" });
}

function adminSection() {
  return within(screen.getByRole("region", { name: "Administrator" }));
}

async function signIn(password: string) {
  const section = adminSection();
  await act(async () => {
    fireEvent.input(section.getByLabelText("Administrator password"), {
      target: { value: password },
    });
  });
  await act(async () => {
    fireEvent.click(section.getByRole("button", { name: "Sign in as administrator" }));
  });
}

function calls(fetchMock: ReturnType<typeof vi.fn>, url: string): number {
  return fetchMock.mock.calls.filter(([u]) => u === url).length;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("signing in shows the Admin link and the admin view, and signing out hides them", async () => {
  server();
  await openAt("#/settings");
  expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  await screen.findByLabelText("Administrator password");
  // The button is never greyed out: with nothing typed, it says what's missing.
  const button = adminSection().getByRole("button", { name: "Sign in as administrator" });
  expect(button).toHaveProperty("disabled", false);
  await act(async () => {
    fireEvent.click(button);
  });
  expect(adminSection().getByText("Type the administrator password first.")).toBeTruthy();

  await signIn("guess");
  await adminSection().findByText("That isn't the administrator password.");
  expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();

  await signIn("secret");
  await screen.findByRole("link", { name: "Admin" });
  expect(adminSection().getByText(/Signed in as administrator/).textContent).toContain(
    "30 minutes without activity",
  );
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Admin signed in \(\d+ ms\)$/));

  await act(async () => {
    fireEvent.click(screen.getByRole("link", { name: "Admin" }));
  });
  await screen.findByRole("heading", { name: "Admin", level: 1 });
  expect(screen.getByText("You are signed in as administrator.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Admin" }).className).toBe("settings-link current");

  window.location.hash = "#/settings";
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  await act(async () => {
    fireEvent.click(adminSection().getByRole("button", { name: "Sign out as administrator" }));
  });
  await screen.findByLabelText("Administrator password");
  expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  expect(console.info).toHaveBeenCalledWith("Admin signed out: signed out");
});

test("with no password set, signing in is off and says so", async () => {
  server({}, false);
  await openAt("#/settings");
  await screen.findByText(/Signing in as the administrator is off/);
  expect(screen.queryByLabelText("Administrator password")).toBeNull();
});

test("the participant view has the Administrator section too", async () => {
  server({ view: "participant" });
  await openAt("#/settings");
  await screen.findByLabelText("Administrator password");
});

test("the admin view opened without a sign-in shows the sign-in", async () => {
  server();
  await openAt("#/admin");
  expect(screen.getByRole("heading", { name: "Admin", level: 1 })).toBeTruthy();
  await screen.findByLabelText("Administrator password");
  expect(screen.queryByText("You are signed in as administrator.")).toBeNull();
});

test("a sign-in ended by inactivity says so on any page and leaves the admin view", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { state } = server();
  await openAt("#/settings");
  await screen.findByLabelText("Administrator password");
  await signIn("secret");
  window.location.hash = "#/admin";
  await screen.findByText("You are signed in as administrator.");

  state.signedIn = false;
  state.ended = "inactive";
  await act(async () => {
    await vi.advanceTimersByTimeAsync(CHECK_MS);
  });
  const notice = await screen.findByRole("status");
  expect(notice.textContent).toContain(
    "Signed out as administrator after 30 minutes without activity.",
  );
  expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  expect(screen.queryByText("You are signed in as administrator.")).toBeNull();
  expect(console.info).toHaveBeenCalledWith("Admin signed out: inactive");

  await act(async () => {
    fireEvent.click(within(notice).getByRole("button", { name: "OK" }));
  });
  expect(screen.queryByRole("status")).toBeNull();
});

test("a changed password says why the sign-in ended", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { state } = server();
  await openAt("#/settings");
  await screen.findByLabelText("Administrator password");
  await signIn("secret");
  await screen.findByRole("link", { name: "Admin" });
  state.signedIn = false;
  state.ended = "password changed";
  await act(async () => {
    await vi.advanceTimersByTimeAsync(CHECK_MS);
  });
  expect((await screen.findByRole("status")).textContent).toContain(
    "because the administrator password was changed",
  );
});

test("a click on the Settings page or in the admin view is activity, at most once a minute", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { fetchMock, state } = server();
  await openAt("#/settings");
  await screen.findByLabelText("Administrator password");
  await signIn("secret");
  await screen.findByRole("link", { name: "Admin" });
  const activity = () => calls(fetchMock, "/api/admin/activity");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(61_000); // past the sign-in click
  });

  await act(async () => {
    fireEvent.click(document.body);
    fireEvent.keyDown(document.body, { key: "a" });
  });
  expect(activity()).toBe(1);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(61_000);
  });
  window.location.hash = "#/admin";
  await screen.findByText("You are signed in as administrator.");
  await act(async () => {
    fireEvent.keyDown(document.body, { key: "a" });
  });
  expect(activity()).toBe(2);

  // Elsewhere, a click is not activity.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(61_000);
  });
  window.location.hash = "#/chat";
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10);
  });
  await act(async () => {
    fireEvent.click(document.body);
  });
  expect(activity()).toBe(2);

  // Activity refused: the sign-in has ended, so it is read again.
  window.location.hash = "#/settings";
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10);
  });
  state.activityOk = false;
  state.signedIn = false;
  const before = calls(fetchMock, "/api/admin/session");
  await act(async () => {
    fireEvent.click(document.body);
  });
  expect(activity()).toBe(3);
  expect(calls(fetchMock, "/api/admin/session")).toBeGreaterThan(before);
  await screen.findByLabelText("Administrator password");
});

test("a server that can't be reached leaves the sign-in waiting", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({});
      return new Response("", { status: 500 });
    }),
  );
  await openAt("#/settings");
  expect(adminSection().getByText("Checking…")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not read the administrator sign-in",
    expect.any(Error),
  );
});

test("a password the browser filled in signs in, though it sent no input event", async () => {
  server();
  await openAt("#/settings");
  const input = await screen.findByLabelText<HTMLInputElement>("Administrator password");
  input.value = "secret";
  await act(async () => {
    fireEvent.click(adminSection().getByRole("button", { name: "Sign in as administrator" }));
  });
  await screen.findByRole("link", { name: "Admin" });
});
