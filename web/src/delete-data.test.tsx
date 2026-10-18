import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CONFIRM_DELETE, DeleteData } from "./delete-data";

// A server that answers Delete my data with this response.
function server(answer: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/data" && init?.method === "DELETE") return answer();
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function clickDelete() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Delete my data" }));
  });
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  window.location.hash = "#/settings";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("Delete my data asks first, deletes, then opens setup at its start", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const fetchMock = server(() => Response.json({ files: 12, bytes: 4096, left: [] }));
  render(<DeleteData />);
  await clickDelete();
  expect(confirm).toHaveBeenCalledWith(CONFIRM_DELETE);
  expect(fetchMock).toHaveBeenCalledWith("/api/data", { method: "DELETE" });
  await vi.waitFor(() => expect(window.location.hash).toBe("#/consent"));
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Deleted my data: 12 file\(s\) \(\d+ ms\)$/),
  );
});

test("nothing is deleted when the confirmation is cancelled", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const fetchMock = server(() => Response.json({ files: 0, bytes: 0, left: [] }));
  render(<DeleteData />);
  await clickDelete();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(window.location.hash).toBe("#/settings");
  expect(console.info).toHaveBeenCalledWith("Delete my data cancelled");
});

test("while it deletes the button waits, and files left behind are reported", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  let answer: (r: Response) => void = () => {};
  server(() => new Promise<Response>((resolve) => (answer = resolve)));
  render(<DeleteData />);
  await clickDelete();
  expect(screen.getByText("Deleting…")).toBeTruthy();
  const button = screen.getByRole("button", {
    name: "Delete my data",
  }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  await act(async () =>
    answer(Response.json({ files: 3, bytes: 30, left: ["replies/idle/a.mp4"] })),
  );
  expect(await screen.findByText(/1 file\(s\) could not be deleted/)).toBeTruthy();
  expect(window.location.hash).toBe("#/settings");
  expect(button.disabled).toBe(false);
  expect(console.error).toHaveBeenCalledWith("Could not delete replies/idle/a.mp4");
});

test("the server's reason is shown when it refuses", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const detail = "Setup is preparing the video. Try again once it has finished.";
  server(() => Response.json({ detail }, { status: 409 }));
  render(<DeleteData />);
  await clickDelete();
  expect(await screen.findByText(detail)).toBeTruthy();
  expect(window.location.hash).toBe("#/settings");
});

test("a failure without a reason says to try again", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  server(() => {
    throw new TypeError("Failed to fetch");
  });
  render(<DeleteData />);
  await clickDelete();
  expect(await screen.findByText("Your data could not be deleted. Try again.")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not delete my data", expect.anything());
});
