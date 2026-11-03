// Deleting a site (roadmap R69a): Settings asks first, with the host's password. Nothing paid for
// is taken away: a subscription is cancelled at the end of the month and the site pauses then; a
// site with nothing paid pauses now. Either way the content goes the admin settings' days after
// it pauses. A wrong password or Stripe's refusal is said, and the main address has no Delete site.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { daysLeft } from "./delete-site";
import { endDay } from "./subscription";

const DAY = 24 * 60 * 60;
// Seven days from now, as the server answers just after Delete site pauses a trial.
const DELETES = Math.round(Date.now() / 1000) + 7 * DAY;
// The end of the month paid for, for a subscribed site.
const ENDS = Math.round(Date.now() / 1000) + 20 * DAY;

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

function server({
  deletable = true,
  subscribed = false,
  refusal = null,
}: {
  deletable?: boolean;
  subscribed?: boolean;
  refusal?: { status: number; detail: string } | null;
} = {}) {
  const asked: string[] = [];
  let deleted = false;
  const answer = () =>
    subscribed ? { ends_at: ENDS, deletes_at: ENDS + 7 * DAY } : { ends_at: null, deletes_at: DELETES };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url} ${init?.body ?? ""}`.trim());
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "host" });
      if (url === "/api/settings/access") return Response.json({ shown: true, as: "host" });
      if (url === "/api/host/session") {
        return Response.json({ signed_in: true, email: "dan@example.com", confirmed: true });
      }
      if (url === "/api/site/subscription") {
        return Response.json({
          available: subscribed,
          price: "5 GB for $1.99 a month",
          status: subscribed ? "active" : null,
          subscribed,
          deletable,
          days_before_deleting: 7,
          ...(deleted ? answer() : { ends_at: null, deletes_at: null }),
        });
      }
      if (url === "/api/site/delete") {
        if (refusal) return Response.json({ detail: refusal.detail }, { status: refusal.status });
        deleted = true;
        return Response.json(answer());
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
  return within(await screen.findByRole("region", { name: "Delete site" }));
}

test("Delete site asks first, with the password, then says when the content goes", async () => {
  const asked = server();
  const section = await panel();
  // The days come from the admin settings.
  expect(section.getByText(/deleted 7 days later/)).toBeTruthy();
  fireEvent.click(section.getByRole("button", { name: "Delete site" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  expect(dialog.getByText("Are you sure you want to delete your site?")).toBeTruthy();
  expect(dialog.getByText(/Your site will be paused now. You will then have 7 days to subscribe/)).toBeTruthy();
  // Backing out deletes nothing.
  fireEvent.click(dialog.getByRole("button", { name: "No, keep my site" }));
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(asked.some((a) => a.startsWith("POST /api/site/delete"))).toBe(false);

  fireEvent.click(section.getByRole("button", { name: "Delete site" }));
  const again = within(await screen.findByRole("alertdialog"));
  fireEvent.input(again.getByLabelText("Your password, to confirm"), {
    target: { value: "a long secret" },
  });
  fireEvent.click(again.getByRole("button", { name: "Yes, delete it" }));
  const status = (await section.findByRole("status")).textContent;
  expect(status).toBe(
    "Your site has been paused. You will have 7 days to start it again before it gets deleted.",
  );
  expect(section.getByText(new RegExp(`deleted on ${endDay(DELETES)}`))).toBeTruthy();
  expect(asked).toContain('POST /api/site/delete {"password":"a long secret"}');
  expect(section.queryByRole("button", { name: "Delete site" })).toBeNull();
});

test("A subscribed site keeps its service to the end of the month, then 7 days", async () => {
  server({ subscribed: true });
  const section = await panel();
  expect(section.getByText(/you keep your site until the end of the month paid for/)).toBeTruthy();
  fireEvent.click(section.getByRole("button", { name: "Delete site" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  expect(
    dialog.getByText(
      "Your subscription is now cancelled. You will have service until the end of the month. " +
        "After that, your service will be paused. You will then have 7 days to renew your " +
        "subscription before the content is deleted.",
    ),
  ).toBeTruthy();
  fireEvent.input(dialog.getByLabelText("Your password, to confirm"), {
    target: { value: "a long secret" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Yes, delete it" }));
  const status = await section.findByText(/Your subscription is cancelled/);
  expect(status.textContent).toContain(`service until ${endDay(ENDS)}`);
  expect(status.textContent).toContain("7 days to renew your subscription");
  // The Subscription panel says it too, read again, with Keep my subscription.
  const subscription = within(await screen.findByRole("region", { name: "Subscription" }));
  expect(await subscription.findByRole("button", { name: "Keep my subscription" })).toBeTruthy();
});

test("A wrong password is said, and the site is kept", async () => {
  server({ refusal: { status: 401, detail: "The password is wrong." } });
  const section = await panel();
  fireEvent.click(section.getByRole("button", { name: "Delete site" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  fireEvent.click(dialog.getByRole("button", { name: "Yes, delete it" }));
  expect(await section.findByText("The password is wrong.")).toBeTruthy();
  expect(section.getByRole("button", { name: "Delete site" })).toBeTruthy();
});

test("A failed call that says nothing asks to try again", async () => {
  server();
  const section = await panel();
  vi.mocked(fetch).mockRejectedValueOnce(new TypeError("offline"));
  fireEvent.click(section.getByRole("button", { name: "Delete site" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  fireEvent.click(dialog.getByRole("button", { name: "Yes, delete it" }));
  expect(await section.findByText("The site could not be deleted. Try again.")).toBeTruthy();
});

test("The main address has no Delete site", async () => {
  server({ deletable: false });
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Settings" });
  await new Promise((r) => setTimeout(r, 50));
  expect(screen.queryByRole("region", { name: "Delete site" })).toBeNull();
});

test("The days left count down from the admin settings' days", () => {
  const day = 24 * 60 * 60;
  expect(daysLeft(1000 + 30 * day, 30, 1000)).toBe(30);
  expect(daysLeft(1000 + 30 * day, 30, 1000 + 1.5 * day)).toBe(29);
  expect(daysLeft(1000, 30, 1000 + day)).toBe(0);
});
