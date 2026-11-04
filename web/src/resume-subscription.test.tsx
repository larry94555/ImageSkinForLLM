// Resuming a cancelled subscription (roadmap R69b): a host whose site paused sees a bar on every
// page, and in Settings Resume subscription, which asks first, saying the price, then brings the
// site back with the card Stripe keeps, or opens Stripe's page when a card is needed.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { go } from "./subscription";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

function server({
  resumable = true,
  answer = { resumed: true } as object,
  status = 200,
}: { resumable?: boolean; answer?: object; status?: number } = {}) {
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
          paused: true,
        });
      }
      if (url === "/api/site/subscription") {
        return Response.json({
          available: true,
          price: "5 GB for $1.99 a month",
          status: "canceled",
          subscribed: false,
          deletable: true,
          days_before_deleting: 30,
          deletes_at: null,
          resumable,
        });
      }
      if (url === "/api/site/subscription/resume") {
        return Response.json(answer, { status });
      }
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

async function panel() {
  window.location.hash = "#/settings";
  render(<App />);
  return within(await screen.findByRole("region", { name: "Subscription" }));
}

async function confirm(section: ReturnType<typeof within>) {
  fireEvent.click(await section.findByRole("button", { name: "Resume subscription" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  expect(
    dialog.getByText(/Your subscription, 5 GB for \$1.99 a month, starts again now/),
  ).toBeTruthy();
  fireEvent.click(dialog.getByRole("button", { name: "Yes, resume it" }));
}

test("Resume subscription asks first, then brings the site back with the card on file", async () => {
  const asked = server();
  const reload = vi.spyOn(go, "reload").mockImplementation(() => {});
  const section = await panel();
  expect(section.getByText(/Your site is paused/)).toBeTruthy();
  expect(section.getByText(/with the card Stripe keeps for you/)).toBeTruthy();
  // Backing out asks Stripe nothing.
  fireEvent.click(section.getByRole("button", { name: "Resume subscription" }));
  fireEvent.click(
    within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Not now" }),
  );
  expect(asked).not.toContain("POST /api/site/subscription/resume");

  await confirm(section);
  await vi.waitFor(() => expect(reload).toHaveBeenCalled());
  expect(asked).toContain("POST /api/site/subscription/resume");
});

test("When Stripe needs a card, its page is opened", async () => {
  server({ answer: { resumed: false, url: "https://checkout.stripe.com/c/pay/cs_1" } });
  const to = vi.spyOn(go, "to").mockImplementation(() => {});
  await confirm(await panel());
  await vi.waitFor(() => expect(to).toHaveBeenCalledWith("https://checkout.stripe.com/c/pay/cs_1"));
});

test("A refusal is said, and the button comes back", async () => {
  server({ answer: { detail: "Stripe couldn't be reached just now." }, status: 502 });
  const section = await panel();
  await confirm(section);
  expect(await section.findByText("Stripe couldn't be reached just now.")).toBeTruthy();
  expect(
    (section.getByRole("button", { name: "Resume subscription" }) as HTMLButtonElement).disabled,
  ).toBe(false);
});

test("A failed call that says nothing asks to try again", async () => {
  server();
  const section = await panel();
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
  await confirm(section);
  expect(await section.findByText("Resuming didn't work. Try again.")).toBeTruthy();
});

test("A site never paid for subscribes as before", async () => {
  server({ resumable: false });
  const section = await panel();
  expect(await section.findByRole("button", { name: "Subscribe" })).toBeTruthy();
  expect(section.queryByRole("button", { name: "Resume subscription" })).toBeNull();
});

test("Every page but Settings shows the paused bar, with Resume subscription", async () => {
  server();
  window.location.hash = "#/content";
  render(<App />);
  const bar = await screen.findByText(/Your site is paused: visitors see that it is paused/);
  const link = within(bar).getByRole("link", { name: "Resume subscription" });
  expect(link.getAttribute("href")).toBe("#/settings");
});
