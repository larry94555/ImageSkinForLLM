// The host's resource view (roadmap R193, item 152): the disk space the signed-in host has used,
// counted by the server (R192) each time the page is opened. Every file of their site counts,
// in six lines (R65b).

import { useEffect, useState } from "preact/hooks";

import { getHostDisk, type HostDisk } from "./api";
import { HostOnlyPage, useHost } from "./host";

const MB = 1000 ** 2;
const GB = 1000 ** 3;

// In MB below a GB, else in GB, as the disk's maker and the admin dashboard count (1000³).
export function size(bytes: number): string {
  if (bytes >= GB) return `${(bytes / GB).toFixed(2)} GB`;
  return `${(bytes / MB).toFixed(1)} MB`;
}

const ROWS: [keyof HostDisk, string, string][] = [
  [
    "images_and_recordings",
    "Images and voice recordings",
    "Your photos and recordings, with the faces, voice and videos made from them.",
  ],
  ["pdfs", "PDFs", "Your PDFs, with what was read from them and the wiki."],
  ["guidelines", "Guidelines", "The identity, goals and guidelines, with their saved versions."],
  ["conversations", "Conversations and history", "Every visitor's conversation on your site."],
  ["preferences", "Preferences", "Your site's settings and its LLM."],
  ["other", "Other", "Everything else your site keeps, such as the setup's progress."],
  ["total", "Total", "All the disk space your site takes."],
];

export function ResourcesPage() {
  const session = useHost().session;
  const host = session?.signed_in === true;
  const [disk, setDisk] = useState<HostDisk | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!host) return;
    getHostDisk(true).then(
      (read) => {
        setDisk(read);
        console.info(`Resource view opened: ${JSON.stringify(read)}`);
      },
      (e: unknown) => {
        console.error("Could not read the disk space used", e);
        setFailed(true);
      },
    );
  }, [host]);

  if (session === null) return <p>Loading…</p>;
  if (!host) return <HostOnlyPage />;
  return (
    <div className="host-page resources-page">
      <h1>Resources</h1>
      <p className="lead">The disk space your site's files take, as {session.email}.</p>
      {failed && (
        <p className="error">The disk space used could not be read. Reload to try again.</p>
      )}
      {!failed && disk === null && <p className="muted busy">Counting…</p>}
      {disk && (
        <section className="panel" aria-label="Disk space used">
          <h2>Disk space used</h2>
          <dl className="disk-used">
            {ROWS.map(([key, label, about]) => (
              <div key={key} className={key === "total" ? "disk-row total" : "disk-row"}>
                <dt>
                  {label}
                  <span className="muted"> · {about}</span>
                </dt>
                <dd>{size(disk[key])}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
