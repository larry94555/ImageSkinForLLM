// The Customization page (roadmap R92, item 87): the AI's identity and goals as the LLM is given
// them with every prompt, for a signed-in host only. Editing them here comes with R94; until
// then they are changed in customization.json in the app's home folder.

import { useEffect, useState } from "preact/hooks";

import { type Customization, getCustomization } from "./api";
import { HostOnlyPage, useHost } from "./host";

const IDENTITY: [keyof Customization["identity"], string][] = [
  ["name", "Name"],
  ["speaks_as", "Speaks as"],
  ["purpose", "Purpose"],
  ["audience", "Who it is for"],
  ["helps_with", "What it can help with"],
];

export function CustomizationPage() {
  const session = useHost().session;
  const host = session?.signed_in === true;
  const [read, setRead] = useState<Customization | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!host) return;
    getCustomization(true).then(
      (got) => {
        setRead(got);
        console.info(`Customization page opened: shipped=${got.shipped}`);
      },
      (e: unknown) => {
        console.error("Could not read the customization", e);
        setFailed(true);
      },
    );
  }, [host]);

  if (session === null) return <p>Loading…</p>;
  if (!host) return <HostOnlyPage />;
  return (
    <div className="host-page customization-page">
      <h1>Customization</h1>
      <p className="lead">
        Who the person in the video is and what they aim for, given to the LLM with every prompt.
        "Who are you?" and "What is your purpose?" are answered from the identity.
      </p>
      {failed && (
        <p className="error">The customization could not be read. Reload to try again.</p>
      )}
      {!failed && read === null && <p className="muted busy">Loading…</p>}
      {read && (
        <>
          <p className="muted">
            {read.shipped ? "As shipped. " : ""}To change them for now, edit customization.json in
            the app's home folder; the change is used from the next prompt.
          </p>
          <section className="panel" aria-labelledby="customization-identity">
            <h2 id="customization-identity">Identity</h2>
            <dl className="identity">
              {IDENTITY.map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{read.identity[key] || <span className="muted">Not set</span>}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="panel" aria-labelledby="customization-goals">
            <h2 id="customization-goals">Goals</h2>
            {read.goals.length ? (
              <ul className="goals">
                {read.goals.map((goal) => (
                  <li key={goal}>{goal}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">None</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
