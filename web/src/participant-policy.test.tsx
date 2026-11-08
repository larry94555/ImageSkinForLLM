// Where each participant may go (roadmap R261): the host's account page sets the sites every
// participant, or one of them, may open and where signing in sends them; signing in follows it.

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { ParticipantPolicy } from "./api";
import { reloading } from "./participant";

vi.unmock("./api");

const SITES = [
  { site: "a", address: "https://a.me0.ai" },
  { site: "b", address: "https://b.me0.ai" },
];
const PAT = "pat@example.com";

interface Server {
  policy: ParticipantPolicy;
  asked: string[];
  refuse?: string;
  readFails?: boolean;
}

function server(state: Partial<Server> = {}): Server {
  const s: Server = {
    policy: { every: { sites: null, landing: null }, participants: {} },
    asked: [],
    ...state,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? init.body : "";
      s.asked.push(`${method} ${url} ${body}`.trim());
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "host" });
      if (url === "/api/settings/access")
        return Response.json({ shown: true, as: "host" });
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: true,
          email: "ann@example.com",
          display_name: "Ann",
          confirmed: true,
        });
      }
      if (url === "/api/participant/session")
        return Response.json({ signed_in: false, email: null });
      if (url === "/api/host/sites") return Response.json({ sites: [] });
      if (url === "/api/host/me") {
        return Response.json({
          email: "ann@example.com",
          custom_image: true,
          custom_voice: true,
        });
      }
      if (url === "/api/host/participant-policy") {
        if (method === "PUT") {
          if (s.refuse)
            return Response.json({ detail: s.refuse }, { status: 400 });
          s.policy = JSON.parse(body) as ParticipantPolicy;
        } else if (s.readFails) {
          return Response.json({ detail: "no" }, { status: 503 });
        }
        return Response.json({
          sites: SITES,
          participants: [PAT, "sam@example.com"],
          policy: s.policy,
        });
      }
      return new Response("", { status: 404 });
    }),
  );
  return s;
}

function panel(): HTMLElement {
  return screen
    .getByRole("heading", { name: "Where participants may go" })
    .closest("form") as HTMLElement;
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

test("every site is open by default, and a rule for every participant is saved", async () => {
  const s = server();
  window.location.hash = "#/host/account";
  render(<App />);
  await screen.findByRole("heading", { name: "Where participants may go" });
  const every = within(panel()).getByRole("group", { name: "Every participant" });
  const boxes = within(every).getAllByRole("checkbox") as HTMLInputElement[];
  expect(boxes.map((b) => b.checked)).toEqual([true, true]);
  // Only b: the landing choice offers only b.
  fireEvent.change(within(every).getByRole("checkbox", { name: "a.me0.ai" }), {
    target: { checked: false },
  });
  const landing = within(every).getByLabelText("Sent to after signing in");
  expect(
    within(landing).getAllByRole("option").map((o) => o.textContent),
  ).toEqual(["The first site they may open", "b.me0.ai"]);
  fireEvent.change(landing, { target: { value: "b" } });
  await act(async () => {
    fireEvent.click(within(panel()).getByRole("button", { name: "Save" }));
  });
  await waitFor(() =>
    expect(s.policy).toEqual({
      every: { sites: ["b"], landing: "b" },
      participants: {},
    }),
  );
  expect((await screen.findByRole("status")).textContent).toMatch(
    /next time a participant signs in/,
  );
});

test("one participant gets a rule of their own, and can go back to every participant's", async () => {
  const s = server({
    policy: { every: { sites: ["b"], landing: null }, participants: {} },
  });
  window.location.hash = "#/host/account";
  render(<App />);
  await screen.findByRole("heading", { name: "Where participants may go" });
  fireEvent.change(within(panel()).getByLabelText("A participant"), {
    target: { value: PAT },
  });
  fireEvent.click(
    within(panel()).getByRole("button", { name: "Give them a rule of their own" }),
  );
  const own = within(panel()).getByRole("group", { name: PAT });
  // It starts as every participant's rule; ticking a as well opens every site.
  fireEvent.change(within(own).getByRole("checkbox", { name: "a.me0.ai" }), {
    target: { checked: true },
  });
  fireEvent.change(within(own).getByLabelText("Sent to after signing in"), {
    target: { value: "a" },
  });
  await act(async () => {
    fireEvent.click(within(panel()).getByRole("button", { name: "Save" }));
  });
  await waitFor(() =>
    expect(s.policy.participants).toEqual({
      [PAT]: { sites: null, landing: "a" },
    }),
  );
  fireEvent.click(
    within(panel()).getByRole("button", {
      name: "Use the rule for every participant",
    }),
  );
  expect(within(panel()).queryByRole("group", { name: PAT })).toBeNull();
  // Unticking the landing site leaves "the first site" in its place.
  const every = within(panel()).getByRole("group", { name: "Every participant" });
  fireEvent.change(within(every).getByLabelText("Sent to after signing in"), {
    target: { value: "b" },
  });
  fireEvent.change(within(every).getByRole("checkbox", { name: "a.me0.ai" }), {
    target: { checked: true },
  });
  fireEvent.change(within(every).getByRole("checkbox", { name: "b.me0.ai" }), {
    target: { checked: false },
  });
  expect(
    (within(every).getByLabelText("Sent to after signing in") as HTMLSelectElement)
      .value,
  ).toBe("");
});

test("a rule the server refuses says why", async () => {
  server({ refuse: "Allow at least one site." });
  window.location.hash = "#/host/account";
  render(<App />);
  await screen.findByRole("heading", { name: "Where participants may go" });
  await act(async () => {
    fireEvent.click(within(panel()).getByRole("button", { name: "Save" }));
  });
  expect((await screen.findByRole("alert")).textContent).toBe(
    "Allow at least one site.",
  );
});

test("a policy that can't be read says so", async () => {
  server({ readFails: true });
  window.location.hash = "#/host/account";
  render(<App />);
  expect(
    await screen.findByText("Where participants may go can't be read just now."),
  ).toBeTruthy();
});

test("signing in goes to the site the host sends them to", async () => {
  const went = vi.spyOn(reloading, "goTo").mockImplementation(() => {});
  const reloaded = vi.spyOn(reloading, "reload").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "participant" });
      if (url === "/api/settings/access")
        return Response.json({ shown: false, as: null });
      if (url === "/api/host/session")
        return Response.json({ signed_in: false, email: null });
      if (url === "/api/participant/session")
        return Response.json({ signed_in: false, email: null });
      if (url === "/api/host/sign-in")
        return Response.json({ detail: "Wrong." }, { status: 401 });
      if (url === "/api/participant/sign-in") {
        return Response.json({
          signed_in: true,
          email: PAT,
          go_to: "https://b.me0.ai/",
        });
      }
      if (url === "/api/participant/progress") return Response.json({});
      return new Response("", { status: 404 });
    }),
  );
  window.location.hash = "#/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Sign in" });
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: PAT } });
  fireEvent.input(screen.getByLabelText(/^Password$/), {
    target: { value: "a long secret" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  });
  await waitFor(() => expect(went).toHaveBeenCalledWith("https://b.me0.ai/"));
  expect(reloaded).not.toHaveBeenCalled();
});
