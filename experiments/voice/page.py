"""The listening page: the person's own recording, then each line in every voice, side by side."""

from dataclasses import dataclass, field
from html import escape


@dataclass
class Clip:
    wav: str  # file name next to the page
    speech_s: float
    added_ms: float = 0.0  # time the tool took on top of Kokoro (or Kokoro's own time)
    similarity: float | None = None  # to the person's recording, -1 to 1
    video: str = ""


@dataclass
class Line:
    text: str
    clips: dict[str, Clip] = field(default_factory=dict)  # by voice name, in column order


def _audio(name: str) -> str:
    return f'<audio controls preload="none" src="{escape(name)}"></audio>'


def _cell(clip: Clip | None) -> str:
    if clip is None:
        return "<td>not made</td>"
    notes = [f"{clip.speech_s:.1f} s of speech, made in {clip.added_ms / 1000:.1f} s"]
    if clip.similarity is not None:
        notes.append(f"similarity {clip.similarity:.2f}")
    video = ""
    if clip.video:
        video = f'<video controls preload="none" src="{escape(clip.video)}"></video>'
    return f"<td>{_audio(clip.wav)}<br>{video}<small>{'; '.join(notes)}</small></td>"


def summary(lines: list[Line], voice: str) -> tuple[float, float | None]:
    """Seconds taken per second of speech, and the mean similarity, for one voice."""
    clips = [line.clips[voice] for line in lines if voice in line.clips]
    speech = sum(c.speech_s for c in clips)
    taken = sum(c.added_ms for c in clips) / 1000
    sims = [c.similarity for c in clips if c.similarity is not None]
    return (taken / speech if speech else 0.0), (sum(sims) / len(sims) if sims else None)


def build_page(recording: str, voices: dict[str, str], lines: list[Line]) -> str:
    """HTML for the page. voices maps each voice name to a description shown over its column."""
    head = "".join(f"<th>{escape(n)}<br><small>{escape(d)}</small></th>" for n, d in voices.items())
    rows = []
    for line in lines:
        cells = "".join(_cell(line.clips.get(name)) for name in voices)
        rows.append(f"<tr><td>{escape(line.text)}</td>{cells}</tr>")
    totals = []
    for name in voices:
        per_s, sim = summary(lines, name)
        sim_text = f", mean similarity {sim:.2f}" if sim is not None else ""
        totals.append(f"<li>{escape(name)}: {per_s:.2f} s per second of speech{sim_text}</li>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice cloning test</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; color: #1d1d1f; background: #fff; }}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ccc; padding: 8px; vertical-align: top; }}
td:first-child {{ max-width: 280px; }} video {{ width: 240px; display: block; margin-top: 6px; }}
</style></head><body>
<h1>Voice cloning test</h1>
<p>Your own recording: {_audio(recording)}</p>
<p>Similarity compares each clip's voice with your recording (a speaker-recognition model; above
about 0.5 usually means the same speaker, 1.0 is identical). Your ears decide.</p>
<ul>{"".join(totals)}</ul>
<table><tr><th>Line</th>{head}</tr>
{"".join(rows)}
</table></body></html>
"""
