// The administrator acting as a host (roadmap R44a, R44b): Act as this host in Host properties,
// the bar on the host's site with Stop acting, and the administrator's password on Change email.

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { navigation } from "./host";
import { HostProperties } from "./host-properties";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const BACK = "http://localhost:8000/#/admin/settings";

// The host's site, signed in as ann by the administrator acting as her. `state.acting` turns
// false when the administrator's sign-in ends.
function server() {
  const state = { acting: true, stopped: false, activity: 0 };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, string>) : {};
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/host/session") {
      return Response.json({
        signed_in: true,
        email: "ann@example.com",
        confirmed: true,
        acting_as_admin: true,
      });
    }
    if (url === "/api/host/act-as/stop") {
      state.stopped = true;
      return Response.json({ stopped: true, go_to: BACK });
    }
    if (url === "/api/host/act-as/activity") {
      state.activity += 1;
      return new Response(null, { status: state.acting ? 204 : 401 });
    }
    if (url === "/api/host/email") {
      return body.password === "admin secret"
        ? Response.json({ sent_to: body.new_email })
        : Response.json({ detail: "The password is wrong." }, { status: 401 });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, state };
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  window.location.hash = "";
});

function bar(): HTMLElement {
  return document.querySelector(".acting-bar") as HTMLElement;
}

test("every page says who the administrator acts as, and Stop acting goes back", async () => {
  const { state } = server();
  const goTo = vi.spyOn(navigation, "goTo").mockImplementation(() => {});
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("ann@example.com", { selector: ".acting-bar strong" });
  expect(bar().textContent).toContain("Acting as ann@example.com, as the administrator");
  expect(console.info).toHaveBeenCalledWith("Acting as host started");
  await act(async () => {
    fireEvent.click(within(bar()).getByRole("button", { name: "Stop acting" }));
  });
  await waitFor(() => expect(goTo).toHaveBeenCalledWith(BACK));
  expect(state.stopped).toBe(true);
  expect(state.activity).toBe(0); // the Stop acting click isn't activity
  expect(console.info).toHaveBeenCalledWith("Acting as host stopped");
});

test("a click is the administrator's activity once a minute, and acting ending says so", async () => {
  const { state } = server();
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("ann@example.com", { selector: ".acting-bar strong" });
  const now = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
  await act(async () => {
    fireEvent.click(document.body);
  });
  await act(async () => {
    fireEvent.click(document.body);
  });
  expect(state.activity).toBe(1);
  state.acting = false;
  now.mockReturnValue(1_000_000 + 61_000);
  await act(async () => {
    fireEvent.click(document.body);
  });
  await screen.findByText("Stopped acting as ann@example.com.");
  expect(state.activity).toBe(2);
});

test("Change email asks for the administrator's password while acting", async () => {
  server();
  window.location.hash = "#/host/account";
  render(<App />);
  await screen.findByRole("heading", { name: "Your account" });
  fireEvent.input(screen.getByLabelText(/^New email/), { target: { value: "ann2@example.com" } });
  fireEvent.input(screen.getByLabelText(/^Administrator password/), {
    target: { value: "admin secret" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send the link" }));
  });
  await screen.findByText(/We sent a link to ann2@example.com/);
});

test("a link that didn't work says why", async () => {
  server();
  window.location.hash = "#/host/act-as-failed";
  render(<App />);
  await screen.findByRole("heading", { name: "Couldn't act as this host" });
  expect(screen.getByRole("alert").textContent).toContain("already used");
});

test("Act as this host in Host properties asks first, then goes to the host's site", async () => {
  const link = "http://a.localhost:8000/api/host/act-as/the-link";
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/admin/hosts") return Response.json({ hosts: ["ann@example.com"] });
    if (url.startsWith("/api/admin/hosts/properties")) {
      return Response.json({
        custom_image: null,
        custom_voice: null,
        default: { custom_image: "allowed", custom_voice: "allowed" },
      });
    }
    if (url === "/api/admin/act-as") return Response.json({ link });
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const goTo = vi.spyOn(navigation, "goTo").mockImplementation(() => {});
  render(<HostProperties />);
  fireEvent.click(await screen.findByRole("button", { name: "ann@example.com" }));
  fireEvent.click(await screen.findByRole("button", { name: "Act as this host" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog.textContent).toContain("Act as ann@example.com?");
  fireEvent.click(within(dialog).getByRole("button", { name: "No, stay here" }));
  expect(fetchMock).not.toHaveBeenCalledWith("/api/admin/act-as", expect.anything());
  fireEvent.click(screen.getByRole("button", { name: "Act as this host" }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Yes, act as this host" }));
  });
  await waitFor(() => expect(goTo).toHaveBeenCalledWith(link));
  const asked = fetchMock.mock.calls.find(([u]) => u === "/api/admin/act-as") as unknown as [
    string,
    RequestInit,
  ];
  expect(JSON.parse(String(asked[1].body))).toEqual({ email: "ann@example.com" });
});

test("Act as this host refused says why", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/admin/hosts") return Response.json({ hosts: ["ann@example.com"] });
      if (url.startsWith("/api/admin/hosts/properties")) {
        return Response.json({
          custom_image: null,
          custom_voice: null,
          default: { custom_image: "allowed", custom_voice: "allowed" },
        });
      }
      return Response.json({ detail: "There is no host with that email address." }, { status: 404 });
    }),
  );
  render(<HostProperties />);
  fireEvent.click(await screen.findByRole("button", { name: "ann@example.com" }));
  fireEvent.click(await screen.findByRole("button", { name: "Act as this host" }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Yes, act as this host" }));
  });
  await screen.findByText("There is no host with that email address.");
});
