// Run with `npm test`, which compiles first. Tests the compiled router.
import assert from "node:assert/strict";
import { test } from "node:test";

import { pageFor, resolve } from "../../src/imageskin/static/js/router.js";

test("hashes map to pages", () => {
  assert.equal(pageFor(""), "home");
  assert.equal(pageFor("#/"), "home");
  assert.equal(pageFor("#/consent"), "consent");
  assert.equal(pageFor("#/setup/"), "setup");
  assert.equal(pageFor("#/nowhere"), "not-found");
});

test("setup is blocked until consent is confirmed", () => {
  assert.deepEqual(resolve("#/setup", false), { page: "consent", redirect: "#/consent" });
  assert.deepEqual(resolve("#/setup", true), { page: "setup" });
});

test("other pages are open without consent", () => {
  assert.deepEqual(resolve("#/", false), { page: "home" });
  assert.deepEqual(resolve("#/consent", false), { page: "consent" });
});
