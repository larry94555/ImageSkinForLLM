import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { useState } from "preact/hooks";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ConfirmDialog, useConfirm } from "./confirm-dialog";

// A button that asks first, and shows the answer, between other controls on the page.
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
      <button type="button">Before</button>
      <button type="button" onClick={go}>
        Remove
      </button>
      <button type="button" onClick={go}>
        Remove another
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

// Opens the box the way a person does: focus on Remove, then click it.
async function open() {
  render(<Asker />);
  button("Remove").focus();
  await press(() => fireEvent.click(button("Remove")));
}

// Tab or Shift+Tab, as the browser would move the focus unless the box stops it.
function tab(shift = false) {
  return fireEvent.keyDown(document.activeElement ?? document, { key: "Tab", shiftKey: shift });
}

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
  await open();
  const dialog = screen.getByRole("alertdialog", { name: "Remove guide.pdf?" });
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  const about = document.getElementById(dialog.getAttribute("aria-describedby")!);
  expect(about?.textContent).toBe("Its wiki pages are removed too.");
  expect(document.activeElement).toBe(button("No, keep it"));
  expect(document.querySelector(".confirm-backdrop")).toBeTruthy();
});

test("Yes answers yes, closes the box and gives the focus back to Remove", async () => {
  await open();
  await press(() => fireEvent.click(button("Yes, remove it")));
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(screen.getByText("Answer: yes")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Remove guide.pdf? confirmed");
  expect(document.activeElement).toBe(button("Remove"));
});

test.each([
  ["No", () => fireEvent.click(button("No, keep it"))],
  ["Escape", () => fireEvent.keyDown(document, { key: "Escape" })],
  ["a click outside the box", () => fireEvent.click(document.querySelector(".confirm-backdrop")!)],
])("%s answers no, closes the box and gives the focus back to Remove", async (_, backOut) => {
  await open();
  await press(backOut);
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(screen.getByText("Answer: no")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Remove guide.pdf? cancelled");
  expect(document.activeElement).toBe(button("Remove"));
});

test("a click inside the box keeps it open, and other keys do nothing", async () => {
  await open();
  await press(() => {
    fireEvent.click(screen.getByRole("alertdialog"));
    fireEvent.keyDown(document, { key: "Enter" });
  });
  expect(screen.getByRole("alertdialog")).toBeTruthy();
  expect(screen.getByText("Answer: none yet")).toBeTruthy();
});

test("Tab and Shift+Tab go round the box's own buttons, never to the page behind", async () => {
  await open();
  const no = button("No, keep it");
  const yes = button("Yes, remove it");
  // From No, Tab is left to the browser: Yes is next, inside the box.
  expect(tab()).toBe(true);
  yes.focus();
  expect(tab()).toBe(false); // the browser's move is stopped...
  expect(document.activeElement).toBe(no); // ...and the focus goes round to the first
  expect(tab(true)).toBe(false);
  expect(document.activeElement).toBe(yes);
  expect(tab(true)).toBe(true); // Shift+Tab from Yes back to No is the browser's own
});

test("focus that lands behind the box is brought back, so nothing there can be used", async () => {
  await open();
  await press(() => button("Remove another").focus());
  expect(document.activeElement).toBe(button("No, keep it"));
  await press(() => button("Before").focus());
  expect(document.activeElement).toBe(button("No, keep it"));
  // Tab from outside the box, if the focus is ever there, goes to the box.
  (document.activeElement as HTMLElement).blur();
  expect(tab()).toBe(false);
  expect(document.activeElement).toBe(button("No, keep it"));
  expect(tab(true)).toBe(false);
  expect(document.activeElement).toBe(button("Yes, remove it"));
  expect(screen.getAllByRole("alertdialog")).toHaveLength(1);
});

test("the focus isn't given back to a button that went with the answer", () => {
  const gone = document.createElement("button");
  document.body.append(gone);
  gone.focus();
  const view = render(
    <ConfirmDialog
      title="Sure?"
      keepLabel="No"
      confirmLabel="Yes"
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );
  gone.remove();
  view.unmount();
  expect(document.activeElement).toBe(document.body);
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

test("each box has its own ids, and one with no details isn't described by an empty part", () => {
  render(
    <>
      <ConfirmDialog
        title="One?"
        keepLabel="No"
        confirmLabel="Yes"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />
      <ConfirmDialog
        title="Two?"
        keepLabel="No"
        confirmLabel="Yes"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      >
        <p>Details</p>
      </ConfirmDialog>
    </>,
  );
  const [one, two] = screen.getAllByRole("alertdialog");
  expect(one.getAttribute("aria-labelledby")).not.toBe(two.getAttribute("aria-labelledby"));
  expect(one.hasAttribute("aria-describedby")).toBe(false);
  expect(screen.getByRole("alertdialog", { name: "Two?" })).toBe(two);
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
