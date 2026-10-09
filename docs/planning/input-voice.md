# ImageSkinForLLM inputs: the voice sample

**Short answer:** yes. About 4 minutes of clean recordings of the person, reading a prepared script and then talking freely, is enough to clone their voice with today's tools. The recording guide splits this into 3 short recordings, and the app combines them into one voice sample. Since 2026-10-09 the guide asks for 4 more (7 in all, about 15 minutes of talking). Today's clone and accent conversion still learn from only 10 seconds of the sample, so the extra recordings are not used yet: they are recorded once now so that a fine-tuned voice (see below) can be trained later without asking the person to record again. Larry asked for them after R26a's converted accents did not sound enough like him; training is not on the roadmap yet. The voice sample is not played back in the video. It is a *reference* the voice model learns from. For each LLM reply, the voice model generates brand-new audio of that reply in the person's voice, and that new audio drives the lip sync.

**Not yet verified.** Tool facts here (inputs, streaming, timestamps, GPU needs, consent, latency) describe the tools as of mid-2026 and have not been checked against their documentation. Vendors change these often. Before choosing an engine, check each fact that affects the choice against the vendor or project documentation, and record the link and a "verified on YYYY-MM-DD" date next to it.

## How the pieces fit

1. **Once, up front:** the person makes the recordings, and the app combines them into the voice sample. We upload it to (or load it into) a voice-cloning text-to-speech (TTS) engine, which produces a "voice."
2. **Every chatbot turn:** LLM reply text goes to TTS with that voice, which returns an audio clip of the reply.
3. That audio clip, plus the photo (or base video), goes to the video engine, which returns the video with lips matched to the audio.
4. The text shown on screen is the same text that went to TTS, so text, voice and lips all line up. Many TTS engines also return word timestamps, which we can use to highlight words as they're spoken.

## How much audio do the tools need?

| Kind of clone | Audio needed | Examples | Quality |
|---|---|---|---|
| **Instant / zero-shot** | 5 to 30 seconds works; 1 to 2 minutes is better | ElevenLabs Instant Voice Clone, Cartesia, PlayHT, Resemble; open source XTTS-v2, F5-TTS, CosyVoice 2, Fish Speech / OpenAudio, Chatterbox, OpenVoice | Good likeness of tone and accent. Can drift on long replies or sound slightly generic. No training wait. |
| **Light fine-tune** | About 1 to 10 minutes | GPT-SoVITS, StyleTTS 2 fine-tune, XTTS fine-tune | Noticeably closer to the person. Needs a GPU and some setup. |
| **Professional / trained** | 30 minutes minimum, 1 to 3 hours ideal | ElevenLabs Professional Voice Clone, Resemble custom voice | Hard to tell from the real person. Hours of recording and a verification step. |

**More audio is not always better for instant clones.** Most instant engines use only the first 10 to 60 seconds of what you give them, so the *best* minute matters more than the total. Extra minutes pay off only if we later move to a fine-tuned or professional clone.

**Recommendation:** record once, the 7 recordings in the guide (about 15 minutes; Recordings 1 to 3, about 4 minutes, are enough for the instant clone). Use the best 1 to 2 minutes for an instant clone now, and keep all the recordings so we can upgrade to a fine-tuned voice later without asking the person to record again.

## Read script vs. free talking

A read script is a good idea: it guarantees the sample covers all the sounds of the language, and it is easy for the person. The one catch is that people sound like they are *reading* when they read, and the clone copies that. A chatbot should sound conversational. So the script below has two parts: a read section, then a few questions to answer off the cuff.

## One file or several?

The tools need one voice sample, but the person does not have to record it in one take. The recording guide asks for 7 separate recordings, one per section, so a mistake means redoing one short section, not the whole script. The app checks each file and combines the valid ones into one voice sample. Practical notes:

- Keep the mic, room and distance the same for all recordings.
- Trim long silences, coughs and restarts before uploading.
- If the person also records the optional talking video clip (see [input-images.md](input-images.md)), have them **read this same script on camera**. The clip's audio becomes the voice sample, and one session covers both inputs. Use an external mic even then; a phone or laptop camera mic from a meter away is the most common cause of a bad clone.

## Recording format and quality

- **Format:** WAV, 44.1 or 48 kHz, 16- or 24-bit, mono. Keep this as the master. MP3 at 192 kbps or higher is acceptable for uploading, but don't record straight to low-bitrate MP3.
- **Room:** quiet, with soft furnishings (a closet full of clothes is a classic home vocal booth). No echo, fans, AC, traffic, music or TV.
- **Mic:** a decent USB mic or a phone held about 15 to 20 cm from the mouth, slightly off to the side to avoid breath pops. Same distance throughout.
- **Levels:** loud enough that speech peaks around -12 to -6 dB, never clipping (hitting the top).
- **No processing:** no noise suppression, auto-gain, reverb or music. Turn off "voice isolation" or "enhance" features on phones and conferencing apps. The clone copies whatever processing it hears.
- **Delivery:** the person's normal, relaxed speaking voice at a natural pace, the way they'd talk to a friend. Not a "presentation" voice. Only one speaker on the recording.
- **Consent:** hosted services (ElevenLabs and others) require the person's consent and sometimes a short spoken verification phrase, especially for professional clones. Plan on the person being available for that.

## The recording script

Reading time is about 3 minutes at a relaxed pace, then about 1 minute of free talking. Lines are short so the person can pause naturally between them. In the recording guide, lines 1 to 10 are Recording 1, lines 11 to 19 are Recording 2, and the free talking is Recording 3. Recordings 4 to 7 (a story, script lines 20 to 39, an explanation and more free talking) are only in the guide. The script keeps the guide's spelling.

### Part 1: read aloud (Recordings 1 and 2)

> Hi, thanks for stopping by. It's good to see you.
>
> I wasn't sure what to expect today, but honestly, I'm glad you asked.
>
> Let me think about that for a second. Okay, here's what I'd do.
>
> First, take a deep breath. Second, write down the three things that matter most. Third, pick one and start there.
>
> Really? You found it in the garage, behind the old bicycle? That's amazing!
>
> No, no, that's not what I meant at all. I meant the other one, the blue one.
>
> The weather this weekend should be cool and breezy, with a chance of rain on Sunday afternoon.
>
> My favourite meal is still my grandmother's soup, with fresh bread and a little too much butter.
>
> She sells seashells by the seashore, and the shells she sells are surely seashells.
>
> The quick brown fox jumps over the lazy dog, and the dog doesn't seem to mind.
>
> Could you call me back around four thirty? My number is five five five, two nine one, eight three zero seven.
>
> It cost about twelve dollars and fifty cents, which felt fair for what it was.
>
> Hmm, I'm not totally sure. I think it was in two thousand nineteen, but don't quote me on that.
>
> Wow. That is genuinely the best news I've heard all week.
>
> I'm sorry to hear that. That sounds really hard, and it makes sense that you're tired.
>
> Here's a fun fact: an octopus has three hearts and blue blood.
>
> Would you like the short version, or the long version with all the details?
>
> Measure twice, cut once. My father used to say that, and he was usually right.
>
> Thanks for listening. Take care of yourself, and let's talk again soon.

### Part 2: talk freely (Recording 3, about 1 minute, no script)

Answer two or three of these in your own words, as if chatting with a friend:

- What did you do last weekend?
- Describe a place you love and why.
- Explain how to make something you cook often.
- What's something you've changed your mind about?

## Removing an accent while keeping the voice

**Short answer:** yes, mostly. A voice is roughly two layers: *timbre* (the sound of the throat and mouth, which is what makes it recognizably "them") and *accent and prosody* (how vowels are shaped, rhythm, intonation). Tools can now keep the first and replace the second. The result sounds like the person's voice speaking with an American accent. Expect it to sound very much like them, but a little less "them" than a direct clone, because some of how a person sounds really is their rhythm and intonation.

**Why a plain clone won't do it:** instant cloners copy the accent along with the timbre, since both are in the sample. Cloning a Russian-accented English sample gives Russian-accented English output. Cloning from a Russian-language sample and asking for English usually still carries the accent.

### Approaches (best fit first)

| Approach | How it works | Identity kept | Notes |
|---|---|---|---|
| **American TTS + voice conversion** | Generate the reply with a native American TTS voice, then run that audio through a voice-conversion model that swaps in the person's timbre. Open source: OpenVoice (built specifically to separate timbre from accent and style), Seed-VC, RVC. Hosted: speech-to-speech "voice changer" features such as ElevenLabs Voice Changer. | Timbre: high. Rhythm and intonation come from the American base voice. | Most controllable and works today. Adds one step (and some delay) per reply. Pick a base voice close to the person in age, gender and pitch; it matters a lot. |
| **Accent-controllable TTS** | Some newer TTS models and voice-design tools take an accent or language setting separate from the reference voice. | Varies by tool; often weaker than voice conversion. | Worth testing as a single-step option, but support for overriding the accent of a *cloned* voice is inconsistent. Check current docs. |
| **Real-time accent conversion** | Products such as Sanas and Krisp accent conversion change a live speaker's accent while keeping their voice. | High. | Built for call centers converting a live microphone, and focused on specific accents (often South Asian and Filipino English). Check whether Russian-accented English is supported. Not a natural fit for a TTS pipeline. |
| **Fine-tuned voice** | Train a voice model on the person's audio plus lots of American speech so it learns their timbre with American pronunciation. | Highest, in principle. | Research-grade effort, needs a GPU and tuning. A later option only. |

### Effect on the recording plan

- **The recording stays the same:** one clean session, same format and tips as above. For the voice-conversion route, the sample only needs to capture timbre, so the accent in it doesn't matter.
- **Add one optional minute in the person's first language** (the guide's optional Recording 4, "Voice 4"). People often speak most relaxed and natural in their first language, which gives a clean timbre reference, and voice-conversion models don't care which language the sample is in.
- **Plan an A/B listening test:** generate the same few replies with (A) a direct clone, which keeps the accent, and (B) American TTS plus voice conversion. Let the person choose; some people prefer to keep a light accent because it sounds more like them.
- **Lip sync is unaffected.** The video engine follows whatever final audio it gets.

## Open questions for the next step

- **Hosted or self-hosted TTS?** Hosted (ElevenLabs, Cartesia) is the fastest and simplest to stream, which matters for chat latency. Open source (XTTS-v2, F5-TTS, CosyVoice 2) keeps the voice data local and costs nothing per word, but needs a GPU.
- **Accent:** if we need accent removal, voice conversion adds a step per reply. That favors tools that can do it in one pass, or a fast self-hosted converter.
- This choice ties into the video engine choice in [input-images.md](input-images.md), since both steps add delay to every reply.
