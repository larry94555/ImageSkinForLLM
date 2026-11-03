// Subscribing (roadmap R67): Settings offers Subscribe where Stripe is set up, goes to Stripe's
// page, and shows the site as subscribed once Stripe's event has recorded it.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { go } from "./subscription";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const PRICE = "5 GB for $1.99 a month";

function server({
  subscribed = false,
  available = true,
  paused = false,
  subscribe = () => Response.json({ url: "https://checkout.stripe.com/c/pay/cs_1" }),
}: {
  subscribed?: boolean;
  available?: boolean;
  paused?: boolean;
  subscribe?: () => Response;
} = {}) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "host" });
      if (url === "/api/settings/access") return Response.json({ shown: true, as: "host" });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: true,
          email: "dan@example.com",
          confirmed: true,
          ...(subscribed ? { subscribed: true } : { trial: true }),
          ...(paused ? { paused: true } : {}),
        });
      }
      if (url === "/api/site/subscription") {
        return Response.json({
          available,
          price: PRICE,
          status: subscribed ? "active" : null,
          subscribed,
        });
      }
      if (url === "/api/site/subscribe") return subscribe();
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

test("Subscribe goes to Stripe's page, with the price said first", async () => {
  const asked = server({ paused: true });
  const went = vi.spyOn(go, "to").mockImplementation(() => {});
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Subscription" }));
  expect(section.getByText(/5 GB for \$1.99 a month, paid on Stripe's secure page/)).toBeTruthy();
  expect(section.getByText(/Subscribing brings your paused site back/)).toBeTruthy();
  fireEvent.click(section.getByRole("button", { name: "Subscribe" }));
  await vi.waitFor(() => expect(went).toHaveBeenCalledWith("https://checkout.stripe.com/c/pay/cs_1"));
  expect(asked).toContain("POST /api/site/subscribe");
  expect(console.info).toHaveBeenCalledWith("Subscribing: going to Stripe's page");
});

test("a subscribed site says so, with no Subscribe and no Cancel free trial", async () => {
  server({ subscribed: true });
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Subscription" }));
  expect(section.getByRole("status").textContent).toBe(`Subscribed: ${PRICE}.`);
  expect(section.queryByRole("button", { name: "Subscribe" })).toBeNull();
  expect(screen.queryByRole("region", { name: "Free trial" })).toBeNull();
});

test("a refusal says why, and nothing is offered where Stripe isn't set up", async () => {
  server({ subscribe: () => Response.json({ detail: "Stripe couldn't be reached just now." }, { status: 502 }) });
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Subscription" }));
  fireEvent.click(section.getByRole("button", { name: "Subscribe" }));
  expect(await section.findByText("Stripe couldn't be reached just now.")).toBeTruthy();
  expect((section.getByRole("button", { name: "Subscribe" }) as HTMLButtonElement).disabled).toBe(false);
  cleanup();
  server({ available: false });
  render(<App />);
  await screen.findByRole("region", { name: "Free trial" });
  expect(screen.queryByRole("region", { name: "Subscription" })).toBeNull();
});
