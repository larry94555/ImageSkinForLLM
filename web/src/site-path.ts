// A trial site is at a path of the main address, /t/<code> (roadmap R61a), and the server
// serves its page there. Every call and file the page asks for goes under that path too, so it
// reaches that site: `under` puts an address of the app there, and `sendFetchesUnderSitePath`
// does it for every fetch, so the calls need no change. At any other address both do nothing.

const TRIAL_PATH = /^\/t\/[a-z0-9]{12}(?=\/|$)/;

// "/t/<code>" when the page is a trial site's, otherwise "".
export function sitePath(pathname: string = window.location.pathname): string {
  return TRIAL_PATH.exec(pathname)?.[0] ?? "";
}

// The app's address `url` as this page asks for it: under its trial site's path, if any.
export function under(url: string, path: string = sitePath()): string {
  if (!path || !url.startsWith("/") || url.startsWith("//")) return url;
  if (url === path || url.startsWith(`${path}/`)) return url; // there already
  return `${path}${url}`;
}

// Makes every fetch of an address of the app go under the trial site's path.
export function sendFetchesUnderSitePath(
  target: { fetch: typeof fetch } = window,
): void {
  const path = sitePath();
  if (!path) return;
  const original = target.fetch.bind(target);
  target.fetch = (input: RequestInfo | URL, init?: RequestInit) =>
    original(typeof input === "string" ? under(input, path) : input, init);
  console.info(`Trial site: calls are made under ${path}`);
}
