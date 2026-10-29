// This laptop's key and ID (roadmap R164, item 133). The browser makes an ECDSA P-256 key pair
// the first time it is needed, marked not exportable, so no page, this one included, can read
// the private key out; it is kept in IndexedDB, so it lasts across reloads until the site's data
// is cleared. The laptop ID is the first 20 base32 characters of the SHA-256 of the public key
// (SPKI), in groups of four, the same as the server works out (admin_laptops.laptop_id). At each
// sign-in the key signs the server's one-time challenge (R163).

export interface LaptopProof {
  public_key: string; // SPKI, base64
  challenge: string;
  signature: string; // WebCrypto's raw r and s, base64
}

// Where the key pair is kept: IndexedDB in the app, a stand-in in tests.
export interface KeyStore {
  load(): Promise<CryptoKeyPair | undefined>;
  save(pair: CryptoKeyPair): Promise<void>;
}

const DB = "imageskin-laptop";
const STORE = "keys";
const KEY = "laptop";

function request<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error ?? new Error("IndexedDB request failed"));
  });
}

function openDb(): Promise<IDBDatabase> {
  const open = indexedDB.open(DB, 1);
  open.onupgradeneeded = () => open.result.createObjectStore(STORE);
  return request(open);
}

export const indexedDbStore: KeyStore = {
  async load() {
    const db = await openDb();
    try {
      const value: unknown = await request(db.transaction(STORE).objectStore(STORE).get(KEY));
      return value as CryptoKeyPair | undefined;
    } finally {
      db.close();
    }
  },
  async save(pair) {
    const db = await openDb();
    try {
      await request(db.transaction(STORE, "readwrite").objectStore(STORE).put(pair, KEY));
    } finally {
      db.close();
    }
  },
};

let store: KeyStore = indexedDbStore;
let pair: Promise<CryptoKeyPair> | null = null;

// For tests: another place to keep the key, and forgetting the one already read.
export function useKeyStore(other: KeyStore): void {
  store = other;
  pair = null;
}

// Whether this browser can make and keep a laptop key: WebCrypto needs HTTPS or localhost.
export function canProve(): boolean {
  return Boolean(globalThis.isSecureContext && globalThis.crypto?.subtle && globalThis.indexedDB);
}

function keyPair(): Promise<CryptoKeyPair> {
  pair ??= (async () => {
    const kept = await store.load();
    if (kept) return kept;
    const made = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, false, [
      "sign",
      "verify",
    ]);
    await store.save(made);
    console.info("Laptop key made");
    return made;
  })();
  // A failure is tried again next time rather than kept.
  pair.catch(() => (pair = null));
  return pair;
}

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32(bytes: Uint8Array): string {
  let bits = 0;
  let value = 0;
  let out = "";
  for (const byte of bytes) {
    value = (value << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      out += BASE32[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) out += BASE32[(value << (5 - bits)) & 31];
  return out;
}

function base64(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}

// The laptop ID for a public key in SPKI form, as the server works it out.
export async function idFromSpki(spki: BufferSource): Promise<string> {
  const digest = base32(new Uint8Array(await crypto.subtle.digest("SHA-256", spki))).slice(0, 20);
  return "LT-" + (digest.match(/.{4}/g) ?? []).join("-");
}

async function publicSpki(): Promise<ArrayBuffer> {
  return crypto.subtle.exportKey("spki", (await keyPair()).publicKey);
}

// This laptop's ID, making its key the first time.
export async function laptopId(): Promise<string> {
  const id = await idFromSpki(await publicSpki());
  console.info("Laptop ID shown");
  return id;
}

// The proof for the server's challenge: the public key and the key's signature over it.
export async function prove(challenge: string): Promise<LaptopProof> {
  const start = performance.now();
  const { privateKey } = await keyPair();
  const signature = await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" },
    privateKey,
    new TextEncoder().encode(challenge),
  );
  const proof = { public_key: base64(await publicSpki()), challenge, signature: base64(signature) };
  console.info(`Laptop proof sent (${Math.round(performance.now() - start)} ms)`);
  return proof;
}

// The lines to paste into admin-laptops.toml for this laptop.
export function laptopEntry(id: string): string {
  return `[[laptop]]\nname = "My laptop"\nid = "${id}"\n`;
}
