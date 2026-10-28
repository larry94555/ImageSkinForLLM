// The admin view's resource dashboard (roadmap R154, item 124): CPU, memory, disk and this
// month's network, each with what is available, used and remaining, the remaining amount in its
// colour and the colour's name, so it never relies on colour alone. It is read every 10 seconds
// while open; that is not activity, so it doesn't keep the administrator signed in (R150).

import { Fragment } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

import { useAdmin } from "./admin";
import {
  getResources,
  type Resource,
  type ResourceColour,
  type Resources,
  ServerRefusal,
  type Thresholds,
} from "./api";

export const REFRESH_MS = 10_000;

const TITLES: Record<Resource["name"], string> = {
  cpu: "CPU",
  memory: "Memory",
  disk: "Disk",
  network: "Network this month",
};

// What each colour means and what to do, in the order shown under the cards.
export const MEANINGS: [ResourceColour, string, string][] = [
  ["blue", "More than enough", "The site could take on more work, or reserve less."],
  ["green", "Enough", "No action needed."],
  ["orange", "Getting close", "Act now, before it runs out."],
  ["red", "Running out", "Act at once: the site may slow down or fail."],
];

const NAMES: Record<ResourceColour, string> = {
  blue: "Blue",
  green: "Green",
  orange: "Orange",
  red: "Red",
  unknown: "Unknown",
};

const GB = 1000 ** 3;
const GIB = 1024 ** 3;

// Memory in GB as the operating system counts it (1024³), disk and network as Oracle does (1000³).
export function amount(resource: Resource, value: number | null | undefined): string {
  if (value === null || value === undefined) return "unknown";
  if (resource.unit === "cores") return `${value.toFixed(value >= 10 ? 0 : 2)} cores`;
  const binary = resource.name === "memory";
  const gb = value / (binary ? GIB : GB);
  if (gb >= 1000) return `${(gb / 1000).toFixed(2)} TB`;
  if (gb >= 10) return `${gb.toFixed(0)} GB`;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = value / (binary ? 1024 ** 2 : 1000 ** 2);
  if (mb >= 1) return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
  return `${Math.round(value / (binary ? 1024 : 1000))} KB`;
}

function rangeOf(colour: ResourceColour, t: Thresholds): string {
  return {
    blue: `more than ${t.blue_above}% left`,
    green: `${t.orange_below}% to ${t.blue_above}% left`,
    orange: `${t.red_below}% to ${t.orange_below}% left`,
    red: `less than ${t.red_below}% left`,
    unknown: "",
  }[colour];
}

// Where `available` comes from, in a line.
function basisLine(resource: Resource): string {
  const limit = amount(resource, resource.free_tier);
  if (resource.name === "disk") {
    return `This disk's own size. Oracle's free tier allows ${limit} of disks in all.`;
  }
  if (resource.name === "network") return `Oracle's free tier allows ${limit} out each month.`;
  if (resource.basis === "machine") {
    return `This machine's own, less than the free tier's ${limit}.`;
  }
  return `Oracle's free tier limit.`;
}

function detailLines(resource: Resource): string[] {
  const d = resource.details;
  const bytes = (v: unknown) => amount({ ...resource, unit: "bytes" }, v as number);
  if (resource.name === "cpu" && d.load_15 !== undefined) {
    return [`Load over 1, 5 and 15 minutes: ${d.load_1}, ${d.load_5}, ${d.load_15}`];
  }
  if (resource.name === "memory" && typeof d.app_cap === "number") {
    return [`The app: ${bytes(d.app_used)} of its ${bytes(d.app_cap)} cap`];
  }
  if (resource.name === "disk" && typeof d.llm_location === "string") {
    return [`The LLM model: ${d.llm_location}`];
  }
  if (resource.name === "network" && d.month !== undefined) {
    const lines = [
      `Received: ${bytes(d.received)} (inbound is free)`,
      `Now: ${bytes(d.sent_per_s)}/s out, ${bytes(d.received_per_s)}/s in`,
    ];
    if (typeof d.projected_sent === "number") {
      lines.push(`At this pace, about ${bytes(d.projected_sent)} out by the month's end`);
    }
    return lines;
  }
  return [];
}

// The disk's Used split into the local LLM's model file and Other, which add up to it (R175).
// To a tenth of a GB, so the two parts shown add up to the Used shown.
function usedBy(resource: Resource): [string, string][] {
  const d = resource.details;
  if (resource.name !== "disk" || typeof d.llm_bytes !== "number") return [];
  return [
    [`LLM model ${d.llm_model}`, tenths(d.llm_bytes)],
    ["Other", tenths(Number(d.other_bytes))],
  ];
}

function tenths(bytes: number): string {
  return `${(bytes / GB).toFixed(1)} GB`;
}

function usedShown(resource: Resource): string {
  if (usedBy(resource).length === 0) return amount(resource, resource.used);
  return tenths(Number(resource.details.llm_bytes) + Number(resource.details.other_bytes));
}

function Card({ resource, thresholds }: { resource: Resource; thresholds: Thresholds }) {
  const known = resource.colour !== "unknown";
  const usedShare =
    known && resource.available ? (100 * (resource.used ?? 0)) / resource.available : 0;
  const name = TITLES[resource.name];
  return (
    <section className={`panel resource ${resource.colour}`} aria-labelledby={`resource-${resource.name}`}>
      <h2 id={`resource-${resource.name}`}>{name}</h2>
      <p className="remaining">
        <span className="big">{amount(resource, resource.remaining)}</span> remaining
        {known && <span className="muted"> · {resource.percent_remaining}%</span>}
      </p>
      <p className={`colour-name ${resource.colour}`}>
        {NAMES[resource.colour]}
        {known ? ` · ${rangeOf(resource.colour, thresholds)}` : " · couldn't be read"}
      </p>
      <div
        className="bar"
        role="meter"
        aria-label={`${name} used`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(usedShare)}
      >
        <span style={{ width: `${Math.min(usedShare, 100)}%` }} />
      </div>
      <dl>
        <dt>Available</dt>
        <dd>{amount(resource, resource.available)}</dd>
        <dt>Used</dt>
        <dd>{usedShown(resource)}</dd>
        {usedBy(resource).map(([label, value]) => (
          <Fragment key={label}>
            <dt className="part">{label}</dt>
            <dd className="part">{value}</dd>
          </Fragment>
        ))}
        <dt>Remaining</dt>
        <dd>{amount(resource, resource.remaining)}</dd>
      </dl>
      <p className="muted small">{basisLine(resource)}</p>
      {detailLines(resource).map((line) => (
        <p key={line} className="muted small">
          {line}
        </p>
      ))}
    </section>
  );
}

export function ResourceDashboard() {
  const { refresh } = useAdmin();
  const [reading, setReading] = useState<Resources | null>(null);
  const [failed, setFailed] = useState(false);
  const colours = useRef<Record<string, ResourceColour> | null>(null);

  useEffect(() => {
    let active = true;
    async function read() {
      const started = performance.now();
      try {
        const read = await getResources();
        if (!active) return;
        setReading(read);
        setFailed(false);
        logColours(read, Math.round(performance.now() - started));
      } catch (e) {
        if (!active) return;
        if (e instanceof ServerRefusal && e.status === 401) {
          await refresh(); // signed out: the admin view gives way to the sign-in
          return;
        }
        console.error("Could not read the resources", e);
        setFailed(true);
      }
    }
    function logColours(read: Resources, took: number) {
      const now = Object.fromEntries(read.resources.map((r) => [r.name, r.colour]));
      const before = colours.current;
      colours.current = now;
      if (!before) {
        console.info(`Resources shown: ${JSON.stringify(now)} (${took} ms)`);
        return;
      }
      for (const [name, colour] of Object.entries(now)) {
        if (before[name] !== colour) {
          console.info(`Resource colour changed: ${name} ${before[name]} to ${colour}`);
        }
      }
    }
    void read();
    const timer = setInterval(() => void read(), REFRESH_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <>
      <h2 className="section-title">Resources</h2>
      {failed && <p className="error">The resources could not be read. Trying again…</p>}
      {!reading && !failed && <p className="muted">Reading the resources…</p>}
      {reading && (
        <>
          <p className="muted">
            Read at {new Date(reading.read_at).toLocaleTimeString()}, every 10 seconds while this
            page is open.
          </p>
          <div className="resources">
            {reading.resources.map((resource) => (
              <Card key={resource.name} resource={resource} thresholds={reading.thresholds} />
            ))}
          </div>
          <section className="panel" aria-labelledby="resource-colours">
            <h2 id="resource-colours">What the colours mean</h2>
            {MEANINGS.map(([colour, meaning, todo]) => (
              <p key={colour} className="colour-key">
                <span className={`colour-name ${colour}`}>{NAMES[colour]}</span>{" "}
                <span className="muted">({rangeOf(colour, reading.thresholds)})</span>: {meaning}.{" "}
                {todo}
              </p>
            ))}
          </section>
        </>
      )}
    </>
  );
}
