import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CONFIRM_CLEAR, VideoAndChat } from "./video-and-chat";

const AGAIN = "/api/prepare/clips/sample/again";

// A server that answers Run the video test again and Clear conversation with these responses.
function server(
  again: () => Response,
  clear: () => Response = () => Response.json({ cleared: 4 }),
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === AGAIN && init?.method === "POST") return again();
    if (url === "/api/chat" && init?.method === "DELETE") return clear();
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function click(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
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

// Clicks Clear conversation, then Yes in the box that asks first.
async function clearConfirmed() {
  await click("Clear conversation");
  await click("Yes, clear it");
}

test("Run the video test again makes the sample again and plays it", async () => {
  // Answered by the test, so it can see the page while the video is made.
  let answer: (r: Response) => void = () => {};
  const fetchMock = vi.fn(
    (url: string) =>
      new Promise<Response>((resolve) => {
        if (url === AGAIN) answer = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<VideoAndChat />);
  expect(screen.queryByLabelText("Sample video")).toBeNull();
  await click("Run the video test again");
  expect(screen.getByText(/Making the sample video/)).toBeTruthy();
  expect(
    (
      screen.getByRole("button", {
        name: "Run the video test again",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  await act(async () => answer(Response.json({ video: "/api/prepare/clips/sample", seconds: 90 })));
  const video = (await screen.findByLabelText("Sample video")) as HTMLVideoElement;
  expect(video.getAttribute("src")).toMatch(/^\/api\/prepare\/clips\/sample\?made=\d+$/);
  expect(video.autoplay).toBe(true);
  expect(screen.queryByText(/Making the sample video/)).toBeNull();
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Video test run again \(\d+ ms\)$/),
  );
});

test("Run the video test again says why when it can't", async () => {
  const detail = "There is no sample video yet. Prepare it in setup first.";
  server(() => Response.json({ detail }, { status: 409 }));
  render(<VideoAndChat />);
  await click("Run the video test again");
  expect(await screen.findByText(detail)).toBeTruthy();
  expect(screen.queryByLabelText("Sample video")).toBeNull();
  expect(console.error).toHaveBeenCalledWith(
    "Could not run the video test again",
    expect.anything(),
  );
});

test("Run the video test again has a plain message when the server gives no reason", async () => {
  server(() => {
    throw new TypeError("Failed to fetch");
  });
  render(<VideoAndChat />);
  await click("Run the video test again");
  expect(await screen.findByText("The video could not be made. Try again.")).toBeTruthy();
});

test("Clear conversation asks first in the app's own box and clears only once confirmed", async () => {
  const fetchMock = server(() => new Response());
  const confirm = vi.spyOn(window, "confirm");
  render(<VideoAndChat />);
  await click("Clear conversation");
  const dialog = screen.getByRole("alertdialog", { name: CONFIRM_CLEAR });
  expect(dialog.textContent).toContain("This can't be undone.");
  await click("No, keep it");
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.queryByText("The conversation was cleared.")).toBeNull();
  expect(console.info).toHaveBeenCalledWith("Clear conversation cancelled");

  await clearConfirmed();
  expect(confirm).not.toHaveBeenCalled(); // not the browser's box
  expect(fetchMock).toHaveBeenCalledWith("/api/chat", { method: "DELETE" });
  expect(await screen.findByText("The conversation was cleared.")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Conversation cleared: 4 turn\(s\) \(\d+ ms\)$/),
  );
});

test("Clear conversation says when it fails", async () => {
  server(
    () => new Response(),
    () => new Response("", { status: 500 }),
  );
  render(<VideoAndChat />);
  await clearConfirmed();
  expect(await screen.findByText("That didn't work. Please try again.")).toBeTruthy();
  expect(screen.queryByText("The conversation was cleared.")).toBeNull();
  expect(console.error).toHaveBeenCalledWith("Could not clear the conversation", expect.anything());
});

test("Clear conversation has a plain message when the server can't be reached", async () => {
  server(
    () => new Response(),
    () => {
      throw new TypeError("Failed to fetch");
    },
  );
  render(<VideoAndChat />);
  await clearConfirmed();
  expect(await screen.findByText("The conversation could not be cleared. Try again.")).toBeTruthy();
});
