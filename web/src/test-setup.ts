// Every browser in the web tests is a signed-in host (R190), as the participant view is for
// anyone else. host.test.tsx and participant-view.test.tsx sign in, or don't, for themselves.
import { vi } from "vitest";

vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  getHostSession: vi.fn(async () => ({ signed_in: true, email: "host@example.com" })),
}));
