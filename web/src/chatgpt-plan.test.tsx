import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ChatGptStatus } from "./api";
import { ChatGptPlanSection } from "./chatgpt-plan";

const SIGNED_OUT: ChatGptStatus = {
  connected: false,
  email: "",
  name: "",
  plan_usage: false,
  registered_email: "",
  label: "",
  accounts: [],
};
const CONNECTED: ChatGptStatus = {
  connected: true,
  email: "larry@example.com",
  name: "Larry",
  plan_usage: true,
  registered_email: "larry@example.com",
  label: "larry@example.com",
  accounts: [],
};

// A fake server: GET /api/chatgpt answers `read`; signing out or switching answers `out`.
function server(read: ChatGptStatus | Response, out: ChatGptStatus | Response = SIGNED_OUT) {
  const fetchMock = vi.fn(async (url: string) => {
    const answer = url === "/api/chatgpt/sign-out" || url === "/api/chatgpt/use" ? out : read;
    return answer instanceof Response ? answer : Response.json(answer);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("signed out, it offers to continue with ChatGPT", async () => {
  server(SIGNED_OUT);
  render(<ChatGptPlanSection />);
  const link = await screen.findByRole("link", { name: "Continue with ChatGPT" });
  expect(link.getAttribute("href")).toBe("/api/chatgpt/sign-in");
  expect(console.info).toHaveBeenCalledWith("ChatGPT sign-in: not connected");
  expect(screen.queryByText(/Use another ChatGPT account/)).toBeNull();
});

test("after a disconnect, it signs in again as the registered account or another", async () => {
  server({ ...SIGNED_OUT, registered_email: "larry@example.com" });
  render(<ChatGptPlanSection />);
  expect(await screen.findByText(/Signs in again as larry@example.com/)).toBeTruthy();
  const another = screen.getByRole("link", { name: "Use another ChatGPT account" });
  expect(another.getAttribute("href")).toBe("/api/chatgpt/sign-in?another=true");
  expect(screen.queryByText(/Or sign in as/)).toBeNull();
});

test("accounts registered before can be signed in as again", async () => {
  server({
    ...SIGNED_OUT,
    registered_email: "larry@example.com",
    accounts: [
      { id: "app-1", email: "first@example.com", label: "", connected: false },
      { id: "app 2", email: "", label: "", connected: false },
    ],
  });
  render(<ChatGptPlanSection />);
  const first = await screen.findByRole("link", { name: "first@example.com" });
  expect(first.getAttribute("href")).toBe("/api/chatgpt/sign-in?account=app-1");
  const unnamed = screen.getByRole("link", { name: "an earlier account" });
  expect(unnamed.getAttribute("href")).toBe("/api/chatgpt/sign-in?account=app%202");
});

test("connected, it names the account and disconnects", async () => {
  const fetchMock = server(CONNECTED);
  render(<ChatGptPlanSection />);
  expect(await screen.findByText("larry@example.com")).toBeTruthy();
  expect(screen.queryByText(/wasn't allowed/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  await screen.findByRole("link", { name: "Continue with ChatGPT" });
  expect(fetchMock).toHaveBeenCalledWith("/api/chatgpt/sign-out", { method: "POST" });
  expect(screen.queryByText(/didn't confirm/)).toBeNull();
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Disconnected ChatGPT \(\d+ ms\)$/));
});

test("a sign-in that didn't allow the plan says how to allow it", async () => {
  server({ ...CONNECTED, email: "", label: "", plan_usage: false });
  render(<ChatGptPlanSection />);
  expect(await screen.findByText("Larry")).toBeTruthy();
  expect(screen.getByText(/Using your plan wasn't allowed/)).toBeTruthy();
  const allow = screen.getByRole("link", { name: "Allow use of my plan" });
  expect(allow.getAttribute("href")).toBe("/api/chatgpt/sign-in?consent=true");
});

test("a disconnect ChatGPT didn't confirm says how to finish it", async () => {
  server(CONNECTED, { ...SIGNED_OUT, registered_email: "larry@example.com", revoked: false });
  render(<ChatGptPlanSection />);
  fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toMatch(/didn't confirm it ended the sign-in/);
  expect(alert.textContent).toMatch(/ChatGPT settings/);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/not confirmed by ChatGPT\)$/));
});

test("a sign-in that can't be read, or a failed disconnect, says so", async () => {
  server(new Response("", { status: 500 }));
  render(<ChatGptPlanSection />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/could not be read/);
  cleanup();
  server(CONNECTED, new Response("", { status: 500 }));
  render(<ChatGptPlanSection />);
  fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/could not be disconnected/);
  expect(screen.getByRole("button", { name: "Disconnect" })).toBeTruthy();
});

test("a connected account switches to another one still connected, with no sign-in", async () => {
  const second = { id: "app-2", email: "b@example.com", label: "", connected: true };
  const fetchMock = server(
    { ...CONNECTED, accounts: [second] },
    {
      ...CONNECTED,
      email: "b@example.com",
      label: "b@example.com",
      accounts: [{ id: "app-1", email: "larry@example.com", label: "", connected: true }],
    },
  );
  const changed = vi.fn();
  window.addEventListener("chatgpt-account-changed", changed);
  render(<ChatGptPlanSection />);
  expect(await screen.findByText(/Other accounts:/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Switch to b@example.com" }));
  expect(await screen.findByText("b@example.com")).toBeTruthy();
  // The LLM setting is told, to read the new account's models (a review on PR #118).
  expect(changed).toHaveBeenCalledTimes(1);
  window.removeEventListener("chatgpt-account-changed", changed);
  expect(fetchMock).toHaveBeenCalledWith("/api/chatgpt/use", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: "app-2" }),
  });
  expect(screen.getByRole("button", { name: "Switch to larry@example.com" })).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Switched ChatGPT account (connected)");
});

test("a failed switch says so", async () => {
  server(
    { ...CONNECTED, accounts: [{ id: "app-2", email: "", label: "", connected: true }] },
    new Response("", { status: 500 }),
  );
  render(<ChatGptPlanSection />);
  fireEvent.click(await screen.findByRole("button", { name: "Switch to an earlier account" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/could not be switched/);
});

test("accounts that share an email are told apart by their labels", async () => {
  server({
    ...CONNECTED,
    label: "larry@example.com (2)",
    accounts: [
      { id: "app-1", email: "larry@example.com", label: "larry@example.com", connected: true },
      { id: "app-3", email: "larry@example.com", label: "larry@example.com (3)", connected: false },
    ],
  });
  render(<ChatGptPlanSection />);
  expect(await screen.findByText("larry@example.com (2)")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Switch to larry@example.com" })).toBeTruthy();
  const third = screen.getByRole("link", { name: "larry@example.com (3)" });
  expect(third.getAttribute("href")).toBe("/api/chatgpt/sign-in?account=app-3");
});
