import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { GuidePage, loadGuide, STEPS } from "./guide";

beforeEach(() => {
  localStorage.clear();
  // jsdom has no scrolling; each step change scrolls the page to the top.
  vi.stubGlobal("scrollTo", vi.fn());
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const heading = () => screen.getByRole("heading", { level: 1 }).textContent;

test("the guide starts at the first step, with Back disabled", () => {
  render(<GuidePage />);
  expect(heading()).toBe("Before you begin");
  expect(screen.getByText(`Recording guide · Step 1 of ${STEPS.length}`)).toBeTruthy();
  expect((screen.getByRole("button", { name: "Back" }) as HTMLButtonElement).disabled).toBe(true);
});

test("Next and Back move through the steps and log each one", () => {
  render(<GuidePage />);
  fireEvent.click(screen.getByRole("button", { name: "Next: Get ready" }));
  expect(heading()).toBe("Get ready");
  expect(console.info).toHaveBeenCalledWith(`Guide step 2 of ${STEPS.length}: Get ready`);
  expect(window.scrollTo).toHaveBeenCalledWith({ top: 0 });
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(heading()).toBe("Before you begin");
});

test("every step can be shown, and the last one has no Next", () => {
  render(<GuidePage />);
  for (let i = 1; i < STEPS.length; i++) {
    fireEvent.click(screen.getByRole("button", { name: `Next: ${STEPS[i].title}` }));
    expect(heading()).toBe(STEPS[i].title);
  }
  expect(screen.queryByRole("button", { name: /^Next/ })).toBeNull();
});

test("the step list jumps straight to a step", () => {
  render(<GuidePage />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "6" } });
  expect(heading()).toBe("Recording 1 of 7");
  expect(screen.getByText("Hi, thanks for stopping by. It's good to see you.")).toBeTruthy();
});

test("before a laptop is picked, every laptop's steps are shown", () => {
  localStorage.setItem("imageskin.guide", JSON.stringify({ step: 5 }));
  render(<GuidePage />);
  expect(screen.getByText("Windows 10: the Voice Recorder app")).toBeTruthy();
  expect(screen.getByText("Windows 11: the Sound Recorder app")).toBeTruthy();
  expect(screen.getByText("Mac: the Voice Memos app")).toBeTruthy();
});

test("picking a laptop shows only its steps, and is remembered", () => {
  render(<GuidePage />);
  fireEvent.click(screen.getByRole("radio", { name: /Mac/ }));
  expect(console.info).toHaveBeenCalledWith("Guide laptop: mac");
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "3" } });
  expect(screen.getByText("Mac: the Photo Booth app")).toBeTruthy();
  expect(screen.queryByText("Windows 10 and Windows 11: the Camera app")).toBeNull();
  expect(loadGuide()).toEqual({ step: 3, laptop: "mac" });
});

test("Windows 11 shows the Sound Recorder steps only", () => {
  localStorage.setItem("imageskin.guide", JSON.stringify({ step: 5, laptop: "win11" }));
  render(<GuidePage />);
  expect(screen.getByText("Windows 11: the Sound Recorder app")).toBeTruthy();
  expect(screen.queryByText("Windows 10: the Voice Recorder app")).toBeNull();
  expect(screen.queryByText("Mac: the Voice Memos app")).toBeNull();
});

test("the guide reopens where it was left", () => {
  localStorage.setItem("imageskin.guide", JSON.stringify({ step: 9, laptop: "win10" }));
  render(<GuidePage />);
  expect(heading()).toBe("Recording 4 of 7");
});

test("the last but one step links to setup", () => {
  const add = STEPS.findIndex((s) => s.title === "Add your files to the app");
  localStorage.setItem("imageskin.guide", JSON.stringify({ step: add }));
  render(<GuidePage />);
  expect(screen.getByRole("link", { name: "Go to setup" }).getAttribute("href")).toBe("#/setup");
});

test("a broken or out of range saved place starts over safely", () => {
  localStorage.setItem("imageskin.guide", "{not json");
  expect(loadGuide()).toEqual({ step: 0, laptop: null });
  localStorage.setItem("imageskin.guide", JSON.stringify({ step: 99, laptop: "linux" }));
  expect(loadGuide()).toEqual({ step: STEPS.length - 1, laptop: null });
  localStorage.setItem("imageskin.guide", JSON.stringify({ step: -3 }));
  expect(loadGuide()).toEqual({ step: 0, laptop: null });
});

test("if the place can't be saved, the guide still works and logs why", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("full");
  });
  render(<GuidePage />);
  fireEvent.click(screen.getByRole("button", { name: "Next: Get ready" }));
  expect(heading()).toBe("Get ready");
  expect(console.error).toHaveBeenCalledWith("Could not save the guide's place", expect.any(Error));
});

test("every step has a clear way back to the Setup page, above and below", () => {
  render(<GuidePage />);
  const links = screen.getAllByRole("link", { name: "← Return to Setup page" });
  expect(links).toHaveLength(2);
  for (const link of links) expect(link.getAttribute("href")).toBe("#/setup");
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "9" } });
  expect(screen.getAllByRole("link", { name: "← Return to Setup page" })).toHaveLength(2);
});
