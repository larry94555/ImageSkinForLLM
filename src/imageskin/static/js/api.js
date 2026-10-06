// Calls to the server's JSON API.
async function json(response) {
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }
    return (await response.json());
}
export async function getConsent() {
    return json(await fetch("/api/consent"));
}
export async function confirmConsent() {
    return json(await fetch("/api/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agreed: true }),
    }));
}
