// What the photo and sound checks found, shown under each photo or recording in setup and on
// the Settings page (R27a).

import type { Upload } from "./api";

// Under each photo or recording (roadmap R8 to R10): what to fix, or that it passed the checks,
// with a photo's score or a recording's length of speech.
// queue: 0 while it is being checked, above 0 while it waits its turn, -1 otherwise.
export function Checks({ item, queue }: { item: Upload; queue: number }) {
  const { problems, score, speech } = item;
  const what = item.kind === "photos" ? "photo" : "recording";
  if (queue === 0) return <span className="muted check busy">Checking {what}…</span>;
  if (queue > 0) return <span className="muted check">Waiting to check</span>;
  if (problems == null) return <span className="muted check">Not checked</span>;
  if (problems.length === 0) {
    return (
      <span className="done check">
        Looks good
        {score !== null && ` · score ${score} of 100`}
        {speech !== null && ` · ${minutes(speech)} of speech`}
      </span>
    );
  }
  return (
    <ul className="problems">
      {problems.map((p) => (
        <li key={p} className="error">
          {p}
        </li>
      ))}
    </ul>
  );
}

// 75.4 -> "1:15"
export function minutes(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
