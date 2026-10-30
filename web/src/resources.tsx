// The host's resource view (roadmap R193, item 152): the disk space the signed-in host has used,
// counted by the server (R192) each time the page is opened.

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
  ["images_and_recordings", "Images and voice recordings", "The photos and recordings you added."],
  ["pdfs", "PDFs", "The PDFs you added."],
  ["total", "Total", "All the disk space your files take."],
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
      <p className="lead">The disk space used by the files you added, as {session.email}.</p>
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
