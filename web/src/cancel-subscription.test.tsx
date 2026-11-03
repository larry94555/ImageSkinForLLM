// Cancelling a subscription (roadmap R69): Settings asks first, says when the site pauses, can
// keep the subscription after all, and tells the host when a renewal failed.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { endDay } from "./subscription";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const ENDS = 1_796_000_000; // 2026-11-30

function server({
  endsAt = null,
  paymentFailed = false,
}: { endsAt?: number | null; paymentFailed?: boolean } = {}) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "host" });
      if (url === "/api/settings/access") return Response.json({ shown: true, as: "host" });
      if (url === "/api/host/session") {
        return Response.json({ signed_in: true, email: "dan@example.com", confirmed: true, subscribed: true });
      }
      if (url === "/api/site/subscription") {
        return Response.json({
          available: true,
          price: "5 GB for $1.99 a month",
          status: paymentFailed ? "past_due" : "active",
          subscribed: true,
          ends_at: endsAt,
          payment_failed: paymentFailed,
        });
      }
      if (url === "/api/site/subscription/cancel") return Response.json({ ends_at: ENDS });
      if (url === "/api/site/subscription/keep") return Response.json({ ends_at: null });
      return new Response("", { status: 404 });
    }),
  );
  return asked;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

async function subscription() {
  window.location.hash = "#/settings";
  render(<App />);
  return within(await screen.findByRole("region", { name: "Subscription" }));
}

test("Cancel asks first, then says when the site pauses, and Keep undoes it", async () => {
  const asked = server();
  const section = await subscription();
  fireEvent.click(section.getByRole("button", { name: "Cancel subscription" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  fireEvent.click(dialog.getByRole("button", { name: "No, keep it" }));
  expect(asked).not.toContain("POST /api/site/subscription/cancel");
  fireEvent.click(section.getByRole("button", { name: "Cancel subscription" }));
  fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Yes, cancel it" }));
  expect(
    await section.findByText(new RegExp(`keeps working until ${endDay(ENDS)}, then pauses`)),
  ).toBeTruthy();
  expect(asked).toContain("POST /api/site/subscription/cancel");
  fireEvent.click(section.getByRole("button", { name: "Keep my subscription" }));
  expect(await section.findByRole("button", { name: "Cancel subscription" })).toBeTruthy();
  expect(asked).toContain("POST /api/site/subscription/keep");
});

test("a cancelled subscription says when it ends, and a failed renewal is said", async () => {
  server({ endsAt: ENDS, paymentFailed: true });
  const section = await subscription();
  expect(section.getByText(new RegExp(`until ${endDay(ENDS)}`))).toBeTruthy();
  expect(section.getByRole("alert").textContent).toContain("Your last payment didn't go through.");
});
