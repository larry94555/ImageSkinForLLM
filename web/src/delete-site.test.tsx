// Deleting a site (roadmap R69a): Settings asks first, with the host's password, then says the
// site is deleted and the account kept; a wrong password or Stripe's refusal is said, and the
// main address has no Delete site.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

function server({
  deletable = true,
  refusal = null,
}: { deletable?: boolean; refusal?: { status: number; detail: string } | null } = {}) {
  const asked: string[] = [];
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
          available: false,
          price: "5 GB for $1.99 a month",
          status: null,
          subscribed: false,
          deletable,
        });
      }
      if (url === "/api/site/delete") {
        if (refusal) return Response.json({ detail: refusal.detail }, { status: refusal.status });
        return Response.json({ deleted: true });
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

test("Delete site asks first, with the password, then says the account is kept", async () => {
  const asked = server();
  const section = await panel();
  fireEvent.click(section.getByRole("button", { name: "Delete site" }));
  const dialog = within(await screen.findByRole("alertdialog"));
  expect(dialog.getByText("Are you sure you want to delete your site?")).toBeTruthy();
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
  expect((await section.findByRole("status")).textContent).toContain("Your account is kept");
  expect(asked).toContain('POST /api/site/delete {"password":"a long secret"}');
  expect(section.queryByRole("button", { name: "Delete site" })).toBeNull();
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
