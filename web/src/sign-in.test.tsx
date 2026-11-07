// The one Sign in page (roadmap R269): the display name filled in from the email, and the
// participant's side of signing in and up. host.test.tsx and participant.test.tsx have the rest.

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { reloading } from "./participant";

vi.unmock("./api");

const PAT = "pat@example.com";

interface Server {
  participant: boolean;
  name: string | null;
  suggestion: "pat1" | "fails";
  participantSignIn: number;
  asked: string[];
}

function server(state: Partial<Server> = {}): Server {
  const s: Server = {
    participant: false,
    name: null,
    suggestion: "pat1",
    participantSignIn: 401,
    asked: [],
    ...state,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      s.asked.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "participant" });
      if (url === "/api/settings/access") return Response.json({ shown: false, as: null });
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/session") {
        return Response.json({ signed_in: false, email: null, host_name: "Dr. Smith" });
      }
      if (url === "/api/participant/session") {
        return Response.json({
          signed_in: s.participant,
          email: s.participant ? PAT : null,
          ...(s.participant && s.name ? { display_name: s.name } : {}),
        });
      }
      if (url.startsWith("/api/host/display-name/suggestion")) {
        return s.suggestion === "fails"
          ? new Response("", { status: 503 })
          : Response.json({ display_name: s.suggestion });
      }
      if (url === "/api/host/sign-in") return Response.json({ detail: "Wrong." }, { status: 401 });
      if (url === "/api/participant/sign-in") {
        return Response.json({ detail: "Accounts can't be read." }, { status: s.participantSignIn });
      }
      if (url === "/api/participant/progress") return Response.json({});
      return new Response("", { status: 404 });
    }),
  );
  return s;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(reloading, "reload").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

async function page() {
  window.location.hash = "#/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Sign in" });
}

function nameField(): HTMLInputElement {
  return screen.getByLabelText(/^Display name/) as HTMLInputElement;
}

test("the display name is asked for once per email, and only once there is an @", async () => {
  const s = server();
  await page();
  const email = screen.getByLabelText("Email");
  fireEvent.input(email, { target: { value: "pat" } });
  fireEvent.blur(email);
  fireEvent.input(email, { target: { value: PAT } });
  fireEvent.blur(email);
  await waitFor(() => expect(nameField().value).toBe("pat1"));
  fireEvent.blur(email);
  const asks = s.asked.filter((a) => a.includes("/display-name/suggestion"));
  expect(asks).toEqual([`GET /api/host/display-name/suggestion?email=${encodeURIComponent(PAT)}`]);
});

test("a suggestion that fails leaves the display name blank, and says so in the log", async () => {
  server({ suggestion: "fails" });
  await page();
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: PAT } });
  fireEvent.blur(screen.getByLabelText("Email"));
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith("Could not suggest a display name", expect.anything()),
  );
  expect(nameField().value).toBe("");
});

test("a participant sign-in the server can't answer says why, and makes no account", async () => {
  const s = server({ participantSignIn: 503 });
  await page();
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: PAT } });
  fireEvent.input(screen.getByLabelText(/^Password$/), { target: { value: "a long secret" } });
  fireEvent.input(screen.getByLabelText(/^Password again/), { target: { value: "a long secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Accounts can't be read.");
  expect(s.asked.some((a) => a.endsWith("/sign-up"))).toBe(false);
});

test("a signed-in participant is named by their display name, and the page says so", async () => {
  server({ participant: true, name: "Pat Lee" });
  await page();
  expect(await screen.findByText(/You are signed in as Pat Lee/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Go on" })).toHaveProperty("hash", "#/chat");
  const bar = within(document.querySelector("header") as HTMLElement);
  expect(bar.getByText("Pat Lee")).toBeTruthy();
  expect(bar.queryByText(PAT)).toBeNull();
});
