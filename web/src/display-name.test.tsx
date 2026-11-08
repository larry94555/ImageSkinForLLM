// The host's display name (roadmap R259): sign-up asks for it, the account page changes it, and
// participants and visitors see the host by it, never by their email.

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

vi.unmock("./api");

const EMAIL = "ann@example.com";

interface Server {
  host: boolean;
  view: "host" | "participant";
  name: string;
  asked: string[];
}

function server(host = false, view: Server["view"] = "host"): Server {
  const state: Server = { host, view, name: "Dr. Smith", asked: [] };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? init.body : "";
      state.asked.push(`${method} ${url} ${body}`.trim());
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") {
        return Response.json({ view: state.host ? state.view : "participant" });
      }
      if (url === "/api/settings/access") {
        return Response.json({
          shown: state.host,
          as: state.host ? "host" : null,
        });
      }
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: state.host,
          email: state.host ? EMAIL : null,
          host_name: state.name,
          ...(state.host ? { display_name: state.name, confirmed: true } : {}),
        });
      }
      if (url === "/api/host/sites") return Response.json({ sites: [] });
      if (url === "/api/host/me") {
        return Response.json({
          email: EMAIL,
          custom_image: true,
          custom_voice: true,
        });
      }
      if (url === "/api/host/sign-in" || url === "/api/participant/sign-in") {
        return Response.json({ detail: "Wrong." }, { status: 401 });
      }
      if (url === "/api/host/sign-up") {
        const sent = JSON.parse(body) as { display_name?: string };
        state.host = true;
        state.name = sent.display_name || "ann";
        return Response.json({
          signed_in: true,
          email: EMAIL,
          display_name: state.name,
        });
      }
      if (url === "/api/host/display-name") {
        const sent = JSON.parse(body) as { display_name: string };
        if (!sent.display_name.trim()) {
          return Response.json(
            { detail: "Enter a display name, such as Dr. Smith." },
            { status: 400 },
          );
        }
        state.name = sent.display_name.trim();
        return Response.json({ display_name: state.name });
      }
      return new Response("", { status: 404 });
    }),
  );
  return state;
}

function topBar(): HTMLElement {
  return document.querySelector("header") as HTMLElement;
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

test("a visitor sees the host by their display name, and their email nowhere", async () => {
  server();
  window.location.hash = "#/chat";
  render(<App />);
  expect(await within(topBar()).findByText("Dr. Smith")).toBeTruthy();
  expect(topBar().textContent).toContain("Hosted by Dr. Smith");
  expect(document.body.textContent).not.toContain(EMAIL);
});

test("the host's participant view names them as participants see it", async () => {
  server(true, "participant");
  window.location.hash = "#/chat";
  render(<App />);
  await waitFor(() =>
    expect(topBar().textContent).toContain("Hosted by Dr. Smith"),
  );
  // Their own link in the top bar is their display name too.
  expect(
    within(topBar()).getByRole("link", { name: "Dr. Smith" }),
  ).toBeTruthy();
  expect(topBar().textContent).not.toContain(EMAIL);
});

test("the host's own view has no Hosted by, and names them by their display name", async () => {
  server(true, "host");
  window.location.hash = "#/host/account";
  render(<App />);
  expect(
    await within(topBar()).findByRole("link", { name: "Dr. Smith" }),
  ).toBeTruthy();
  expect(topBar().textContent).not.toContain("Hosted by");
});

test("sign-up asks for a display name and sends it", async () => {
  const state = server();
  state.name = ""; // the main address: no host yet, so a new account is a host's (R269)
  window.location.hash = "#/host/sign-up";
  render(<App />);
  const name = await screen.findByLabelText(/^Display name/);
  // Typed before the email, it is kept: the email doesn't fill it in (R269).
  fireEvent.input(name, { target: { value: "Dr. Jones" } });
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: EMAIL } });
  fireEvent.blur(screen.getByLabelText("Email"));
  fireEvent.input(screen.getByLabelText(/^Password$/), {
    target: { value: "a long password" },
  });
  fireEvent.input(screen.getByLabelText(/^Password again/), {
    target: { value: "a long password" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  });
  await waitFor(() =>
    expect(state.asked.some((a) => a.startsWith("POST /api/host/sign-up"))).toBe(true),
  );
  const sent = state.asked.find((a) => a.startsWith("POST /api/host/sign-up"));
  expect(sent).toContain('"display_name":"Dr. Jones"');
  expect((name as HTMLInputElement).value).toBe("Dr. Jones");
  expect(
    await within(topBar()).findByRole("link", { name: "Dr. Jones" }),
  ).toBeTruthy();
});

test("the account page changes the display name, and the top bar says it at once", async () => {
  const state = server(true, "host");
  window.location.hash = "#/host/account";
  render(<App />);
  const field = (await screen.findByLabelText(
    "What participants and visitors see you called",
  )) as HTMLInputElement;
  await waitFor(() => expect(field.value).toBe("Dr. Smith"));
  const save = screen.getByRole("button", {
    name: "Save display name",
  }) as HTMLButtonElement;
  expect(save.disabled).toBe(true); // nothing changed yet
  await act(async () => {
    fireEvent.input(field, { target: { value: "Ann Smith, PhD" } });
  });
  await act(async () => {
    fireEvent.click(save);
  });
  expect(
    await screen.findByText(
      "Saved. Participants and visitors see you as Ann Smith, PhD.",
    ),
  ).toBeTruthy();
  expect(state.asked).toContain(
    'PUT /api/host/display-name {"display_name":"Ann Smith, PhD"}',
  );
  expect(
    within(topBar()).getByRole("link", { name: "Ann Smith, PhD" }),
  ).toBeTruthy();
});

test("a display name refused says why", async () => {
  server(true, "host");
  window.location.hash = "#/host/account";
  render(<App />);
  const field = (await screen.findByLabelText(
    "What participants and visitors see you called",
  )) as HTMLInputElement;
  await waitFor(() => expect(field.value).toBe("Dr. Smith"));
  await act(async () => {
    fireEvent.input(field, { target: { value: "Dr. " + "Smith".repeat(12) } });
  });
  vi.mocked(fetch).mockImplementationOnce(async () =>
    Response.json(
      { detail: "The display name can be at most 60 characters." },
      { status: 400 },
    ),
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Save display name" }));
  });
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "The display name can be at most 60 characters.",
  );
  expect(
    within(topBar()).getByRole("link", { name: "Dr. Smith" }),
  ).toBeTruthy();
});
