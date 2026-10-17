// The photo and recordings in use, on the Settings page (roadmap R27a): view the photo, play
// each recording, and run its checks again.

import { useEffect, useState } from "preact/hooks";

import {
  checkUpload,
  getConsent,
  getPhotoChoice,
  listUploads,
  type Upload,
  uploadUrl,
} from "./api";
import { Checks, minutes } from "./checks";

interface InUse {
  photo: Upload | null; // the one the video is made from
  sounds: Upload[]; // the ones that passed the checks, joined into the voice sample
}

// What is in use: nothing before consent, since nothing can be uploaded until then.
async function readInUse(): Promise<InUse> {
  if (!(await getConsent()).agreed) return { photo: null, sounds: [] };
  const [photos, choice, sounds] = await Promise.all([
    listUploads("photos"),
    getPhotoChoice(),
    listUploads("sounds"),
  ]);
  return {
    photo: photos.find((p) => p.id === choice.id) ?? null,
    sounds: sounds.filter((s) => s.problems?.length === 0),
  };
}

export function YourFiles() {
  // null until it has loaded.
  const [inUse, setInUse] = useState<InUse | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [checking, setChecking] = useState<string | null>(null); // one at a time
  const [failed, setFailed] = useState<string | null>(null); // the one that couldn't be checked

  useEffect(() => {
    readInUse()
      .then((read) => {
        setInUse(read);
        const photo = read.photo?.name ?? "no photo";
        console.info(`Photos and recordings in use: ${photo}, ${read.sounds.length} recording(s)`);
      })
      .catch((e: unknown) => {
        console.error("Could not load the photos and recordings in use", e);
        setLoadFailed(true);
      });
  }, []);

  // The result replaces the old one, and stays shown even if it no longer passes.
  async function checkAgain(item: Upload) {
    if (checking !== null) return;
    setChecking(item.id);
    setFailed(null);
    const started = performance.now();
    try {
      const checked = await checkUpload(item.kind, item.id);
      const swap = (u: Upload) => (u.id === checked.id ? checked : u);
      setInUse(
        (current) =>
          current && {
            photo: current.photo && swap(current.photo),
            sounds: current.sounds.map(swap),
          },
      );
      const took = Math.round(performance.now() - started);
      const found =
        checked.problems === null ? "not checked" : `${checked.problems.length} problem(s)`;
      console.info(`Checked again: ${item.name}, ${found} (${took} ms)`);
    } catch (e) {
      console.error(`Could not check ${item.name} again`, e);
      setFailed(item.id);
    }
    setChecking(null);
  }

  function actions(item: Upload) {
    return (
      <>
        <Checks item={item} queue={checking === item.id ? 0 : -1} />
        <button
          type="button"
          className="use"
          disabled={checking !== null}
          onClick={() => checkAgain(item)}
        >
          Check again
        </button>
        {failed === item.id && <p className="error">It could not be checked. Try again.</p>}
      </>
    );
  }

  return (
    <section className="panel" aria-labelledby="settings-files">
      <h2 id="settings-files">Photos and recordings</h2>
      <p className="muted">
        The photo the video is made from, and the recordings the voice is made from.
      </p>
      {loadFailed && <p className="error">Could not load them. Reload the page to try again.</p>}
      {inUse === null && !loadFailed && <p className="muted busy">Loading…</p>}
      {inUse && (
        <>
          <h3>Photo</h3>
          {inUse.photo ? (
            <ul className="photos">
              <li>
                <a href={uploadUrl("photos", inUse.photo.id)} target="_blank" rel="noreferrer">
                  <img src={uploadUrl("photos", inUse.photo.id)} alt={inUse.photo.name} />
                </a>
                <span className="name">{inUse.photo.name}</span>
                {actions(inUse.photo)}
              </li>
            </ul>
          ) : (
            <p className="muted">
              No photo is in use yet. Add one in <a href="#/setup">Setup</a>.
            </p>
          )}
          <h3>Recordings</h3>
          {inUse.sounds.length > 0 ? (
            <ul className="sounds">
              {inUse.sounds.map((item) => (
                <li key={item.id}>
                  <audio controls preload="none" src={uploadUrl("sounds", item.id)} />
                  <span className="name">
                    {item.name}
                    {item.seconds !== null && ` (${minutes(item.seconds)})`}
                  </span>
                  {actions(item)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              No recording is in use yet. Add them in <a href="#/setup">Setup</a>.
            </p>
          )}
        </>
      )}
    </section>
  );
}
