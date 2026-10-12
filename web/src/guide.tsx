// The recording guide as a step-by-step wizard: how to take the five photos and make the seven
// voice recordings on a Windows 10, Windows 11 or Mac laptop, then add them on the Setup page.
// The same content as docs/guides/Photo-and-Voice-Recording-Guide.pdf, except that the last part
// adds the files to this app instead of sending them to someone.

import type { ComponentChildren } from "preact";
import { useEffect, useState } from "preact/hooks";

export type Laptop = "win10" | "win11" | "mac";

const LAPTOPS: { id: Laptop; label: string; photo: string; voice: string }[] = [
  { id: "win10", label: "Windows 10", photo: "Camera app", voice: "Voice Recorder app" },
  { id: "win11", label: "Windows 11", photo: "Camera app", voice: "Sound Recorder app" },
  { id: "mac", label: "Mac", photo: "Photo Booth app", voice: "Voice Memos app" },
];

// Where the wizard is and which laptop was picked, kept in this browser so the guide opens where
// the user left it: the recordings can take a few sittings.
export interface GuideState {
  step: number;
  laptop: Laptop | null;
}

const STORAGE_KEY = "imageskin.guide";

export function loadGuide(): GuideState {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as Partial<GuideState>;
    const step = typeof saved?.step === "number" ? saved.step : 0;
    const laptop = LAPTOPS.some((l) => l.id === saved?.laptop) ? (saved?.laptop as Laptop) : null;
    return { step: Math.min(Math.max(0, Math.floor(step)), STEPS.length - 1), laptop };
  } catch {
    return { step: 0, laptop: null };
  }
}

function saveGuide(state: GuideState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.error("Could not save the guide's place", e);
  }
}

// Shows its children only for the laptops given, or for every laptop when none is picked yet.
function For({
  laptop,
  only,
  children,
}: {
  laptop: Laptop | null;
  only: Laptop[];
  children: ComponentChildren;
}) {
  return laptop === null || only.includes(laptop) ? <>{children}</> : null;
}

interface Step {
  title: string;
  body: (laptop: Laptop | null, pick: (l: Laptop) => void) => ComponentChildren;
}

function Script({ first, lines }: { first: number; lines: string[] }) {
  return (
    <ol className="script" start={first}>
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ol>
  );
}

function Before({ name, minutes, children }: { name: string; minutes: string; children?: ComponentChildren }) {
  return (
    <p className="notice">
      {children ?? (
        <>
          Press Record. Read each line, then pause about 1 second (one breath) before the next line.
        </>
      )}{" "}
      At the end: press Stop, listen to check it, and name it <b>{name}</b>. This whole recording
      takes about {minutes}.
    </p>
  );
}

function Questions({ items }: { items: string[] }) {
  return (
    <ul className="bullets">
      {items.map((q) => (
        <li key={q}>{q}</li>
      ))}
    </ul>
  );
}

export const STEPS: Step[] = [
  {
    title: "Before you begin",
    body: (laptop, pick) => (
      <>
        <p>This guide helps you make, on your own laptop:</p>
        <ul className="bullets">
          <li>Five photos of your face (picture files, usually ending in .jpg).</li>
          <li>
            Seven recordings of your voice, about 15 minutes of talking in total (sound files,
            usually ending in .m4a or .wav).
          </li>
        </ul>
        <p>
          The photo becomes the face, and the recordings teach the app to speak in a voice that
          sounds like you. Your recordings are not played back as they are; they are only used as a
          sample.
        </p>
        <h2>What you need</h2>
        <ul className="bullets">
          <li>A laptop with a built-in camera and microphone (almost all laptops have both).</li>
          <li>A quiet room and about 40 minutes (you can take a break between recordings).</li>
          <li>A window or lamp in front of you for light.</li>
          <li>This guide open next to the recording app, or on a second screen, so you can read the script while recording.</li>
        </ul>
        <p>No accounts, downloads or technical skills are needed. Everything uses apps that already come with your laptop.</p>
        <h2>Which laptop do you have?</h2>
        <p className="muted">The guide then shows only the steps for your laptop.</p>
        <fieldset className="laptops">
          <legend className="sr-only">Your laptop</legend>
          {LAPTOPS.map((l) => (
            <label key={l.id} className={laptop === l.id ? "picked" : undefined}>
              <input
                type="radio"
                name="laptop"
                checked={laptop === l.id}
                onChange={() => pick(l.id)}
              />
              <span className="title">{l.label}</span>
              <span className="muted">
                Photo: {l.photo}. Voice: {l.voice}.
              </span>
            </label>
          ))}
        </fieldset>
        <p className="muted">
          Not sure which Windows you have? Press the Windows key, type <b>winver</b> and press
          Enter. A small window shows "Windows 10" or "Windows 11". Click OK to close it.
        </p>
        <p className="notice">
          Your permission matters. Only use photos and voice recordings of yourself, or of someone
          who is happy for them to be used to make a talking video that looks and sounds like them.
        </p>
      </>
    ),
  },
  {
    title: "Get ready",
    body: () => (
      <>
        <h2>For the photo</h2>
        <ul className="bullets">
          <li><b>Light in front of you.</b> Sit facing a window (daytime is best) or a lamp. Do not sit with a bright window behind you, or your face will be dark.</li>
          <li><b>Plain background.</b> A plain wall behind you is ideal.</li>
          <li><b>Clean the camera lens.</b> Gently wipe the small lens above your screen with a soft cloth. Smudges make the photo blurry.</li>
          <li><b>Raise the laptop.</b> Put it on a few books so the camera is at about the height of your eyes, not looking up at your chin.</li>
          <li><b>Clear your face.</b> Take off sunglasses, hats and masks, and move hair away from your eyes. Ordinary glasses are fine, but tilt them slightly if they reflect light.</li>
        </ul>
        <h2>For the voice recording</h2>
        <ul className="bullets">
          <li><b>Quiet room.</b> Turn off the TV, music, fans, heaters and air conditioning. Close the windows and door. Silence your phone.</li>
          <li><b>Soft room is better.</b> A bedroom with curtains, a bed and carpet sounds much better than a kitchen or bathroom, which echo.</li>
          <li><b>Sit close.</b> Sit about an arm's length from the laptop or a little closer, and stay at the same distance the whole time.</li>
          <li><b>Have water nearby.</b> A sip between sections keeps your voice clear.</li>
          <li><b>Plug in the laptop</b> so it does not go to sleep or run out of battery while you record.</li>
        </ul>
        <p className="muted">
          Using a headset or plug-in microphone? That is fine and often sounds better. Plug it in
          before you open the recording app. Keep it a hand's width from your mouth, a little to the
          side so your breath does not hit it.
        </p>
        <h2>"Allow" messages</h2>
        <p>
          The first time you open a camera or recording app, your laptop may ask whether the app can
          use the camera or microphone. Always click <b>Allow</b> or <b>OK</b>. If you clicked
          "Don't allow" by mistake, see the last step of this guide.
        </p>
      </>
    ),
  },
  {
    title: "Take 5 photos",
    body: () => (
      <>
        <p>
          Take these 5 photos, in this order, without moving the laptop or changing the light
          between them. The app picks the best one as your face; the others are backups.
        </p>
        <table className="guide-table">
          <thead>
            <tr><th>Photo</th><th>Your head</th><th>Your face</th></tr>
          </thead>
          <tbody>
            <tr><td>1</td><td>Straight at the camera</td><td>Relaxed and neutral, mouth closed. This is the most important photo.</td></tr>
            <tr><td>2</td><td>Straight at the camera</td><td>Relaxed, lips slightly apart (as if about to say "uh"). No teeth showing, or only a little.</td></tr>
            <tr><td>3</td><td>Straight at the camera</td><td>A gentle, closed-mouth smile, the way you smile when greeting someone.</td></tr>
            <tr><td>4</td><td>Turned slightly to your left (about the angle of glancing at a clock on the wall). Eyes still on the lens.</td><td>Relaxed, mouth closed.</td></tr>
            <tr><td>5</td><td>Turned slightly to your right, the same small amount. Eyes still on the lens.</td><td>Relaxed, mouth closed.</td></tr>
          </tbody>
        </table>
        <p className="muted">If a photo comes out blurry, with eyes closed, or badly lit, simply take that one again.</p>
        <h2>What matters most</h2>
        <ol className="tips">
          <li><b>Your face fills a good part of the picture.</b> Head and shoulders only. Leave about a hand's width of space above your head and some space on each side, because the face moves slightly in the video.</li>
          <li><b>Eyes on the lens, not the screen.</b> Look at the small camera dot above the screen. Keep your eyes open and relaxed, not wide.</li>
          <li><b>Mouth closed or only slightly open.</b> The app makes the mouth movements itself. A big smile or open mouth "freezes" your teeth into every word.</li>
          <li><b>Soft, even light on both sides of your face.</b> Avoid one side in shadow, shiny spots on your forehead, or a bright window behind you.</li>
          <li><b>Sharp, not blurry.</b> Hold still for the moment the photo is taken. Clean the lens first.</li>
          <li><b>Nothing covering your face.</b> No hands near your face, hair out of your eyes, no hat, sunglasses or mask. Normal glasses are fine without glare.</li>
          <li><b>Camera at eye level.</b> Sit up straight with your shoulders relaxed and level.</li>
          <li><b>Plain, tidy background.</b> Avoid busy shelves, mirrors, posters, or other people behind you.</li>
          <li><b>Look like yourself on a normal day.</b> Solid colours look better than busy patterns. This is how the video version of you will look.</li>
        </ol>
      </>
    ),
  },
  {
    title: "How to take the photos",
    body: (laptop) => (
      <>
        <For laptop={laptop} only={["win10", "win11"]}>
          <h2>Windows 10 and Windows 11: the Camera app</h2>
          <ol className="tips">
            <li>Click the Start button, or press the Windows key on your keyboard.</li>
            <li>Type <b>Camera</b>. When the Camera app appears in the list, click it.</li>
            <li>If asked "Let Camera access your camera?" or similar, click <b>Yes</b> or <b>Allow</b>. Your face now appears on the screen.</li>
            <li>Make sure the app is in photo mode, not video. If the round button on the right shows a video camera, click the small camera icon next to it.</li>
            <li>Sit back so your head and shoulders fit in the picture. Look at the small camera lens above the screen.</li>
            <li>Click the round <b>Take photo</b> button. You hear a shutter sound, and a small preview appears in a corner.</li>
            <li>Take the rest of the 5 photos from the previous step, one after another.</li>
            <li>To look at them, click the small preview in the corner. Close the Camera app when you are done.</li>
          </ol>
          <p className="muted">
            The photos are saved in your <b>Pictures</b> folder, inside <b>Camera Roll</b>. For a
            sharper photo, click the gear icon (Settings) and choose the largest size under Photo
            quality.
          </p>
        </For>
        <For laptop={laptop} only={["mac"]}>
          <h2>Mac: the Photo Booth app</h2>
          <ol className="tips">
            <li>Press <b>Command + Space</b> together. A search bar appears.</li>
            <li>Type <b>Photo Booth</b> and press Return. Your face appears and a small green light turns on next to the camera.</li>
            <li>In the bottom left corner, click the left of the three small buttons (a single square), so the app takes one photo, not four.</li>
            <li>If you see an Effects button, make sure no effect is chosen ("Normal").</li>
            <li>Sit back so your head and shoulders fit in the picture. Look at the camera lens above the screen.</li>
            <li>Click the red camera button. Photo Booth counts down 3, 2, 1, the screen flashes white, and the photo is taken.</li>
            <li>Take the rest of the 5 photos from the previous step. They appear as small pictures along the bottom.</li>
            <li>Save each photo to the Desktop: click it, then choose <b>File &gt; Export</b>, choose Desktop, name it (such as Photo 1) and click Save. Or drag each small picture onto your Desktop.</li>
          </ol>
        </For>
      </>
    ),
  },
  {
    title: "Record your voice",
    body: () => (
      <>
        <p>
          You will make 7 recordings, one for each of the next steps. Record a section, stop, listen
          to check it, and only then move on. If a section goes wrong, just record that section
          again; you never have to start over.
        </p>
        <table className="guide-table">
          <thead>
            <tr><th>Recording</th><th>What you say</th><th>About</th></tr>
          </thead>
          <tbody>
            <tr><td>Voice 1</td><td>Read script lines 1 to 10</td><td>1½ minutes</td></tr>
            <tr><td>Voice 2</td><td>Read script lines 11 to 19</td><td>1½ minutes</td></tr>
            <tr><td>Voice 3</td><td>Answer 2 or 3 questions in your own words</td><td>1 minute</td></tr>
            <tr><td>Voice 4</td><td>Read a short story</td><td>3 minutes</td></tr>
            <tr><td>Voice 5</td><td>Read script lines 20 to 39</td><td>3 minutes</td></tr>
            <tr><td>Voice 6</td><td>Read a short explanation</td><td>3 minutes</td></tr>
            <tr><td>Voice 7</td><td>Answer 4 or 5 questions in your own words</td><td>2 minutes</td></tr>
          </tbody>
        </table>
        <p className="muted">
          The times are the length of each whole recording, from Record to Stop. Recordings 1 to 3
          teach the app what your voice sounds like; 4 to 7 give it enough to learn your voice in
          depth, so it still sounds like you with a different accent. You can take breaks between
          recordings, as long as you use the same room, microphone and distance.
        </p>
        <h2>How to speak</h2>
        <ul className="bullets">
          <li>Use your normal, relaxed voice, the way you talk to a friend.</li>
          <li>Speak at a natural, everyday pace. Pause about 1 second (one breath) after each line.</li>
          <li>Small slip? Don't stop. Pause for a second, then say that line again and carry on.</li>
          <li>Lots of slips, or a noise (cough, phone, dog)? Stop, delete that recording, and record that section again.</li>
          <li>Only your voice should be on the recording. Ask others in the house to stay quiet.</li>
        </ul>
        <h2>First, a 10-second test</h2>
        <p>
          Record yourself saying "Hello, this is a test" and play it back. If it sounds muffled,
          quiet or echoey, move closer to the laptop or try a different room.
        </p>
      </>
    ),
  },
  {
    title: "How to make each recording",
    body: (laptop) => (
      <>
        <p>You repeat these "record, stop, check, rename" steps seven times, once for each recording.</p>
        <For laptop={laptop} only={["win10"]}>
          <h2>Windows 10: the Voice Recorder app</h2>
          <ol className="tips">
            <li>Press the Windows key, type <b>Voice Recorder</b>, and click the app.</li>
            <li>If asked to allow the microphone, click <b>Yes</b> or <b>Allow</b>.</li>
            <li>Click the big round blue microphone button to start recording. A timer starts counting.</li>
            <li>Read that step's page only. At the end, click the round <b>Stop</b> button. The recording appears in the list on the left.</li>
            <li>Click the recording and press Play. Listen to a few seconds at the start and the end.</li>
            <li>Rename it: right-click the recording, choose <b>Rename</b>, type Voice 1 (then Voice 2 and so on) and press Enter.</li>
            <li>Not happy with it? Right-click it, choose Delete, and record that section again.</li>
          </ol>
          <p className="muted">
            The recordings are saved in <b>Documents</b>, inside <b>Sound recordings</b>, as .m4a
            files. Can't find Voice Recorder? Get "Windows Voice Recorder" free from the Microsoft
            Store.
          </p>
        </For>
        <For laptop={laptop} only={["win11"]}>
          <h2>Windows 11: the Sound Recorder app</h2>
          <ol className="tips">
            <li>Press the Windows key, type <b>Sound Recorder</b>, and click the app.</li>
            <li>If asked to allow the microphone, click <b>Yes</b> or <b>Allow</b>.</li>
            <li>One time only: click the three dots (···) at the top right, choose Settings, set Recording format to <b>WAV</b> (if shown) and Audio quality to <b>High</b>. Click the back arrow.</li>
            <li>If you use a headset or plug-in mic, pick it from the microphone list at the bottom left.</li>
            <li>Click the big round red <b>Record</b> button. A timer starts counting.</li>
            <li>Read that step's page only. At the end, click the square <b>Stop</b> button.</li>
            <li>Click the recording and press Play. Listen to a few seconds at the start and the end.</li>
            <li>Rename it: right-click it, choose <b>Rename</b>, type Voice 1 (then Voice 2 and so on) and press Enter.</li>
            <li>Not happy with it? Right-click it, choose Delete, and record that section again.</li>
          </ol>
          <p className="muted">
            The recordings are saved in <b>Documents</b>, inside <b>Sound recordings</b>, as .wav or
            .m4a files. Either is fine.
          </p>
        </For>
        <For laptop={laptop} only={["mac"]}>
          <h2>Mac: the Voice Memos app</h2>
          <ol className="tips">
            <li>Press <b>Command + Space</b>, type <b>Voice Memos</b>, and press Return.</li>
            <li>If asked to allow the microphone, click <b>OK</b> or <b>Allow</b>.</li>
            <li>One time only: choose <b>Voice Memos &gt; Settings</b> (Preferences on older Macs) and set Audio Quality to <b>Lossless</b>.</li>
            <li>Click the big round red <b>Record</b> button at the bottom left.</li>
            <li>Read that step's page only. At the end, click <b>Done</b>.</li>
            <li>Click the recording and press Play. Listen to a few seconds at the start and the end.</li>
            <li>Rename it: double-click its name, type Voice 1 (then Voice 2 and so on) and press Return.</li>
            <li>Not happy with it? Click it, press Delete, and record that section again.</li>
            <li>Drag the recording from the list onto your Desktop. A file ending in .m4a appears there.</li>
          </ol>
          <p className="muted">Do not click the magic-wand Enhance Recording button, and do not add effects.</p>
        </For>
        <p className="notice">
          Leave "clean-up" features off. Noise reduction, voice clarity, voice focus or "enhance"
          options make the voice worse for this. The plain, natural sound gives the best result.
        </p>
      </>
    ),
  },
  {
    title: "Recording 1 of 7",
    body: () => (
      <>
        <Before name="Voice 1" minutes="1½ minutes" />
        <Script
          first={1}
          lines={[
            "Hi, thanks for stopping by. It's good to see you.",
            "I wasn't sure what to expect today, but honestly, I'm glad you asked.",
            "Let me think about that for a second. Okay, here's what I'd do.",
            "First, take a deep breath. Second, write down the three things that matter most. Third, pick one and start there.",
            "Really? You found it in the garage, behind the old bicycle? That's amazing!",
            "No, no, that's not what I meant at all. I meant the other one, the blue one.",
            "The weather this weekend should be cool and breezy, with a chance of rain on Sunday afternoon.",
            "My favourite meal is still my grandmother's soup, with fresh bread and a little too much butter.",
            "She sells seashells by the seashore, and the shells she sells are surely seashells.",
            "The quick brown fox jumps over the lazy dog, and the dog doesn't seem to mind.",
          ]}
        />
      </>
    ),
  },
  {
    title: "Recording 2 of 7",
    body: () => (
      <>
        <Before name="Voice 2" minutes="1½ minutes" />
        <Script
          first={11}
          lines={[
            "Could you call me back around four thirty? My number is five five five, two nine one, eight three zero seven.",
            "It cost about twelve dollars and fifty cents, which felt fair for what it was.",
            "Hmm, I'm not totally sure. I think it was in two thousand nineteen, but don't quote me on that.",
            "Wow. That is genuinely the best news I've heard all week.",
            "I'm sorry to hear that. That sounds really hard, and it makes sense that you're tired.",
            "Here's a fun fact: an octopus has three hearts and blue blood.",
            "Would you like the short version, or the long version with all the details?",
            "Measure twice, cut once. My father used to say that, and he was usually right.",
            "Thanks for listening. Take care of yourself, and let's talk again soon.",
          ]}
        />
      </>
    ),
  },
  {
    title: "Recording 3 of 7",
    body: () => (
      <>
        <Before name="Voice 3" minutes="1 minute">
          Choose two or three of the questions below. Press Record and answer them out loud in your
          own words, as if chatting with a friend, for about 20 to 30 seconds each. Pause for a
          second between questions.
        </Before>
        <Questions
          items={[
            "What did you do last weekend?",
            "Describe a place you love and why.",
            "Explain how to make something you cook often.",
            "What's something you've changed your mind about?",
          ]}
        />
      </>
    ),
  },
  {
    title: "Recording 4 of 7",
    body: () => (
      <>
        <Before name="Voice 4" minutes="3 minutes">
          Press Record. Read the story at a relaxed, natural pace, as if reading to a friend. Pause
          about 1 second between paragraphs. If you stumble, pause and reread that sentence.
        </Before>
        <div className="story">
          <p>Every Saturday morning, my neighbour Ruth walks her old dog, Biscuit, down to the bakery on the corner. Biscuit is twelve years old, mostly grey around the nose, and moves at exactly one speed: slow. Ruth says that suits her just fine.</p>
          <p>Last spring, the bakery changed owners. The new baker, a quiet young man named Theo, didn't know about Biscuit. On his first Saturday, he looked up from the counter to find a dog sitting politely by the door, staring at the shelf of day-old rolls.</p>
          <p>"Is he waiting for someone?" Theo asked. Ruth laughed. "He's waiting for you. The last owner gave him the end of a loaf every week. I think he expects the tradition to continue."</p>
          <p>Theo thought about it for a moment, then broke off a small piece of crust and crouched down. Biscuit took it gently, wagged his tail twice, and walked straight back out the door. Ruth apologised and hurried after him.</p>
          <p>The next Saturday, Theo had a paper bag ready, with "Biscuit" written on it in thick black marker. The Saturday after that, he added a second bag for Ruth: two warm cinnamon buns and a note that said, "For the person holding the leash."</p>
          <p>By summer, half the street knew the story. Children waved at Biscuit through the window. A man from the hardware store brought a water bowl for the doorstep. Somebody even painted a small sign, shaped like a bone, that read: "Dogs welcome. Especially Biscuit."</p>
          <p>I asked Ruth once why she thought the whole thing had caught on. She shrugged and said, "People like a routine they can count on. And everybody likes being expected." Then she checked her watch, because it was almost nine o'clock, and Biscuit was already standing by the door.</p>
        </div>
      </>
    ),
  },
  {
    title: "Recording 5 of 7",
    body: () => (
      <>
        <Before name="Voice 5" minutes="3 minutes" />
        <Script
          first={20}
          lines={[
            "Good morning! Did you sleep well, or were the neighbours noisy again?",
            "That's a fair question, and I don't have a perfect answer, but I'll do my best.",
            "Wait, say that again? I think I missed the most important part.",
            "The train leaves at seven fifteen from platform nine, so we should be there by seven.",
            "Honestly, I loved the first half of the film, but the ending felt rushed.",
            "If you add a pinch of salt to the water, the pasta tastes much better.",
            "Oh no, I left my umbrella on the bus. Typical!",
            "Let's keep it simple: one page, three ideas, and a clear next step.",
            "She was born on the fourth of July, nineteen eighty-six, in a small town by the river.",
            "Are you sure? Because yesterday you told me the opposite.",
            "Thank you so much. That was incredibly kind, and I won't forget it.",
            "The library opens at ten, closes at six, and is shut on Mondays.",
            "Please don't worry about it. These things happen to everyone.",
            "Which would you rather have: a quiet cabin in the woods, or a flat in the middle of the city?",
            "Turn left at the lights, go past the petrol station, and it's the third house on the right.",
            "I can't believe it's already October. Where did the year go?",
            "Bright yellow jackets, thick woollen gloves, and very wet boots.",
            "The answer is forty-two, but nobody remembers what the question was.",
            "Hmm. Let me check my notes, and I'll get back to you this afternoon.",
            "That's everything for now. Thanks again, and have a lovely evening.",
          ]}
        />
      </>
    ),
  },
  {
    title: "Recording 6 of 7",
    body: () => (
      <>
        <Before name="Voice 6" minutes="3 minutes">
          Press Record. Read it as if you were explaining it to a curious friend. Pause about 1
          second between paragraphs.
        </Before>
        <div className="story">
          <p>Have you ever wondered why the sky is blue during the day, but red and orange at sunset? The answer has to do with sunlight, and with the air itself.</p>
          <p>Sunlight looks white, but it is really a mixture of every colour of the rainbow. Each colour travels as a wave, and the waves have different lengths. Red light has long, lazy waves. Blue and violet light have short, quick ones.</p>
          <p>When sunlight enters the air, it bumps into tiny gas molecules, mostly nitrogen and oxygen. These molecules are far too small to see, but they scatter short waves much more strongly than long ones. So blue light bounces around the sky in every direction, and wherever you look, some of it reaches your eyes. That is why the whole sky seems to glow blue.</p>
          <p>You might ask: if violet waves are even shorter, why isn't the sky violet? There are two reasons. First, the sun gives off less violet light than blue. Second, our eyes are simply more sensitive to blue. Put those together, and blue wins.</p>
          <p>Now think about sunset. When the sun is low, its light has to travel through much more air before it reaches you, sometimes forty times as much as at midday. Along that long path, most of the blue light is scattered away to the sides. What is left is the light that scatters least: the yellows, oranges and deep reds.</p>
          <p>Dust, smoke and tiny water droplets can make sunsets even more dramatic, because they add their own scattering and colour. After a large volcanic eruption, people around the world have seen unusually vivid sunsets for months.</p>
          <p>So the next time you watch the sky change colour in the evening, remember: you are watching sunlight take the long way home.</p>
        </div>
      </>
    ),
  },
  {
    title: "Recording 7 of 7",
    body: () => (
      <>
        <Before name="Voice 7" minutes="2 minutes">
          Choose four or five of the questions below, different from the ones in Recording 3. Press
          Record and answer them out loud in your own words, for about 20 to 30 seconds each. Pause
          for a second between questions.
        </Before>
        <Questions
          items={[
            "What was your first job, and what did you learn from it?",
            "Describe your ideal day off, from morning to night.",
            "Tell a short story about a time something went wrong but turned out fine.",
            "What's a book, film or song you'd recommend, and why?",
            "Explain how to get from your home to a shop or café you like.",
            "If you could learn any skill instantly, what would it be?",
            "What's the best piece of advice anyone has given you?",
          ]}
        />
        <p className="muted">
          Optional: is English not your first language? Make one more recording of about 1 minute
          talking about anything in your first language, and name it Voice 8. It helps capture the
          sound of your voice.
        </p>
      </>
    ),
  },
  {
    title: "Check your recordings",
    body: () => (
      <ul className="checklist">
        <li>You have 7 recordings named Voice 1 to Voice 7 (plus Voice 8 if you made the optional one).</li>
        <li>Voice 1 and Voice 2 are each about 1 to 2 minutes long; Voice 3 is about 1 minute; Voice 4, 5 and 6 are each about 3 minutes; Voice 7 is about 2 minutes.</li>
        <li>When you play them back, your voice is clear and easy to hear.</li>
        <li>There is no music, TV, other voices or loud background hum.</li>
        <li>If one of them went wrong, delete just that one and record that section again.</li>
      </ul>
    ),
  },
  {
    title: "Add your files to the app",
    body: (laptop) => (
      <>
        <p>Find your 5 photos and 7 recordings, then add them on the Setup page.</p>
        <For laptop={laptop} only={["win10", "win11"]}>
          <h2>Windows</h2>
          <ul className="bullets">
            <li>Photos: in the file picker, open <b>Pictures</b>, then <b>Camera Roll</b>. Your 5 photos are the newest ones.</li>
            <li>Recordings: open <b>Documents</b>, then <b>Sound recordings</b>. You should see Voice 1 to Voice 7.</li>
            <li>Can't find them? Pictures and Documents may be inside a OneDrive folder. Type <b>Camera Roll</b> or <b>Sound recordings</b> in the search box at the top right.</li>
          </ul>
        </For>
        <For laptop={laptop} only={["mac"]}>
          <h2>Mac</h2>
          <p>All 12 files are on your Desktop (you put them there in the earlier steps).</p>
        </For>
        <ol className="tips">
          <li>On the Setup page, click <b>Add photos</b> and choose all 5 photos at once.</li>
          <li>Click <b>Add recordings</b> and choose all 7 recordings at once.</li>
          <li>Each file is checked as it arrives. If one needs fixing, the page says what to change; take or record that one again and add it.</li>
        </ol>
        <a className="button" href="#/setup">
          Go to setup
        </a>
      </>
    ),
  },
  {
    title: "If something goes wrong",
    body: () => (
      <table className="guide-table">
        <thead>
          <tr><th>Problem</th><th>What to try</th></tr>
        </thead>
        <tbody>
          <tr><td>The camera shows a black screen or "We can't find your camera"</td><td>Some laptops have a sliding cover over the camera, or a camera on/off key. Slide the cover open or press the key. Close any other app that might use the camera (Zoom, Teams, Skype, FaceTime) and try again.</td></tr>
          <tr><td>Windows: I clicked "No" when asked about the camera or microphone</td><td>Press the Windows key, type <b>Camera privacy settings</b> (or <b>Microphone privacy settings</b>) and open it. Turn on access, and make sure Camera, Voice Recorder or Sound Recorder is switched on.</td></tr>
          <tr><td>Mac: I clicked "Don't Allow"</td><td>Apple menu &gt; System Settings &gt; Privacy &amp; Security. Click Camera or Microphone and switch on Photo Booth or Voice Memos.</td></tr>
          <tr><td>The photo is dark or has strong shadows</td><td>Face a window or put a lamp behind the laptop, shining toward your face. Turn off bright lights behind you.</td></tr>
          <tr><td>The photo is blurry</td><td>Wipe the camera lens, sit still, and make sure the room is bright.</td></tr>
          <tr><td>The recording timer doesn't move, or playback is silent</td><td>Check that the microphone is allowed (see above). Plug a headset in before opening the app. On Windows 11 Sound Recorder, check the microphone chosen at the bottom left.</td></tr>
          <tr><td>The recording sounds echoey or noisy</td><td>Move to a smaller room with soft furniture, curtains or carpet. A walk-in closet works very well. Turn off fans and air conditioning.</td></tr>
          <tr><td>I can't find Voice Recorder or Sound Recorder (Windows)</td><td>Open the Microsoft Store, search for "Sound Recorder" or "Windows Voice Recorder", and click Get. It is free.</td></tr>
          <tr><td>I can't find my files</td><td>Windows: in File Explorer, type the file name, Camera Roll or Sound recordings in the search box at the top right. Mac: press Command + Space and type the file name.</td></tr>
        </tbody>
      </table>
    ),
  },
];

export function GuidePage() {
  const [state, setState] = useState<GuideState>(loadGuide);
  const { step, laptop } = state;

  useEffect(() => {
    saveGuide(state);
  }, [state]);

  function go(to: number) {
    setState({ ...state, step: to });
    console.info(`Guide step ${to + 1} of ${STEPS.length}: ${STEPS[to].title}`);
    window.scrollTo?.({ top: 0 });
  }

  function pick(l: Laptop) {
    setState({ ...state, laptop: l });
    console.info(`Guide laptop: ${l}`);
  }

  const current = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <section className="guide">
      <p className="muted step-count">
        Recording guide · Step {step + 1} of {STEPS.length}
      </p>
      <progress value={step + 1} max={STEPS.length} aria-label="Guide progress" />
      <h1>{current.title}</h1>
      {current.body(laptop, pick)}
      <div className="guide-nav">
        <button type="button" className="secondary" disabled={step === 0} onClick={() => go(step - 1)}>
          Back
        </button>
        {!last && (
          <button type="button" onClick={() => go(step + 1)}>
            Next: {STEPS[step + 1].title}
          </button>
        )}
      </div>
      <label className="jump">
        Go to step{" "}
        <select value={step} onChange={(e) => go(Number(e.currentTarget.value))}>
          {STEPS.map((s, i) => (
            <option key={s.title} value={i}>
              {i + 1}. {s.title}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
