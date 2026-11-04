// Where this browser keeps a lesson (R41h), a quiz (R41i) and an assessment (R41j) under way, so
// a reload or a participant who stops picks up where they left off.

export const LESSON_KEY = "imageskin.lesson";
export const QUIZ_KEY = "imageskin.quiz";
export const ASSESSMENT_KEY = "imageskin.assessment";

// Each site's own (roadmap R65). A subdomain is an origin of its own, with storage of its own,
// but trial sites share the main address's origin at /t/<code>/ (R61a), so their keys are named
// for their code: "imageskin.lesson.k7q2". The main address keeps the names it always had, so a
// lesson under way there is kept.
export function progressKey(key: string, path = window.location.pathname): string {
  const trial = /^\/t\/([^/]+)/.exec(path);
  return trial ? `${key}.${trial[1]}` : key;
}

// Forgets them, as part of the conversation, when Delete my data has removed it (roadmap R31).
// Other things kept here, such as the sound and the guide, are preferences and stay.
export function clearProgress(): void {
  for (const key of [LESSON_KEY, QUIZ_KEY, ASSESSMENT_KEY].map((k) => progressKey(k))) {
    try {
      localStorage.removeItem(key);
    } catch (e) {
      console.error(`Could not clear ${key}`, e);
    }
  }
}

// A signed-in participant's progress is kept for their account (roadmap R46), so it follows them
// to another browser: what this browser keeps is sent to the server a moment after each change,
// and what the server kept is put here when they sign in or the page opens.
export type Kept = Partial<Record<"lesson" | "quiz" | "assessment", unknown>>;
const KEPT: [keyof Kept, string][] = [
  ["lesson", LESSON_KEY],
  ["quiz", QUIZ_KEY],
  ["assessment", ASSESSMENT_KEY],
];
export const SYNC_DELAY_MS = 500;

let send: ((kept: Kept) => void) | null = null;
let waiting: ReturnType<typeof setTimeout> | null = null;

export function readProgress(): Kept {
  const kept: Kept = {};
  for (const [name, key] of KEPT) {
    try {
      const saved = JSON.parse(localStorage.getItem(progressKey(key)) ?? "null") as unknown;
      if (saved !== null) kept[name] = saved;
    } catch {
      // storage blocked, or something else saved there
    }
  }
  return kept;
}

export function writeProgress(kept: Kept): void {
  for (const [name, key] of KEPT) {
    try {
      const value = kept[name];
      if (value === undefined || value === null) localStorage.removeItem(progressKey(key));
      else localStorage.setItem(progressKey(key), JSON.stringify(value));
    } catch (e) {
      console.error(`Could not keep ${key}`, e);
    }
  }
}

// Called by each save of the lesson, quiz or assessment: sends them once the changes settle.
export function progressChanged(): void {
  if (!send) return;
  if (waiting) clearTimeout(waiting);
  waiting = setTimeout(() => {
    waiting = null;
    send?.(readProgress());
  }, SYNC_DELAY_MS);
}

// Starts sending this browser's progress for the signed-in participant, or stops (null).
export function syncProgress(to: ((kept: Kept) => void) | null): void {
  if (waiting) clearTimeout(waiting);
  waiting = null;
  send = to;
}
