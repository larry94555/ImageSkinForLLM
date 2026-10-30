import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { hostPageOpened } from "./api";

// A server with consent given and the host accounts of R188: "host@example.com" with the
// password "a long secret" can sign in; `state` says who is signed in.
function server(signedIn: string | null = null) {
  const state = { email: signedIn, taken: new Set(["host@example.com"]), signOutFails: false };
  const pages: string[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, string>) : {};
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/host/session") {
      return Response.json({ signed_in: state.email !== null, email: state.email });
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
  expect(window.location.hash).toBe("#/");
  expect(within(topBar()).queryByRole("link", { name: "Host sign up" })).toBeNull();
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
  expect(window.location.hash).toBe("#/chat");
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
