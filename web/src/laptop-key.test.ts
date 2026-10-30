import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  canProve,
  idFromSpki,
  indexedDbStore,
  type KeyStore,
  laptopEntry,
  laptopId,
  prove,
  useKeyStore,
} from "./laptop-key";

// A key store that lasts across "reloads" (forgetting the key read), as IndexedDB does.
function memoryStore(): KeyStore & { saved: number } {
  let kept: CryptoKeyPair | undefined;
  return {
    saved: 0,
    async load() {
      return kept;
    },
    async save(pair) {
      kept = pair;
      this.saved += 1;
    },
  };
}

function bytes(base64: string): Uint8Array<ArrayBuffer> {
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
}

beforeEach(() => {
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  useKeyStore(indexedDbStore);
});

test("the ID is the same as the server's for the same key", async () => {
  // tests/test_admin_laptops.py has the same value for these bytes.
  expect(await idFromSpki(new TextEncoder().encode("a public key"))).toBe(
    "LT-BNZU-R6QD-RFYM-JDWA-PTLT",
  );
});

test("the key is made once and kept across reloads", async () => {
  const store = memoryStore();
  useKeyStore(store);
  const first = await laptopId();
  expect(first).toMatch(/^LT(-[A-Z2-7]{4}){5}$/);
  useKeyStore(store); // a reload: the page forgets the key it read
  expect(await laptopId()).toBe(first);
  expect(store.saved).toBe(1);
  expect(console.info).toHaveBeenCalledWith("Laptop key made");
  useKeyStore(memoryStore()); // cleared site data: a new key, a new ID
  expect(await laptopId()).not.toBe(first);
});

test("the key can't be exported", async () => {
  const store = memoryStore();
  useKeyStore(store);
  await laptopId();
  const pair = (await store.load())!;
  expect(pair.privateKey.extractable).toBe(false);
  await expect(crypto.subtle.exportKey("pkcs8", pair.privateKey)).rejects.toThrow();
});

test("the proof is the key's signature over the challenge, with the key", async () => {
  useKeyStore(memoryStore());
  const proof = await prove("the challenge");
  expect(proof.challenge).toBe("the challenge");
  expect(await idFromSpki(bytes(proof.public_key))).toBe(await laptopId());
  const key = await crypto.subtle.importKey(
    "spki",
    bytes(proof.public_key),
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["verify"],
  );
  const signature = bytes(proof.signature);
  expect(signature.length).toBe(64); // raw r and s, as the server expects
  const signed = new TextEncoder().encode("the challenge");
  const check = { name: "ECDSA", hash: "SHA-256" };
  expect(await crypto.subtle.verify(check, key, signature, signed)).toBe(true);
  expect(await crypto.subtle.verify(check, key, signature, new TextEncoder().encode("x"))).toBe(
    false,
  );
});

test("a key that couldn't be kept is made again next time", async () => {
  const store = memoryStore();
  store.save = () => Promise.reject(new Error("quota"));
  useKeyStore(store);
  await expect(laptopId()).rejects.toThrow("quota");
  store.save = async () => {};
  await expect(laptopId()).resolves.toMatch(/^LT-/);
});

test("a proof needs HTTPS or localhost", () => {
  vi.stubGlobal("isSecureContext", false);
  expect(canProve()).toBe(false);
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("indexedDB", {});
  expect(canProve()).toBe(true);
});

test("the entry to paste names the laptop's ID", () => {
  expect(laptopEntry("LT-AAAA")).toBe('[[laptop]]\nname = "My laptop"\nid = "LT-AAAA"\n');
});

test("IndexedDB keeps the key pair", async () => {
  const { indexedDB: fake } = await import("fake-indexeddb");
  vi.stubGlobal("indexedDB", fake);
  expect(await indexedDbStore.load()).toBeUndefined();
  const made = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, [
    "sign",
    "verify",
  ]);
  await indexedDbStore.save(made);
  const kept = (await indexedDbStore.load())!;
  expect(kept.privateKey.extractable).toBe(false);
  const spki = (key: CryptoKey) => crypto.subtle.exportKey("spki", key);
  expect(new Uint8Array(await spki(kept.publicKey))).toEqual(
    new Uint8Array(await spki(made.publicKey)),
  );
});
