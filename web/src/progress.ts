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
