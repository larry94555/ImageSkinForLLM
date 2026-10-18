import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DELETED, DeleteData } from "./delete-data";

// A server that answers Delete my data with this response.
function server(answer: () => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/data" && init?.method === "DELETE") return answer();
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

// Opens the confirmation and confirms it.
async function deleteEverything() {
  await click("Delete my data");
  await click("Yes, delete everything");
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

test("the confirmation asks if you are sure and says what is deleted", async () => {
  const fetchMock = server(() => Response.json({ files: 0, bytes: 0, left: [] }));
  render(<DeleteData />);
  expect(screen.queryByRole("alertdialog")).toBeNull();
  await click("Delete my data");
  const dialog = screen.getByRole("alertdialog", {
    name: "Are you sure you want to delete all your data?",
  });
  for (const item of DELETED) expect(dialog.textContent).toContain(item);
  expect(dialog.textContent).toContain("Your PDFs and settings are kept.");
  expect(dialog.textContent).toContain("This can't be undone.");
  // Backing out is the default: it has the focus.
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "No, keep my data" }));
  expect(fetchMock).not.toHaveBeenCalled();
});

test("Yes, delete everything deletes, then opens setup at its start", async () => {
  const fetchMock = server(() => Response.json({ files: 12, bytes: 4096, left: [] }));
  render(<DeleteData />);
  await deleteEverything();
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(fetchMock).toHaveBeenCalledWith("/api/data", { method: "DELETE" });
  await vi.waitFor(() => expect(window.location.hash).toBe("#/consent"));
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Deleted my data: 12 file\(s\) \(\d+ ms\)$/),
  );
});

test.each([
  [
    "No, keep my data",
    () => fireEvent.click(screen.getByRole("button", { name: "No, keep my data" })),
  ],
  ["Escape", () => fireEvent.keyDown(document, { key: "Escape" })],
  ["a click outside the box", () => fireEvent.click(document.querySelector(".confirm-backdrop")!)],
])("%s backs out and deletes nothing", async (_, backOut) => {
  const fetchMock = server(() => Response.json({ files: 0, bytes: 0, left: [] }));
  render(<DeleteData />);
  await click("Delete my data");
  await act(async () => {
    backOut();
  });
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
  expect(window.location.hash).toBe("#/settings");
  expect(console.info).toHaveBeenCalledWith("Delete my data cancelled");
});

test("a click inside the box keeps it open, and other keys do nothing", async () => {
  server(() => Response.json({ files: 0, bytes: 0, left: [] }));
  render(<DeleteData />);
  await click("Delete my data");
  await act(async () => {
    fireEvent.click(screen.getByRole("alertdialog"));
    fireEvent.keyDown(document, { key: "Enter" });
  });
  expect(screen.getByRole("alertdialog")).toBeTruthy();
});

test("while it deletes the button waits, and files left behind are reported", async () => {
  let answer: (r: Response) => void = () => {};
  server(() => new Promise<Response>((resolve) => (answer = resolve)));
  render(<DeleteData />);
  await deleteEverything();
  expect(screen.getByText("Deleting…")).toBeTruthy();
  const button = screen.getByRole("button", { name: "Delete my data" }) as HTMLButtonElement;
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
  const detail = "Setup is preparing the video. Try again once it has finished.";
  server(() => Response.json({ detail }, { status: 409 }));
  render(<DeleteData />);
  await deleteEverything();
  expect(await screen.findByText(detail)).toBeTruthy();
  expect(window.location.hash).toBe("#/settings");
});

test("a failure without a reason says to try again", async () => {
  server(() => {
    throw new TypeError("Failed to fetch");
  });
  render(<DeleteData />);
  await deleteEverything();
  expect(await screen.findByText("Your data could not be deleted. Try again.")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not delete my data", expect.anything());
});
