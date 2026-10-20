import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/preact";
import { useState } from "preact/hooks";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ConfirmDialog, useConfirm } from "./confirm-dialog";

// A button that asks first, and shows the answer.
function Asker() {
  const { ask, dialog } = useConfirm();
  const [answer, setAnswer] = useState("none yet");
  async function go() {
    const yes = await ask({
      title: "Remove guide.pdf?",
      children: <p>Its wiki pages are removed too.</p>,
      keepLabel: "No, keep it",
      confirmLabel: "Yes, remove it",
    });
    setAnswer(yes ? "yes" : "no");
  }
  return (
    <div>
      <button type="button" onClick={go}>
        Remove
      </button>
      <p>Answer: {answer}</p>
      {dialog}
    </div>
  );
}

async function press(action: () => void) {
  await act(async () => {
    action();
  });
}

const button = (name: string) => screen.getByRole("button", { name });

beforeEach(() => {
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("nothing shows until something is asked", () => {
  render(<Asker />);
  expect(screen.queryByRole("alertdialog")).toBeNull();
});

test("the box has the question, what it means, and backing out has the focus", async () => {
  render(<Asker />);
  await press(() => fireEvent.click(button("Remove")));
  const dialog = screen.getByRole("alertdialog", { name: "Remove guide.pdf?" });
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(dialog.getAttribute("aria-describedby")).toBe("confirm-about");
  expect(dialog.textContent).toContain("Its wiki pages are removed too.");
  expect(document.activeElement).toBe(button("No, keep it"));
  expect(document.querySelector(".confirm-backdrop")).toBeTruthy();
});

test("Yes answers yes and closes the box", async () => {
  render(<Asker />);
  await press(() => fireEvent.click(button("Remove")));
  await press(() => fireEvent.click(button("Yes, remove it")));
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(screen.getByText("Answer: yes")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Remove guide.pdf? confirmed");
});

test.each([
  ["No", () => fireEvent.click(button("No, keep it"))],
  ["Escape", () => fireEvent.keyDown(document, { key: "Escape" })],
  [
    "a click outside the box",
    () => fireEvent.click(document.querySelector(".confirm-backdrop")!),
  ],
])("%s answers no and closes the box", async (_, backOut) => {
  render(<Asker />);
  await press(() => fireEvent.click(button("Remove")));
  await press(backOut);
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(screen.getByText("Answer: no")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Remove guide.pdf? cancelled");
});

test("a click inside the box keeps it open, and other keys do nothing", async () => {
  render(<Asker />);
  await press(() => fireEvent.click(button("Remove")));
  await press(() => {
    fireEvent.click(screen.getByRole("alertdialog"));
    fireEvent.keyDown(document, { key: "Enter" });
  });
  expect(screen.getByRole("alertdialog")).toBeTruthy();
  expect(screen.getByText("Answer: none yet")).toBeTruthy();
});

test("a page that re-renders doesn't move the focus back, and Escape still backs out", async () => {
  const first = vi.fn();
  const second = vi.fn();
  const view = render(
    <ConfirmDialog
      title="Sure?"
      keepLabel="No"
      confirmLabel="Yes"
      onCancel={first}
      onConfirm={vi.fn()}
    />,
  );
  button("Yes").focus();
  view.rerender(
    <ConfirmDialog
      title="Sure?"
      keepLabel="No"
      confirmLabel="Yes"
      onCancel={second}
      onConfirm={vi.fn()}
    />,
  );
  expect(document.activeElement).toBe(button("Yes"));
  fireEvent.keyDown(document, { key: "Escape" });
  expect(second).toHaveBeenCalledOnce();
  expect(first).not.toHaveBeenCalled();
});

test("a box with no details isn't described by an empty part", () => {
  render(
    <ConfirmDialog
      title="Sure?"
      keepLabel="No"
      confirmLabel="Yes"
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );
  expect(screen.getByRole("alertdialog").hasAttribute("aria-describedby")).toBe(
    false,
  );
  expect(document.getElementById("confirm-about")).toBeNull();
});

test("Escape stops backing out once the box is gone", () => {
  const onCancel = vi.fn();
  const view = render(
    <ConfirmDialog
      title="Sure?"
      keepLabel="No"
      confirmLabel="Yes"
      onCancel={onCancel}
      onConfirm={vi.fn()}
    />,
  );
  view.unmount();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(onCancel).not.toHaveBeenCalled();
});
