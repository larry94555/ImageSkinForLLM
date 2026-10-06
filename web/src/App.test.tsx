import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

function serverWithConsent(agreed: boolean, postOk = true) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return postOk
        ? Response.json({ agreed: true, agreed_at: "2026-10-06T20:00:00+00:00" })
        : new Response("", { status: 500 });
    }
    return Response.json({ agreed, agreed_at: agreed ? "2026-10-06T20:00:00+00:00" : null });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openAt(hash: string) {
  window.location.hash = hash;
  render(<App />);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("setup without consent goes to the consent page", async () => {
  serverWithConsent(false);
  await openAt("#/setup");
  expect(await screen.findByText("Before you start")).toBeTruthy();
  expect(window.location.hash).toBe("#/consent");
  expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(
    true,
  );
});

test("ticking the box and continuing saves consent and opens setup", async () => {
  const fetchMock = serverWithConsent(false);
  await openAt("#/consent");
  fireEvent.click(await screen.findByRole("checkbox"));
  const button = screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement;
  expect(button.disabled).toBe(false);
  await act(async () => fireEvent.click(button));
  expect(await screen.findByText("Thank you, consent is confirmed.")).toBeTruthy();
  expect(window.location.hash).toBe("#/setup");
  expect(fetchMock).toHaveBeenCalledWith("/api/consent", expect.objectContaining({ method: "POST" }));
});

test("a failed save shows a message and lets the user try again", async () => {
  serverWithConsent(false, false);
  await openAt("#/consent");
  fireEvent.click(await screen.findByRole("checkbox"));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Continue" })));
  expect(await screen.findByText("Could not save your answer. Please try again.")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
});

test("with consent, setup opens and the nav marks it", async () => {
  serverWithConsent(true);
  await openAt("#/setup");
  expect(await screen.findByText("Thank you, consent is confirmed.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Setup" }).className).toBe("current");
});

test("unknown pages say so", async () => {
  serverWithConsent(true);
  await openAt("#/nowhere");
  expect(await screen.findByText("Page not found")).toBeTruthy();
});

test("if the server can't be reached, setup stays blocked", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 503 })));
  await openAt("#/setup");
  expect(await screen.findByText("Before you start")).toBeTruthy();
});

test("home starts setup at consent until it is given", async () => {
  serverWithConsent(false);
  await openAt("#/");
  const start = await screen.findByRole("link", { name: "Start setup" });
  expect(start.getAttribute("href")).toBe("#/consent");
});
