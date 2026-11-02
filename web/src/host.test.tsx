import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { hostPageOpened } from "./api";
import { navigation } from "./host";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

// A server with consent given and the host accounts of R188: "host@example.com" with the
// password "a long secret" can sign in; `state` says who is signed in.
function server(signedIn: string | null = null) {
  const state = {
    email: signedIn,
    taken: new Set(["host@example.com"]),
    signOutFails: false,
    confirmed: true,
    sent: 0,
  };
  const pages: string[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, string>) : {};
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/host/session") {
      return Response.json({
        signed_in: state.email !== null,
        email: state.email,
        confirmed: state.confirmed,
      });
    }
    if (url === "/api/host/forgot") {
      return Response.json({ detail: "If an account has that email address, a link is on its way." });
    }
    if (url === "/api/host/reset") {
      if (body.token !== "good-token") {
        return Response.json({ detail: "That link didn't work." }, { status: 400 });
      }
      return Response.json({ reset: true, email: "host@example.com" });
    }
    if (url === "/api/host/confirm/send") {
      state.sent += 1;
      if (state.sent === 1) {
        return Response.json(
          { detail: "The email was sent less than a minute ago." },
          { status: 429 },
        );
      }
      return Response.json({ sent: true });
    }
    if (url === "/api/host/page") {
      pages.push(body.page);
      return new Response(null, { status: 204 });
    }
    if (url === "/api/host/sign-up") {
      if (state.taken.has(body.email)) {
        return Response.json(
          { detail: "That email address is already signed up. Sign in instead." },
          { status: 409 },
        );
      }
      state.email = body.email;
      return Response.json({ signed_in: true, email: body.email });
    }
    if (url === "/api/host/sign-in") {
      if (body.email !== "host@example.com" || body.password !== "a long secret") {
        return Response.json(
          { detail: "The email address or password is wrong." },
          { status: 401 },
        );
      }
      state.email = body.email;
      return Response.json({ signed_in: true, email: body.email });
    }
    if (url === "/api/host/sign-out") {
      if (state.signOutFails) return new Response("", { status: 500 });
      state.email = null;
      return Response.json({ signed_in: false });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, state, pages };
}

function topBar(): HTMLElement {
  return document.querySelector("header") as HTMLElement;
}

function fill(label: RegExp, value: string) {
  fireEvent.input(screen.getByLabelText(label), { target: { value } });
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

test("the top bar has Host sign up and Host sign in while no host is signed in", async () => {
  server();
  window.location.hash = "#/chat";
  render(<App />);
  const bar = topBar();
  expect(await within(bar).findByRole("link", { name: "Host sign up" })).toHaveProperty(
    "hash",
    "#/host/sign-up",
  );
  expect(within(bar).getByRole("link", { name: "Host sign in" })).toHaveProperty(
    "hash",
    "#/host/sign-in",
  );
  expect(within(bar).queryByRole("button", { name: "Sign out" })).toBeNull();
});

test("signing up checks the fields, says the server's message, and signs in", async () => {
  const { pages } = server();
  window.location.hash = "#/host/sign-up";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign up" });
  await vi.waitFor(() => expect(pages).toEqual(["sign-up"]));

  fill(/^Email/, "new@example.com");
  fill(/^Password \(/, "short");
  fill(/^Password again/, "short");
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "The password must be at least 10 characters.",
  );

  fill(/^Password \(/, "a long secret");
  fill(/^Password again/, "a different one");
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  expect((await screen.findByRole("alert")).textContent).toBe("The two passwords are different.");

  fill(/^Email/, "host@example.com");
  fill(/^Password again/, "a long secret");
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  expect(
    await screen.findByText("That email address is already signed up. Sign in instead."),
  ).toBeTruthy();

  fill(/^Email/, "new@example.com");
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  expect(await within(topBar()).findByText("new@example.com")).toBeTruthy();
  await vi.waitFor(() => expect(window.location.hash).toBe("#/"));
  expect(within(topBar()).queryByRole("link", { name: "Host sign up" })).toBeNull();
});

test("signing up at the main address goes to the new site's setup at its trial path (R62)", async () => {
  const { state, fetchMock } = server();
  const real = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url === "/api/host/sign-up") {
      return Response.json({
        signed_in: true,
        email: "new@example.com",
        site: "k7q2x9mf3a8w",
        go_to: "/t/k7q2x9mf3a8w/",
      });
    }
    return real(url, init);
  });
  const went: string[] = [];
  vi.spyOn(navigation, "goTo").mockImplementation((url: string) => {
    went.push(url);
  });
  window.location.hash = "#/host/sign-up";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign up" });
  fill(/^Email/, "new@example.com");
  fill(/^Password \(/, "a long secret");
  fill(/^Password again/, "a long secret");
  fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  await vi.waitFor(() => expect(went).toEqual(["/t/k7q2x9mf3a8w/#/setup"]));
  // Left as it was: the browser is on its way to the new site.
  expect(window.location.hash).toBe("#/host/sign-up");
  expect(state.email).toBeNull();
});

test("a wrong password is refused with its message, then the right one signs in", async () => {
  const { pages } = server();
  window.location.hash = "#/host/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign in" });
  await vi.waitFor(() => expect(pages).toEqual(["sign-in"]));
  expect(screen.queryByLabelText(/^Password again/)).toBeNull();

  fill(/^Email/, "host@example.com");
  fill(/^Password/, "wrong one");
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The email address or password is wrong.",
  );

  fill(/^Password/, "a long secret");
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await within(topBar()).findByText("host@example.com")).toBeTruthy();
});

test("signing out returns to the participant view's chat", async () => {
  const { state } = server("host@example.com");
  window.location.hash = "#/";
  render(<App />);
  const bar = topBar();
  expect(await within(bar).findByText("host@example.com")).toBeTruthy();

  state.signOutFails = true;
  fireEvent.click(within(bar).getByRole("button", { name: "Sign out" }));
  await vi.waitFor(() => expect(console.error).toHaveBeenCalled());
  expect(within(bar).getByText("host@example.com")).toBeTruthy();

  state.signOutFails = false;
  fireEvent.click(within(bar).getByRole("button", { name: "Sign out" }));
  expect(await within(bar).findByRole("link", { name: "Host sign in" })).toBeTruthy();
  await vi.waitFor(() => expect(window.location.hash).toBe("#/chat"));
});

test("the sign-in pages say so when a host is already signed in", async () => {
  server("host@example.com");
  window.location.hash = "#/host/sign-in";
  render(<App />);
  expect(await screen.findByText(/You are signed in as host with host@example.com/)).toBeTruthy();
});

test("a host sign-in that can't be read shows the sign-in links", async () => {
  const { fetchMock } = server();
  const answer = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url === "/api/host/session" ? new Response("", { status: 500 }) : answer(url, init),
  );
  window.location.hash = "#/chat";
  render(<App />);
  expect(await within(topBar()).findByRole("link", { name: "Host sign in" })).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not read the host sign-in", expect.anything());
});

test("logging a host page opened resolves on the server's 204 and throws on an error", async () => {
  // Codex's review: a 204 has no body to parse.
  const { fetchMock } = server();
  await expect(hostPageOpened("sign-up")).resolves.toBeUndefined();
  fetchMock.mockResolvedValueOnce(new Response("", { status: 422 }));
  await expect(hostPageOpened("sign-in")).rejects.toThrow("422");
});

test("opening a host page logs no error about logging it", async () => {
  server();
  window.location.hash = "#/host/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign in" });
  await new Promise((r) => setTimeout(r, 50));
  expect(console.error).not.toHaveBeenCalledWith(
    "Could not log the host page opened",
    expect.anything(),
  );
});

test("a customer who hasn't confirmed their email is asked to, and can send it again (R62b)", async () => {
  const { state, fetchMock } = server("new@example.com");
  state.confirmed = false;
  window.location.hash = "#/setup";
  render(<App />);
  await screen.findByRole("heading", { name: "Confirm your email" });
  const main = document.querySelector(".host-page") as HTMLElement;
  expect(within(main).getByText("new@example.com")).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
  // Not yet the site's host: the host-only call isn't made.
  expect(fetchMock.mock.calls.some(([url]) => url === "/api/host/me")).toBe(false);

  fireEvent.click(screen.getByRole("button", { name: "Send it again" }));
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The email was sent less than a minute ago.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Send it again" }));
  expect((await screen.findByRole("status")).textContent).toBe(
    "A new link is on its way to new@example.com.",
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(state.sent).toBe(2);
});

test("a confirmation link that didn't work says so (R62b)", async () => {
  const { state } = server("new@example.com");
  state.confirmed = false;
  window.location.hash = "#/host/confirm-failed";
  render(<App />);
  await screen.findByRole("heading", { name: "Confirm your email" });
  expect((await screen.findByRole("alert")).textContent).toContain(
    "That confirmation link didn't work",
  );
  expect(screen.getByRole("button", { name: "Send it again" })).toBeTruthy();
});

test("a failed confirmation link opened while signed out says to sign in (R62b)", async () => {
  server();
  window.location.hash = "#/host/confirm-failed";
  render(<App />);
  await screen.findByRole("heading", { name: "Confirm your email" });
  expect(screen.getByRole("alert").textContent).toContain("more than 7 days old");
  const main = document.querySelector(".host-page") as HTMLElement;
  expect(within(main).getByRole("link", { name: "Host sign in" })).toHaveProperty(
    "hash",
    "#/host/sign-in",
  );
});

test("Forgot password asks for a link and shows the server's answer (R62a)", async () => {
  const { fetchMock } = server();
  window.location.hash = "#/host/sign-in";
  render(<App />);
  const link = await screen.findByRole("link", { name: "Forgot your password?" });
  expect(link).toHaveProperty("hash", "#/host/forgot");
  window.location.hash = "#/host/forgot";
  await screen.findByRole("heading", { name: "Forgot your password?" });
  fill(/^Email/, "host@example.com");
  fireEvent.click(screen.getByRole("button", { name: "Send the link" }));
  expect((await screen.findByRole("status")).textContent).toBe(
    "If an account has that email address, a link is on its way.",
  );
  const asked = fetchMock.mock.calls.find(([url]) => url === "/api/host/forgot");
  expect(JSON.parse(String(asked?.[1]?.body))).toEqual({ email: "host@example.com" });
});

test("a Forgot password link sets a new password, or says it didn't work (R62a)", async () => {
  server();
  window.location.hash = "#/host/reset/bad-token";
  render(<App />);
  await screen.findByRole("heading", { name: "Set a new password" });
  fill(/^New password \(/, "short");
  fill(/^New password again/, "short");
  fireEvent.click(screen.getByRole("button", { name: "Set the password" }));
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The password must be at least 10 characters.",
  );
  fill(/^New password \(/, "a new long secret");
  fill(/^New password again/, "another one");
  fireEvent.click(screen.getByRole("button", { name: "Set the password" }));
  expect((await screen.findByRole("alert")).textContent).toBe("The two passwords are different.");
  fill(/^New password again/, "a new long secret");
  fireEvent.click(screen.getByRole("button", { name: "Set the password" }));
  expect((await screen.findByRole("alert")).textContent).toBe("That link didn't work.");
  expect(screen.getByRole("link", { name: "Ask for a new one" })).toHaveProperty(
    "hash",
    "#/host/forgot",
  );

  cleanup();
  window.location.hash = "#/host/reset/good-token";
  render(<App />);
  await screen.findByRole("heading", { name: "Set a new password" });
  fill(/^New password \(/, "a new long secret");
  fill(/^New password again/, "a new long secret");
  fireEvent.click(screen.getByRole("button", { name: "Set the password" }));
  expect((await screen.findByRole("status")).textContent).toBe(
    "Your new password is set. Sign in with it.",
  );
});

test("a reset link opens while a customer who hasn't confirmed is signed in (R62a)", async () => {
  // Codex's review of PR #281: Confirm your email doesn't hide Forgot password's pages.
  const { state } = server("new@example.com");
  state.confirmed = false;
  window.location.hash = "#/host/reset/good-token";
  render(<App />);
  await screen.findByRole("heading", { name: "Set a new password" });
  expect(screen.queryByRole("heading", { name: "Confirm your email" })).toBeNull();
  fill(/^New password \(/, "a new long secret");
  fill(/^New password again/, "a new long secret");
  fireEvent.click(screen.getByRole("button", { name: "Set the password" }));
  expect((await screen.findByRole("status")).textContent).toBe(
    "Your new password is set. Sign in with it.",
  );

  cleanup();
  window.location.hash = "#/host/forgot";
  render(<App />);
  await screen.findByRole("heading", { name: "Forgot your password?" });

  // Every other page still says to confirm.
  cleanup();
  window.location.hash = "#/setup";
  render(<App />);
  await screen.findByRole("heading", { name: "Confirm your email" });
});
