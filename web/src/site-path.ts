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

// Where the page goes when its trial site has moved to its own subdomain; a function so tests
// can see it.
export const moving = { to: (url: string) => window.location.assign(url) };

// Makes every fetch of an address of the app go under the trial site's path. Once the site's
// host picks its subdomain (roadmap R63), a call from a page opened before then is answered
// with the site's new address (X-Site-Moved), and the page goes there, on the same page.
export function sendFetchesUnderSitePath(
  target: { fetch: typeof fetch } = window,
): void {
  const path = sitePath();
  if (!path) return;
  const original = target.fetch.bind(target);
  let moved = false;
  target.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await original(typeof input === "string" ? under(input, path) : input, init);
    const to = response.headers.get("x-site-moved");
    if (to && !moved) {
      moved = true;
      console.info(`Trial site moved to ${to}: going there`);
      moving.to(`${to}${window.location.hash}`);
    }
    return response;
  };
  console.info(`Trial site: calls are made under ${path}`);
}
