// Starting a deleted site again (roadmap R69c): signing in to an account whose site was deleted
// says so and offers Start my site again, which goes to the new site, signed in, where Resume
// subscription brings it live (R69b).

import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { navigation } from "./host";

vi.unmock("./api");

const DELETED = "Your site was deleted. Your account is kept, so you can start it again.";
const LINK = "https://dans.me0.ai/api/host/sign-in/once";

function server(restart: { status: number; body: object } = { status: 200, body: { sign_in_at: LINK } }) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url} ${init?.body ?? ""}`.trim());
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({});
      if (url === "/api/host/session") return Response.json({ signed_in: false, email: null });
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/sign-in") {
        const body = JSON.parse(String(init?.body)) as { password: string };
        if (body.password !== "a long secret") {
          return Response.json({ detail: "The email address or password is wrong." }, { status: 401 });
        }
        return Response.json({ detail: DELETED, deleted: true }, { status: 401 });
      }
      if (url === "/api/host/restart") return Response.json(restart.body, { status: restart.status });
      return new Response("", { status: 404 });
    }),
  );
  return asked;
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

async function signIn(password = "a long secret") {
  window.location.hash = "#/host/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign in" });
  fireEvent.input(screen.getByLabelText(/^Email/), { target: { value: "dan@example.com" } });
  fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

test("A deleted site's host is offered Start my site again, which goes to the new site", async () => {
  const asked = server();
  const went: string[] = [];
  vi.spyOn(navigation, "goTo").mockImplementation((url: string) => {
    went.push(url);
  });
  await signIn();
  expect((await screen.findByRole("alert")).textContent).toBe(DELETED);
  expect(screen.getByText(/at your old address if it is still free/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Start my site again" }));
  await vi.waitFor(() => expect(went).toEqual([LINK]));
  expect(asked).toContain(
    'POST /api/host/restart {"email":"dan@example.com","password":"a long secret"}',
  );
});

test("A wrong password offers nothing more", async () => {
  server();
  await signIn("wrong one");
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The email address or password is wrong.",
  );
  expect(screen.queryByRole("button", { name: "Start my site again" })).toBeNull();
});

test("A restart the server refuses is said, and the button goes", async () => {
  server({ status: 503, body: { detail: "Your account was made, but its site wasn't." } });
  await signIn();
  fireEvent.click(await screen.findByRole("button", { name: "Start my site again" }));
  expect(await screen.findByText("Your account was made, but its site wasn't.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Start my site again" })).toBeNull();
});

test("A restart that fails without a reason asks to try again", async () => {
  server();
  await signIn();
  const button = await screen.findByRole("button", { name: "Start my site again" });
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
  fireEvent.click(button);
  expect(await screen.findByText("That didn't work. Please try again.")).toBeTruthy();
});
