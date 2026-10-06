// Page routing from the URL hash (#/consent). Pure, so it can be tested without a browser.
const PAGES = {
    "": "home",
    "/": "home",
    "/consent": "consent",
    "/setup": "setup",
};
export function pageFor(hash) {
    const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
    return PAGES[path] ?? "not-found";
}
// Setup is blocked until the user confirms consent (feature item 22).
export function resolve(hash, consented) {
    const page = pageFor(hash);
    if (page === "setup" && !consented) {
        return { page: "consent", redirect: "#/consent" };
    }
    return { page };
}
