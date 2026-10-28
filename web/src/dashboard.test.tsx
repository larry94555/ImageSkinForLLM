import { act, cleanup, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { Resource, Resources } from "./api";
import { amount, REFRESH_MS } from "./dashboard";

const GB = 1000 ** 3;
const GIB = 1024 ** 3;
const THRESHOLDS = { blue_above: 60, orange_below: 30, red_below: 15 };

function entry(over: Partial<Resource> & Pick<Resource, "name">): Resource {
  return {
    unit: "bytes",
    available: 100 * GB,
    used: 50 * GB,
    remaining: 50 * GB,
    percent_remaining: 50,
    colour: "green",
    free_tier: 200 * GB,
    basis: "machine",
    details: {},
    ...over,
  };
}

// The hosted machine, as R152 and R153 read it.
function hosted(): Resources {
  return {
    read_at: "2026-10-26T20:00:00Z",
    thresholds: THRESHOLDS,
    resources: [
      entry({
        name: "cpu",
        unit: "cores",
        available: 4,
        used: 0.5,
        remaining: 3.5,
        percent_remaining: 87.5,
        colour: "blue",
        free_tier: 4,
        basis: "free tier",
        details: { load_1: 1.2, load_5: 0.8, load_15: 0.5, percent_now: 12 },
      }),
      entry({
        name: "memory",
        available: 23.4 * GIB,
        used: 17 * GIB,
        remaining: 6.4 * GIB,
        percent_remaining: 27.4,
        colour: "orange",
        free_tier: 24 * GIB,
        details: { app_used: 9 * GIB, app_cap: 14 * GIB },
      }),
      entry({
        name: "disk",
        available: 96 * GB,
        used: 86 * GB,
        remaining: 10 * GB,
        percent_remaining: 10.4,
        colour: "red",
        details: { path: "/data" },
      }),
      entry({
        name: "network",
        available: 10_000 * GB,
        used: 2_500 * GB,
        remaining: 7_500 * GB,
        percent_remaining: 75,
        colour: "blue",
        free_tier: 10_000 * GB,
        basis: "free tier",
        details: {
          month: "2026-10",
          sent: 2_500 * GB,
          received: 400 * GB,
          sent_per_s: 2_000_000,
          received_per_s: 500_000,
          projected_sent: 3_100 * GB,
          source: "machine",
        },
      }),
    ],
  };
}

// A server with an administrator signed in and the resources as `reading()` gives them.
function server(reading: () => Resources | number) {
  const state = { signedIn: true };
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/admin/session") {
      return Response.json({
        signed_in: state.signedIn,
        password_set: true,
        timeout_minutes: 30,
        ended: state.signedIn ? null : "inactive",
      });
    }
    if (url === "/api/admin/resources") {
      const read = reading();
      if (typeof read === "number") return Response.json({ detail: "No." }, { status: read });
      return Response.json(read);
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, state };
}

async function openDashboard() {
  window.location.hash = "#/admin";
  render(<App />);
  await screen.findByRole("heading", { name: "Resources" });
}

function card(name: string) {
  return within(screen.getByRole("region", { name }));
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("each resource shows available, used and remaining, with its colour named", async () => {
  server(hosted);
  await openDashboard();
  await screen.findByRole("region", { name: "CPU" });

  const cpu = card("CPU");
  expect(cpu.getByText("Blue · more than 60% left")).toBeTruthy();
  expect(cpu.getByText("Available").nextElementSibling?.textContent).toBe("4.00 cores");
  expect(cpu.getByText("Used").nextElementSibling?.textContent).toBe("0.50 cores");
  expect(cpu.getByText("Load over 1, 5 and 15 minutes: 1.2, 0.8, 0.5")).toBeTruthy();
  expect(cpu.getByText("Oracle's free tier limit.")).toBeTruthy();

  const memory = card("Memory");
  expect(memory.getByText("Orange · 15% to 30% left")).toBeTruthy();
  expect(memory.getByText("Remaining").nextElementSibling?.textContent).toBe("6.4 GB");
  expect(memory.getByText("This machine's own, less than the free tier's 24 GB.")).toBeTruthy();
  expect(memory.getByText("The app: 9.0 GB of its 14 GB cap")).toBeTruthy();
  expect(memory.getByRole("meter").getAttribute("aria-valuenow")).toBe("73");

  const disk = card("Disk");
  expect(disk.getByText("Red · less than 15% left")).toBeTruthy();
  expect(disk.getByText(/This disk's own size/).textContent).toContain("200 GB of disks in all");

  const network = card("Network this month");
  expect(network.getByText("Available").nextElementSibling?.textContent).toBe("10.00 TB");
  expect(network.getByText("Received: 400 GB (inbound is free)")).toBeTruthy();
  expect(network.getByText("Now: 2.0 MB/s out, 500 KB/s in")).toBeTruthy();
  expect(network.getByText("At this pace, about 3.10 TB out by the month's end")).toBeTruthy();

  const key = within(screen.getByRole("region", { name: "What the colours mean" }));
  expect(key.getAllByText(/\(.*left\)/).map((span) => span.parentElement?.textContent)).toEqual([
    "Blue (more than 60% left): More than enough. The site could take on more work, or reserve less.",
    "Green (30% to 60% left): Enough. No action needed.",
    "Orange (15% to 30% left): Getting close. Act now, before it runs out.",
    "Red (less than 15% left): Running out. Act at once: the site may slow down or fail.",
  ]);
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(
      /^Resources shown: \{"cpu":"blue","memory":"orange","disk":"red","network":"blue"\} \(\d+ ms\)$/,
    ),
  );
});

test("a figure that couldn't be read says so", async () => {
  server(() => ({
    ...hosted(),
    resources: [
      entry({
        name: "memory",
        available: null,
        used: null,
        remaining: null,
        percent_remaining: null,
        colour: "unknown",
      }),
    ],
  }));
  await openDashboard();
  await screen.findByRole("region", { name: "Memory" });
  const memory = card("Memory");
  expect(memory.getByText("Unknown · couldn't be read")).toBeTruthy();
  expect(memory.getByText("Available").nextElementSibling?.textContent).toBe("unknown");
  expect(memory.getByRole("meter").getAttribute("aria-valuenow")).toBe("0");
});

test("it reads again every 10 seconds and logs a colour that changes", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let reading = hosted();
  const { fetchMock } = server(() => reading);
  await openDashboard();
  await screen.findByRole("region", { name: "Disk" });
  const reads = () => fetchMock.mock.calls.filter(([u]) => u === "/api/admin/resources").length;
  const before = reads();

  reading = hosted();
  reading.resources[2] = { ...reading.resources[2], colour: "orange", percent_remaining: 20 };
  await act(async () => {
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
  });
  expect(reads()).toBe(before + 1);
  await card("Disk").findByText("Orange · 15% to 30% left");
  expect(console.info).toHaveBeenCalledWith("Resource colour changed: disk red to orange");
  // Reading is not activity: nothing was sent to keep the sign-in going.
  expect(fetchMock.mock.calls.some(([u]) => u === "/api/admin/activity")).toBe(false);
});

test("a read that fails says so and tries again", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let status: number | null = 500;
  server(() => status ?? hosted());
  await openDashboard();
  await screen.findByText("The resources could not be read. Trying again…");
  status = null;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
  });
  await screen.findByRole("region", { name: "CPU" });
  expect(screen.queryByText(/could not be read/)).toBeNull();
});

test("once signed out, the dashboard gives way to the sign-in", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let status: number | null = null;
  const { state } = server(() => status ?? hosted());
  await openDashboard();
  await screen.findByRole("region", { name: "CPU" });
  state.signedIn = false;
  status = 401;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(REFRESH_MS);
  });
  await screen.findByLabelText("Administrator password");
  expect(screen.queryByRole("heading", { name: "Resources" })).toBeNull();
  expect((await screen.findByRole("status")).textContent).toContain("without activity");
});

test("amounts are shown in cores, GB and TB", () => {
  const memory = entry({ name: "memory" });
  const disk = entry({ name: "disk" });
  const cpu = entry({ name: "cpu", unit: "cores" });
  expect(amount(cpu, 16)).toBe("16 cores");
  expect(amount(memory, 512 * 1024 ** 2)).toBe("512 MB");
  expect(amount(disk, 2_000_000)).toBe("2.0 MB");
  expect(amount(disk, 1_900)).toBe("2 KB");
  expect(amount(memory, 23.4 * GIB)).toBe("23 GB");
  expect(amount(disk, 2.5 * GB)).toBe("2.5 GB");
  expect(amount(disk, 1500 * GB)).toBe("1.50 TB");
  expect(amount(disk, null)).toBe("unknown");
});

test("the disk's Used is split into the LLM model and Other, with where the model is", async () => {
  const LOCATION = "/var/lib/docker/volumes/imageskin_llama-models/_data/models--unsloth--gemma-3-4b-it-GGUF";
  server(() => {
    const read = hosted();
    const disk = read.resources.find((r) => r.name === "disk")!;
    disk.details = {
      path: "/data",
      llm_model: "gemma-3-4b-it-Q4_0.gguf",
      llm_bytes: 2.4 * GB,
      llm_location: LOCATION,
      other_bytes: 83.6 * GB,
    };
    return read;
  });
  await openDashboard();
  const disk = within(await screen.findByRole("region", { name: "Disk" }));
  // To a tenth of a GB, so the two add up to Used as shown.
  expect(disk.getByText("Used").nextElementSibling?.textContent).toBe("86.0 GB");
  const model = disk.getByText("LLM model gemma-3-4b-it-Q4_0.gguf");
  expect(model.nextElementSibling?.textContent).toBe("2.4 GB");
  expect(disk.getByText("Other").nextElementSibling?.textContent).toBe("83.6 GB");
  expect(disk.getByText(`The LLM model: ${LOCATION}`)).toBeTruthy();
});

test("the parts shown add up to Used even when each rounds up on its own", async () => {
  // 2.46 + 1.46 = 3.92: rounded on their own the parts would show 2.5 + 1.5 = 4.0, not 3.9.
  server(() => {
    const read = hosted();
    const disk = read.resources.find((r) => r.name === "disk")!;
    disk.details = {
      path: "/data",
      llm_model: "gemma-3-4b-it-Q4_0.gguf",
      llm_bytes: 2.46 * GB,
      llm_location: "/models",
      other_bytes: 1.46 * GB,
    };
    return read;
  });
  await openDashboard();
  const disk = within(await screen.findByRole("region", { name: "Disk" }));
  expect(disk.getByText("Used").nextElementSibling?.textContent).toBe("3.9 GB");
  const model = disk.getByText("LLM model gemma-3-4b-it-Q4_0.gguf");
  expect(model.nextElementSibling?.textContent).toBe("2.5 GB");
  expect(disk.getByText("Other").nextElementSibling?.textContent).toBe("1.4 GB");
});

test("without a local LLM model the disk's Used is not split", async () => {
  server(hosted);
  await openDashboard();
  const disk = within(await screen.findByRole("region", { name: "Disk" }));
  expect(disk.queryByText("Other")).toBeNull();
  expect(disk.getByText("Used").nextElementSibling?.textContent).toBe("86 GB");
  expect(disk.queryByText(/LLM model/)).toBeNull();
});
