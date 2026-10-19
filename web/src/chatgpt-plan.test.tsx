import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ChatGptStatus } from "./api";
import { ChatGptPlanSection } from "./chatgpt-plan";

const SIGNED_OUT: ChatGptStatus = { connected: false, email: "", name: "", plan_usage: false };
const CONNECTED: ChatGptStatus = {
  connected: true,
  email: "larry@example.com",
  name: "Larry",
  plan_usage: true,
};

// A fake server: GET /api/chatgpt answers `read`; signing out answers `out`.
function server(read: ChatGptStatus | Response, out: ChatGptStatus | Response = SIGNED_OUT) {
  const fetchMock = vi.fn(async (url: string) => {
    const answer = url === "/api/chatgpt/sign-out" ? out : read;
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
});

test("connected, it names the account and disconnects", async () => {
  const fetchMock = server(CONNECTED);
  render(<ChatGptPlanSection />);
  expect(await screen.findByText("larry@example.com")).toBeTruthy();
  expect(screen.queryByText(/wasn't allowed/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  await screen.findByRole("link", { name: "Continue with ChatGPT" });
  expect(fetchMock).toHaveBeenCalledWith("/api/chatgpt/sign-out", { method: "POST" });
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Disconnected ChatGPT \(\d+ ms\)$/));
});

test("a sign-in that didn't allow the plan says how to allow it", async () => {
  server({ ...CONNECTED, email: "", plan_usage: false });
  render(<ChatGptPlanSection />);
  expect(await screen.findByText("Larry")).toBeTruthy();
  expect(screen.getByText(/Using your plan wasn't allowed/)).toBeTruthy();
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
