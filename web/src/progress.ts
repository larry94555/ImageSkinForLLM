// Where this browser keeps a lesson (R41h), a quiz (R41i) and an assessment (R41j) under way, so
// a reload or a participant who stops picks up where they left off.

export const LESSON_KEY = "imageskin.lesson";
export const QUIZ_KEY = "imageskin.quiz";
export const ASSESSMENT_KEY = "imageskin.assessment";

// Forgets them, as part of the conversation, when Delete my data has removed it (roadmap R31).
// Other things kept here, such as the sound and the guide, are preferences and stay.
export function clearProgress(): void {
  for (const key of [LESSON_KEY, QUIZ_KEY, ASSESSMENT_KEY]) {
    try {
      localStorage.removeItem(key);
    } catch (e) {
      console.error(`Could not clear ${key}`, e);
    }
  }
}
