// Each site's own Teach me, Quiz me and assessment progress in the browser (roadmap R65).

import { afterEach, expect, test } from "vitest";

import { loadLesson } from "./pages";
import { clearProgress, LESSON_KEY, progressKey, QUIZ_KEY } from "./progress";

afterEach(() => {
  localStorage.clear();
  window.history.pushState(null, "", "/");
});

test("a trial site's keys are named for its code, and the main address's are as they were", () => {
  expect(progressKey(LESSON_KEY, "/")).toBe("imageskin.lesson");
  expect(progressKey(LESSON_KEY, "/t/k7q2/")).toBe("imageskin.lesson.k7q2");
  expect(progressKey(QUIZ_KEY, "/t/k7q2")).toBe("imageskin.quiz.k7q2");
  expect(progressKey(QUIZ_KEY, "/tea/")).toBe("imageskin.quiz");
});

test("a lesson on one trial site isn't shown on another at the same address", () => {
  window.history.pushState(null, "", "/t/aaaa/");
  localStorage.setItem(progressKey(LESSON_KEY), JSON.stringify({ topic: "Mars", part: 2 }));
  expect(loadLesson()?.topic).toBe("Mars");
  window.history.pushState(null, "", "/t/bbbb/");
  expect(loadLesson()).toBeNull();
  window.history.pushState(null, "", "/");
  expect(loadLesson()).toBeNull(); // nor at the main address
  localStorage.setItem(LESSON_KEY, JSON.stringify({ topic: "Venus", part: 0 }));
  expect(loadLesson()?.topic).toBe("Venus");
  // Delete my data on a trial site clears its own progress only.
  window.history.pushState(null, "", "/t/aaaa/");
  clearProgress();
  expect(loadLesson()).toBeNull();
  expect(localStorage.getItem(LESSON_KEY)).not.toBeNull();
});
