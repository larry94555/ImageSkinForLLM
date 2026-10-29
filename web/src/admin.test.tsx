import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CHECK_MS, GUIDE } from "./admin";
import { App } from "./App";
import { indexedDbStore, type KeyStore, useKeyStore } from "./laptop-key";

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
        // Every failure answers alike, with a new code (R162).
        return Response.json(
          { detail: "Admin login failed with error code A-7K3F9Q.", code: "A-7K3F9Q" },
          { status: 401 },
        );
      }
      state.signedIn = true;
      return Response.json({ signed_in: true });
    }
    if (url === "/api/admin/challenge") return Response.json({ challenge: "the challenge" });
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
  useKeyStore(indexedDbStore);
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("signing in shows the Admin link and the admin view, and signing out hides them", async () => {
  server();
  await openAt("#/settings");
  expect(screen.queryByRole("link", { name: "Admin" })).toBeNull();
  await screen.findByLabelText("Administrator password");
  expect(adminSection().getByRole("button", { name: "Sign in as administrator" })).toHaveProperty(
    "disabled",
    true,
  );

  await signIn("guess");
  // Shown as it comes, with the code that finds the cause in the log.
  await adminSection().findByText("Admin login failed with error code A-7K3F9Q.");
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
  expect(screen.getByRole("heading", { name: "Resources" })).toBeTruthy();
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
  expect(screen.getByRole("link", { name: "admin password guide" }).getAttribute("href")).toBe(
    GUIDE,
  );
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
  expect(screen.queryByRole("heading", { name: "Resources" })).toBeNull();
});

test("a sign-in ended by inactivity says so on any page and leaves the admin view", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { state } = server();
  await openAt("#/settings");
  await screen.findByLabelText("Administrator password");
  await signIn("secret");
  window.location.hash = "#/admin";
  await screen.findByRole("heading", { name: "Resources" });

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
  expect(screen.queryByRole("heading", { name: "Resources" })).toBeNull();
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

test("a laptop taken out of the list signs out without saying why", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const { state } = server();
  await openAt("#/settings");
  await screen.findByLabelText("Administrator password");
  await signIn("secret");
  await screen.findByRole("link", { name: "Admin" });
  state.signedIn = false;
  state.ended = "laptop removed";
  await act(async () => {
    await vi.advanceTimersByTimeAsync(CHECK_MS);
  });
  const notice = await screen.findByRole("status");
  expect(notice.textContent).toContain("Signed out as administrator.");
  expect(notice.textContent).not.toContain("laptop");
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
  await screen.findByRole("heading", { name: "Resources" });
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
    await vi.advanceTimersByTimeAsync(150);
  });
  await act(async () => {
    fireEvent.click(document.body);
  });
  expect(activity()).toBe(2);

  // Activity refused: the sign-in has ended, so it is read again.
  window.location.hash = "#/settings";
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  // Preact runs effects after the next frame, or 100 ms at most: past that the listener is on.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(150);
  });
  state.activityOk = false;
  state.signedIn = false;
  const before = calls(fetchMock, "/api/admin/session");
  await act(async () => {
    fireEvent.click(document.body);
  });
  expect(activity()).toBe(3);
  await vi.waitFor(() => expect(calls(fetchMock, "/api/admin/session")).toBeGreaterThan(before));
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

// A browser that can make a laptop key (HTTPS or localhost), kept in memory for the test.
function secureBrowser(): void {
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("indexedDB", {});
  let kept: CryptoKeyPair | undefined;
  const store: KeyStore = {
    load: async () => kept,
    save: async (pair) => {
      kept = pair;
    },
  };
  useKeyStore(store);
}

test("the Settings page shows this laptop's ID, and Copy gives the lines for the file", async () => {
  secureBrowser();
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  server();
  await openAt("#/settings");
  const id = (await adminSection().findByText(/^LT(-[A-Z2-7]{4}){5}$/)).textContent!;
  await act(async () => {
    fireEvent.click(adminSection().getByRole("button", { name: "Copy" }));
  });
  expect(writeText).toHaveBeenCalledWith(`[[laptop]]\nname = "My laptop"\nid = "${id}"\n`);
  await adminSection().findByRole("button", { name: "Copied" });
  expect(console.info).toHaveBeenCalledWith("Laptop ID shown");
});

test("the ID is shown whether or not a password is set or signed in", async () => {
  secureBrowser();
  server({}, false);
  await openAt("#/settings");
  await adminSection().findByText(/^LT-/);
});

test("signing in sends this laptop's proof of the challenge", async () => {
  secureBrowser();
  const { fetchMock } = server();
  await openAt("#/settings");
  await adminSection().findByText(/^LT-/);
  await signIn("secret");
  await screen.findByRole("link", { name: "Admin" });
  const sent = fetchMock.mock.calls.find(([u]) => u === "/api/admin/sign-in")!;
  const body = JSON.parse(String(sent[1]!.body)) as {
    password: string;
    laptop: { public_key: string; challenge: string; signature: string };
  };
  expect(body.password).toBe("secret");
  expect(body.laptop.challenge).toBe("the challenge");
  expect(atob(body.laptop.signature).length).toBe(64);
  expect(calls(fetchMock, "/api/admin/challenge")).toBe(1);
});

test("at a plain http address the ID can't be shown and no proof is sent", async () => {
  const { fetchMock } = server();
  await openAt("#/settings");
  await adminSection().findByText(/can't be shown at this address/);
  await signIn("secret");
  await screen.findByRole("link", { name: "Admin" });
  const sent = fetchMock.mock.calls.find(([u]) => u === "/api/admin/sign-in")!;
  expect(JSON.parse(String(sent[1]!.body))).toEqual({ password: "secret" });
  expect(calls(fetchMock, "/api/admin/challenge")).toBe(0);
});

test("a key that can't be made says so", async () => {
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("indexedDB", {});
  useKeyStore({
    load: () => Promise.reject(new Error("blocked")),
    save: async () => {},
  });
  server();
  await openAt("#/settings");
  await adminSection().findByText("This laptop's ID couldn't be made in this browser.");
});
