# ImageSkinForLLM inputs: how many images?

**Short answer:** one good photo is enough. Several photos add little with today's tools. A short video clip of the person is the input that really raises quality.

**Not yet verified.** Tool facts here (inputs, streaming, timestamps, GPU needs, consent, latency) describe the tools as of mid-2026 and have not been checked against their documentation. Vendors change these often. Before choosing an engine, check each fact that affects the choice against the vendor or project documentation, and record the link and a "verified on YYYY-MM-DD" date next to it.

## 1. Single image (what most tools are built for)

Current "audio-driven portrait animation" models take **one photo + an audio track** and generate a video of that face speaking the audio, including lip sync, head motion and blinks.

| Tool | Type | Notes |
|---|---|---|
| SadTalker | Open source | Older, fast, runs on a modest GPU. Mostly head and mouth motion, looks a bit stiff. |
| LivePortrait | Open source | Very good at animating a still face, but it is driven by a *video* or motion, not audio. You pair it with an audio-to-motion step. |
| Hallo / Hallo2 / Hallo3 | Open source | Diffusion-based, high quality, slow (well below real time). |
| EchoMimic, Sonic, FantasyTalking, InfiniteTalk / MultiTalk | Open source | The newer generation of diffusion models. Good quality and expressive, but heavy and slow. |
| MuseTalk | Open source | Real-time *lip-sync*: it repaints the mouth on an existing video. Works best with a short base clip. From a still photo you'd first make an idle loop (for example with LivePortrait). |
| D-ID | Hosted | Single photo. Has a streaming API made for chatbots. |
| HeyGen (Photo Avatar / Avatar IV) | Hosted | Single photo gives good results. A custom "digital twin" needs about 2 minutes of video. |
| Hedra (Character-3) | Hosted | Single photo, very expressive. Clip-based, not built for live chat. |
| Tavus, Simli | Hosted | Built for real-time conversational avatars. Tavus wants a short training video; Simli supports photo-based faces. |

**Good:** easiest input to get, and nothing to capture.
**Limits:** the model has to invent everything the photo doesn't show, such as the inside of the mouth, teeth, the far side of the face and how the person actually moves. Large head turns break down. The person's expressions are generic, not their own.

## 2. Several photos (about 3 to 10)

Most audio-driven tools **take only one reference image**, so extra photos mostly go unused. Where they help:
- **Choosing** the best frontal shot.
- **Fine-tuning** a personal model (LoRA-style, typically 10 to 20 images) for some diffusion pipelines. That's more identity consistency, at the cost of a training step.
- Making a few **pose or expression variants** to switch between. That's a polish item.

Net: optional. Extra photos are worth collecting only so the app can pick the best one.

## 3. Short video clip (about 30 seconds to 2 minutes of the person talking)

This is the real step up in quality:
- The mouth interior, teeth, natural blinks and the person's own mannerisms are real, not invented.
- Real-time lip-sync methods (MuseTalk-style, HeyGen and Tavus twins) work best with a base video and are the most practical way to keep up with a chatbot.
- **Bonus:** the same clip's audio can serve as the voice sample for voice cloning, so one capture covers both inputs.

**Downside:** someone has to record it, and hosted twins usually need a consent step from the person.

## What makes a good input photo

- Facing the camera or slightly turned (under about 15 to 20 degrees). Eyes open, looking at the lens.
- Neutral face or a slight smile, **mouth closed or slightly open**, and no big grin (teeth get baked in).
- Even, soft lighting with no harsh shadows across the face.
- Sharp and high resolution: the face should be at least about 512 px tall, and 1024 px or more is better.
- Head and shoulders in frame with some space around the head (the model needs room for motion).
- Nothing covering the face: no hands, hair over eyes, sunglasses or mask. Ordinary glasses are usually fine.
- A plain or simple background is easiest. Some tools animate the background poorly.

## The bigger constraint is speed, not image count

For a chatbot, the LLM replies, then voice synthesis runs, then the video is generated. The high-quality single-photo models (Hallo, EchoMimic and similar) take minutes per sentence on a good GPU. Real-time options are hosted streaming avatars (D-ID, HeyGen, Tavus, Simli) or MuseTalk-style lip-sync on a pre-rendered base clip. Choosing the first video engine is the next planning step, and it partly decides the input: streaming lip-sync favors a short base video.

## Recommendation

1. **Require at least one good photo.** A single photo is enough for several major talking-avatar tools and for the first prototype. Some tools (a Tavus replica, a HeyGen digital twin) need video instead.
2. **Treat a short video clip (about 1 minute of the person talking) as the optional upgrade.** It improves realism and real-time performance, and it can double as the voice sample.
3. **Extra photos are optional.** The recording guide asks for 5 so the app can pick the best one.
