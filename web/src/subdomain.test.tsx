// Picking the site's subdomain at the first payment (roadmap R63): Settings asks for it once the
// trial is paid for, checks it as it is typed, and goes to the site at its new address.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { go } from "./subscription";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const TAKEN = "a is taken. Choose another name.";

function server({
  pick = true,
  change = false,
  subscribed = true,
  picked = () =>
    Response.json({
      subdomain: "cy",
      address: "http://cy.localhost:8000",
      sign_in_at: "http://cy.localhost:8000/api/host/sign-in/abc",
    }),
}: { pick?: boolean; change?: boolean; subscribed?: boolean; picked?: () => Response } = {}) {
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}${init?.body ? ` ${String(init.body)}` : ""}`);
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "host" });
      if (url === "/api/settings/access") return Response.json({ shown: true, as: "host" });
      if (url === "/api/host/session") {
        return Response.json({ signed_in: true, email: "cy@example.com", confirmed: true, subscribed: true });
      }
      if (url === "/api/site/subscription") {
        return Response.json({
          available: subscribed,
          price: "5 GB for $1.99 a month",
          status: subscribed ? "active" : null,
          subscribed,
          subdomain: pick ? null : "cy",
          pick_subdomain: pick,
          change_subdomain: change,
        });
      }
      if (url.startsWith("/api/site/subdomain/check?")) {
        const name = new URLSearchParams(url.split("?")[1]).get("name") ?? "";
        const kept = name.trim().toLowerCase();
        return Response.json({ name: kept, problem: kept === "a" ? TAKEN : null });
      }
      if (url === "/api/site/subdomain") return picked();
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

async function picker() {
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Subscription" }));
  return within(await section.findByRole("form", { name: "Your site's address" }));
}

test("a taken name is refused as it is typed, and a free one is used", async () => {
  const asked = server();
  const went = vi.spyOn(go, "to").mockImplementation(() => {});
  const form = await picker();
  const input = form.getByLabelText("Pick your site's address");
  const use = form.getByRole("button", { name: "Use this address" }) as HTMLButtonElement;
  expect(use.disabled).toBe(true);
  fireEvent.input(input, { target: { value: "a" } });
  expect(await form.findByText(TAKEN)).toBeTruthy();
  expect(use.disabled).toBe(true);
  fireEvent.input(input, { target: { value: "Cy" } });
  expect(await form.findByText("cy is free.")).toBeTruthy();
  expect(use.disabled).toBe(false);
  fireEvent.click(use);
  await vi.waitFor(() =>
    expect(went).toHaveBeenCalledWith("http://cy.localhost:8000/api/host/sign-in/abc"),
  );
  expect(asked).toContain('POST /api/site/subdomain {"name":"Cy"}');
});

test("a refusal says why, and no picker once the site has its subdomain", async () => {
  server({ picked: () => Response.json({ detail: TAKEN }, { status: 409 }) });
  const went = vi.spyOn(go, "to").mockImplementation(() => {});
  const form = await picker();
  fireEvent.input(form.getByLabelText("Pick your site's address"), { target: { value: "cy" } });
  await form.findByText("cy is free.");
  fireEvent.click(form.getByRole("button", { name: "Use this address" }));
  expect(await form.findByText(TAKEN, { selector: ".error" })).toBeTruthy();
  expect(went).not.toHaveBeenCalled();
  cleanup();
  server({ pick: false });
  render(<App />);
  await screen.findByRole("region", { name: "Subscription" });
  expect(screen.queryByRole("form", { name: "Your site's address" })).toBeNull();
});

test("acting as the host, the browser goes to the address with no sign-in link", async () => {
  server({ picked: () => Response.json({ subdomain: "cy", address: "http://cy.localhost:8000" }) });
  const went = vi.spyOn(go, "to").mockImplementation(() => {});
  const form = await picker();
  fireEvent.input(form.getByLabelText("Pick your site's address"), { target: { value: "cy" } });
  await form.findByText("cy is free.");
  fireEvent.click(form.getByRole("button", { name: "Use this address" }));
  await vi.waitFor(() => expect(went).toHaveBeenCalledWith("http://cy.localhost:8000/"));
});

test("a site with its subdomain changes it, from Site address (R64)", async () => {
  const asked = server({
    pick: false,
    change: true,
    subscribed: false,
    picked: () =>
      Response.json({
        subdomain: "cy-two",
        address: "http://cy-two.localhost:8000",
        sign_in_at: "http://cy-two.localhost:8000/api/host/sign-in/xyz",
      }),
  });
  const went = vi.spyOn(go, "to").mockImplementation(() => {});
  window.location.hash = "#/settings";
  render(<App />);
  // A site added from the command line has no subscription, but has its address.
  const section = within(await screen.findByRole("region", { name: "Site address" }));
  expect(screen.queryByRole("region", { name: "Subscription" })).toBeNull();
  expect(section.getByText("cy").tagName).toBe("STRONG");
  expect(section.getByText(/cy then finds no site, and anyone can take it/)).toBeTruthy();
  const input = section.getByLabelText("Change your site's address");
  fireEvent.input(input, { target: { value: "cy-two" } });
  await section.findByText("cy-two is free.");
  fireEvent.click(section.getByRole("button", { name: "Change address" }));
  await vi.waitFor(() =>
    expect(went).toHaveBeenCalledWith("http://cy-two.localhost:8000/api/host/sign-in/xyz"),
  );
  expect(asked).toContain('POST /api/site/subdomain {"name":"cy-two"}');
  expect(console.info).toHaveBeenCalledWith(
    "Subdomain changed: going to the site's new address",
    "http://cy-two.localhost:8000",
  );
});
