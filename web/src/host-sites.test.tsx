// Several sites for one host: the pages (roadmap R257). The top bar's switcher and the account
// page's list go to another of the host's sites, signed in there by a one-time link, and Add a
// site checks the subdomain as it is typed and goes to Stripe to pay for it.

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { navigation } from "./host";

vi.unmock("./api");

const ANN = { site: "ann", address: "https://ann.me0.ai", here: true };
const TWO = { site: "ann-two", address: "https://ann-two.me0.ai", here: false };
const OPEN = "https://ann-two.me0.ai/api/host/sign-in/once";
const STRIPE = "https://checkout.stripe.com/c/pay/cs_test";

interface Answers {
  sites?: object[];
  acting?: boolean;
  available?: boolean;
  add?: { status: number; body: object };
}

function server(answers: Answers = {}) {
  const asked: string[] = [];
  const sites = answers.sites ?? [ANN, TWO];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      asked.push(`${method} ${url} ${init?.body ?? ""}`.trim());
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({});
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: true,
          email: "ann@example.com",
          confirmed: true,
          ...(answers.acting ? { acting_as_admin: true } : {}),
        });
      }
      if (url === "/api/host/sites" && method === "GET") return Response.json({ sites });
      if (url === "/api/host/sites/ann-two/open") return Response.json({ site: "ann-two", go_to: OPEN });
      if (url === "/api/site/subscription") {
        return Response.json({ available: answers.available ?? true, price: "5 GB for $1.99 a month" });
      }
      if (url.startsWith("/api/site/subdomain/check")) {
        const name = new URL(url, "http://x").searchParams.get("name") ?? "";
        const problem = name === "taken" ? "taken is taken. Choose another name." : null;
        return Response.json({ name, problem });
      }
      if (url === "/api/host/sites" && method === "POST") {
        const add = answers.add ?? { status: 200, body: { site: "ann-three", url: STRIPE } };
        return Response.json(add.body, { status: add.status });
      }
      return new Response("", { status: 404 });
    }),
  );
  return asked;
}

let went: string[];

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  went = [];
  vi.spyOn(navigation, "goTo").mockImplementation((url: string) => void went.push(url));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

async function account() {
  window.location.hash = "#/host/account";
  render(<App />);
  await screen.findByRole("heading", { name: "Your sites" });
}

test("the top bar switches to another of the host's sites, signed in there", async () => {
  const asked = server();
  window.location.hash = "#/chat";
  render(<App />);
  const switcher = await screen.findByRole("combobox", { name: "Your sites" });
  expect([...switcher.querySelectorAll("option")].map((o) => o.textContent)).toEqual([
    "ann.me0.ai",
    "ann-two.me0.ai",
  ]);
  expect((switcher as HTMLSelectElement).value).toBe("ann");
  await act(async () => {
    fireEvent.change(switcher, { target: { value: "ann-two" } });
  });
  await waitFor(() => expect(went).toEqual([OPEN]));
  expect(asked).toContain("POST /api/host/sites/ann-two/open");
});

test("a host with one site has no switcher", async () => {
  server({ sites: [ANN] });
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("ann@example.com");
  await act(async () => {});
  expect(screen.queryByRole("combobox", { name: "Your sites" })).toBeNull();
});

test("the account page lists each site with its address and opens another", async () => {
  server({ sites: [ANN, { ...TWO, paused: true }] });
  await account();
  const items = screen.getAllByRole("listitem").map((li) => li.textContent);
  expect(items).toEqual(["ann.me0.ai · this site", "ann-two.me0.ai · pausedOpen"]);
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
  await waitFor(() => expect(went).toEqual([OPEN]));
});

test("Add a site checks the address as it is typed and goes to Stripe to pay for it", async () => {
  const asked = server();
  await account();
  expect(await screen.findByText(/It is 5 GB for \$1\.99 a month, paid on Stripe's secure page\./)).toBeTruthy();
  const add = screen.getByRole("button", { name: "Add and subscribe" });
  expect((add as HTMLButtonElement).disabled).toBe(true);
  const input = screen.getByLabelText("The new site's address");
  fireEvent.input(input, { target: { value: "taken" } });
  expect(await screen.findByText("taken is taken. Choose another name.")).toBeTruthy();
  expect((add as HTMLButtonElement).disabled).toBe(true);
  fireEvent.input(input, { target: { value: "ann-three" } });
  expect(await screen.findByText("ann-three is free.")).toBeTruthy();
  fireEvent.click(add);
  await waitFor(() => expect(went).toEqual([STRIPE]));
  expect(asked).toContain('POST /api/host/sites {"name":"ann-three"}');
});

test("a refused site says why and stays on the page", async () => {
  server({ add: { status: 409, body: { detail: "ann-three is taken. Choose another name." } } });
  await account();
  fireEvent.input(screen.getByLabelText("The new site's address"), { target: { value: "ann-three" } });
  await screen.findByText("ann-three is free.");
  fireEvent.click(screen.getByRole("button", { name: "Add and subscribe" }));
  expect((await screen.findByRole("alert")).textContent).toBe("ann-three is taken. Choose another name.");
  expect(went).toEqual([]);
});

test("the administrator acting as the host can't add a site, nor where subscribing isn't set up", async () => {
  server({ acting: true });
  await account();
  expect(await screen.findByText("Only the host adds a site, as it is paid for with their card.")).toBeTruthy();
  cleanup();
  server({ available: false });
  await account();
  expect(await screen.findByText("Adding a site needs subscribing, which isn't set up here.")).toBeTruthy();
  expect(screen.queryByLabelText("The new site's address")).toBeNull();
});
