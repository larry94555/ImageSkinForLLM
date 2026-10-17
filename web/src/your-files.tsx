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

function isInUse(inUse: InUse, id: string): boolean {
  return inUse.photo?.id === id || inUse.sounds.some((s) => s.id === id);
}

export function YourFiles() {
  // null until it has loaded.
  const [inUse, setInUse] = useState<InUse | null>(null);
  // Checked again here and no longer in use since, shown with their result to say why.
  const [dropped, setDropped] = useState<Upload[]>([]);
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

  // A new result can change what is in use: a photo that no longer passes, or scores below
  // another, is no longer the one for the video, and a recording that no longer passes leaves
  // the voice sample. So what is in use is read again after each check.
  async function checkAgain(item: Upload) {
    if (checking !== null) return;
    setChecking(item.id);
    setFailed(null);
    const started = performance.now();
    let checked: Upload | null = null;
    try {
      checked = await checkUpload(item.kind, item.id);
      const took = Math.round(performance.now() - started);
      const found =
        checked.problems === null ? "not checked" : `${checked.problems.length} problem(s)`;
      console.info(`Checked again: ${item.name}, ${found} (${took} ms)`);
    } catch (e) {
      console.error(`Could not check ${item.name} again`, e);
      setFailed(item.id);
    }
    if (checked) await refresh(checked);
    setChecking(null);
  }

  async function refresh(checked: Upload) {
    try {
      const read = await readInUse();
      const out = !isInUse(read, checked.id);
      if (out) console.info(`${checked.name} is no longer in use`);
      setInUse(read);
      setDropped((was) => [
        ...was.filter((u) => u.id !== checked.id && !isInUse(read, u.id)),
        ...(out ? [checked] : []),
      ]);
    } catch (e) {
      console.error("Could not read the photos and recordings in use again", e);
      setLoadFailed(true);
    }
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

  const photos = inUse
    ? [...(inUse.photo ? [inUse.photo] : []), ...dropped.filter((u) => u.kind === "photos")]
    : [];
  const sounds = inUse ? [...inUse.sounds, ...dropped.filter((u) => u.kind === "sounds")] : [];
  const isDropped = (item: Upload) => dropped.some((u) => u.id === item.id);

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
          {photos.length > 0 ? (
            <ul className="photos">
              {photos.map((item) => (
                <li key={item.id}>
                  <a href={uploadUrl("photos", item.id)} target="_blank" rel="noreferrer">
                    <img src={uploadUrl("photos", item.id)} alt={item.name} />
                  </a>
                  <span className="name">{item.name}</span>
                  {isDropped(item) && (
                    <span className="muted check">No longer used for the video</span>
                  )}
                  {actions(item)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              No photo is in use yet. Add one in <a href="#/setup">Setup</a>.
            </p>
          )}
          <h3>Recordings</h3>
          {sounds.length > 0 ? (
            <ul className="sounds">
              {sounds.map((item) => (
                <li key={item.id}>
                  <audio controls preload="none" src={uploadUrl("sounds", item.id)} />
                  <span className="name">
                    {item.name}
                    {item.seconds !== null && ` (${minutes(item.seconds)})`}
                  </span>
                  {isDropped(item) && (
                    <span className="muted check">No longer in the voice sample</span>
                  )}
                  {actions(item)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              No recording is in use yet. Add them in <a href="#/setup">Setup</a>.
            </p>
          )}
          {dropped.length > 0 && (
            <p className="muted">
              Add, remove or choose photos and recordings in <a href="#/setup">Setup</a>.
            </p>
          )}
        </>
      )}
    </section>
  );
}
