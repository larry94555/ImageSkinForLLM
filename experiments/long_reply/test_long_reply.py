"""Unit tests for the R129 long reply experiment, with made-up clips and speech (no models)."""

import json
import urllib.request
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fake_llm import chunk, paced, pieces, reply_for, serve, tokens_in
from long_reply import (
    Misaligned,
    analyze,
    ends_at,
    gap_cause,
    markdown,
    median,
    new_lines,
    rate,
    sentences_of,
    timeline,
    wait_for_app,
)
from replies import PROMPTS, REPLIES
from serve_logged import clip_row, note_clips, silences

from imageskin.mouth_sync import heard
from imageskin.voice import Speech

RATE = 24000


def clip(n: int, **kw: Any) -> dict[str, Any]:
    """A clip row as time_reply.summarize writes it."""
    row = {
        "clip": n,
        "sentence_ms": 1000 * n,
        "waited_ms": 0,
        "voice_ms": 800,
        "video_ms": 600,
        "listed_ms": None,
        "seen_ms": None,
        "first_byte_ms": None,
        "downloaded_ms": None,
        "seconds": 2.0,
        "plays_ms": None,
        "gap_ms": None,
        "late": False,
        "error": None,
    }
    return {**row, **kw}


def note(
    sentence: str, n: int = 1, wav_s: float = 1.9, lead: float = 0.05, trail: float = 0.1
) -> dict[str, Any]:
    """A line as serve_logged.py notes it, for clip `n` of reply "r"."""
    return {
        "reply": "r",
        "n": n,
        "sentence": sentence,
        "text": sentence,
        "words": len(sentence.split()),
        "wav_s": wav_s,
        "lead_silence_s": lead,
        "trail_silence_s": trail,
    }


def summary(clips: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "prompt": "p",
        "reply_id": "r",
        "error": None,
        "first_word_heard_ms": clips[0]["plays_ms"] if clips else None,
        "first_token_ms": 1000,
        "last_token_ms": 61000,
        "clips": clips,
    }


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("It had two wheels.", "sentence"),
        ('He said "yes!"', "sentence"),
        ("Is it?", "sentence"),
        ("- Drink water before and after your run", "sentence"),
        ("## Tips", "sentence"),
        ("First line\nsecond", "sentence"),
        ("In the 1860s, French makers added pedals,", "clause"),
        ("Here are a few more tips:", "clause"),
        ("a leader —", "clause"),
        ("so riders pushed themselves along with", "none"),
    ],
)
def test_ends_at(sentence: str, expected: str) -> None:
    assert ends_at(sentence) == expected


def test_gap_cause() -> None:
    before = {"plays_ms": 5000}
    assert gap_cause({"gap_ms": None, "waited_ms": 0, "sentence_ms": 0}, before) is None
    assert gap_cause({"gap_ms": 0, "waited_ms": 0, "sentence_ms": 0}, before) is None
    assert gap_cause({"gap_ms": 500, "waited_ms": 900, "sentence_ms": 6000}, before) == "queued"
    assert gap_cause({"gap_ms": 500, "waited_ms": 0, "sentence_ms": 6000}, before) == "text late"
    assert gap_cause({"gap_ms": 500, "waited_ms": 50, "sentence_ms": 4000}, before) == (
        "slow to make"
    )
    assert gap_cause({"gap_ms": 500, "waited_ms": 0, "sentence_ms": None}, before) == (
        "slow to make"
    )


def test_analyze_joins_clips_and_finds_the_pauses() -> None:
    clips = [
        clip(1, first_byte_ms=3000, plays_ms=3000, seconds=2.0),
        # Ready 0.5 s after clip 1 ended: a gap, and it waited behind clip 1.
        clip(2, sentence_ms=2000, waited_ms=1000, first_byte_ms=5500, plays_ms=5500, gap_ms=500),
        # On time.
        clip(3, sentence_ms=4000, first_byte_ms=7000, plays_ms=7500, gap_ms=0, seconds=3.0),
    ]
    notes = [
        note("The bicycle has a long history,", trail=0.2),
        note("and it starts in Germany.", 2, lead=0.1),
        note("It had two wheels and no pedals.", 3, wav_s=2.9),
    ]
    result = analyze(summary(clips), notes)
    one, two, three = result["clips"]
    assert one["ends_at"] == "clause" and one["pause_heard_ms"] is None
    assert one["end_ms"] == 5000
    assert two["ready_before_end_ms"] == -500
    assert two["pause_heard_ms"] == 200 + 500 + 100
    assert two["cause"] == "queued" and two["after_ends_at"] == "clause"
    assert three["ready_before_end_ms"] == 500
    assert three["cause"] is None and three["pause_heard_ms"] == 100 + 0 + 50
    assert three["stretch_ms"] == 100
    words = 6 + 5 + 7
    assert result["words"] == words
    assert result["heard_s"] == 7.5  # 3.0 s to 10.5 s
    assert result["rate_heard_wpm"] == round(words / 7.5 * 60)
    assert result["rate_in_clips_wpm"] == round(words / 7.0 * 60)
    speech = (1.9 - 0.25) + (1.9 - 0.2) + (2.9 - 0.15)  # each clip's silence left out
    assert result["rate_speech_wpm"] == round(words / speech * 60)
    assert result["rate_llm_wpm"] == words  # written over 60 s
    assert result["make_ratio"] == round(3 * 1.4 / 7.0, 2)
    assert result["gaps_over"] == 1 and result["gaps_total_s"] == 0.5
    assert result["gap_causes"] == {"queued": 1}
    assert result["pauses_over"] == 1 and result["pauses_mid_sentence"] == 1
    assert result["ends"] == {"clause": 1, "sentence": 2}
    assert result["silence_ms"] == {"start": 50, "end": 100}
    assert result["stretch_ms_max"] == 100
    assert result["cut_together"] == 0 and not three["cut_together"]
    assert result["join_silence_s"] == round((200 + 100 + 100 + 50) / 1000, 1)


def test_analyze_takes_only_its_reply_s_lines() -> None:
    other = {**note("Another reply."), "reply": "x"}
    result = analyze(summary([clip(1), clip(2)]), [other, note("One.", 1), note("Two.", 2)])
    assert [c["text"] for c in result["clips"]] == ["One.", "Two."]


@pytest.mark.parametrize(
    "lines",
    [
        [1, 3],  # a line missing: clip 2's words would be clip 3's
        [1, 2, 2, 3],  # a line too many
        [2, 1, 3],  # out of order
        [1, 2],  # the last clip has no line
    ],
)
def test_analyze_refuses_misaligned_lines(lines: list[int]) -> None:
    clips = [clip(1), clip(2), clip(3)]
    with pytest.raises(Misaligned):
        analyze(summary(clips), [note(f"Clip {n}.", n) for n in lines])


def test_run_writes_nothing_from_misaligned_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import long_reply

    from imageskin import time_reply

    noted = tmp_path / "clips.jsonl"

    def measure(base: str, prompt: str) -> str:
        with noted.open("a", encoding="utf-8") as f:  # clip 2's line was never noted
            for n in (1, 3):
                f.write(json.dumps(note(f"Clip {n}.", n)) + "\n")
        return prompt

    monkeypatch.setattr(time_reply, "ask", lambda url, timeout=30: {"status": "ok"})
    monkeypatch.setattr(time_reply, "measure", measure)
    monkeypatch.setattr(time_reply, "summarize", lambda m: summary([clip(1), clip(2), clip(3)]))
    out = tmp_path / "out"
    code = long_reply.run("http://x", ["One?"], noted, out, "t", "v", None)
    assert code == 1 and not out.exists()
    assert "nothing written" in capsys.readouterr().out


def test_analyze_with_nothing_played() -> None:
    result = analyze(summary([clip(1)]), [note("Hello.")])
    assert result["heard_s"] is None and result["rate_heard_wpm"] is None
    assert result["rate_in_clips_wpm"] is None and result["make_ratio"] is None
    empty = analyze({**summary([]), "first_token_ms": None}, [])
    assert empty["words"] == 0 and empty["rate_llm_wpm"] is None
    assert empty["silence_ms"] == {"start": None, "end": None}


def test_median_and_rate() -> None:
    assert median([]) is None and median([None]) is None
    assert median([3, 1, None, 2]) == 2
    assert median([1, 4]) == 2  # rounded: 2.5 to the even 2
    assert rate(150, 60.0) == 150 and rate(10, 0) is None and rate(10, None) is None


def test_new_lines(tmp_path: Path) -> None:
    path = tmp_path / "clips.jsonl"
    assert new_lines(path, 0) == ([], 0)
    path.write_text('{"n": 1}\n{"n": 2}\n', encoding="utf-8")
    rows, offset = new_lines(path, 0)
    assert [r["n"] for r in rows] == [1, 2]
    with path.open("a", encoding="utf-8") as f:
        f.write('{"n": 3}\n')
    rows, _ = new_lines(path, offset)
    assert [r["n"] for r in rows] == [3]


def test_markdown_and_timeline(tmp_path: Path) -> None:
    clips = [
        clip(1, first_byte_ms=3000, plays_ms=3000),
        clip(2, sentence_ms=6000, first_byte_ms=5800, plays_ms=5800, gap_ms=800),
    ]
    clips.append(clip(3, sentence_ms=6020, first_byte_ms=8000, plays_ms=8000, gap_ms=0))
    notes = [note("Hello there,"), note("x " * 40 + "end.", 2), note("Bye.", 3)]
    result = analyze(summary(clips), notes)
    assert result["cut_together"] == 1
    result["own_rate_wpm"] = 170
    report = markdown([result, {**result, "error": "boom"}], "test")
    assert "# Where the pauses come from in a long reply (test)" in report
    assert "| 1 | 44 | 3000 |" in report
    assert "text late 1" in report and "Error: boom" in report
    assert "…" in report  # the long text is cut
    pytest.importorskip("matplotlib")
    path = tmp_path / "t.png"
    assert timeline(result, path, "Reply 1")
    assert path.stat().st_size > 1000


def test_reply_for_and_pieces() -> None:
    assert reply_for([{"role": "user", "content": PROMPTS[1]}]) == REPLIES[PROMPTS[1]]
    asked = [{"role": "system", "content": PROMPTS[2]}, {"role": "user", "content": "Hi"}]
    assert reply_for(asked) == REPLIES[PROMPTS[0]]
    assert reply_for([]) == REPLIES[PROMPTS[0]]
    text = "Hello there.\n\n- A list item"
    got = pieces(text)
    assert "".join(p for p, _ in got) == text
    assert got[0] == ("Hello", 1) and got[2] == ("\n\n-", 1)
    assert tokens_in("  extraordinary") == 3


def test_paced_sleeps_for_each_piece() -> None:
    slept: list[float] = []
    out = list(paced("one three", 2.0, 1.5, slept.append))
    assert out == ["one", " three"]
    assert slept == [1.5, 0.5, 0.5]


def test_chunk() -> None:
    assert json.loads(chunk("Hi").decode().removeprefix("data: "))["choices"][0] == {
        "index": 0,
        "delta": {"content": "Hi"},
        "finish_reason": None,
    }
    last = json.loads(chunk(None, "stop").decode().removeprefix("data: "))["choices"][0]
    assert last["delta"] == {} and last["finish_reason"] == "stop"


def post(url: str, body: dict[str, Any]) -> bytes:
    request = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        data: bytes = response.read()
        return data


def test_fake_llm_answers_as_llama_server_does() -> None:
    server = serve(0, 1000.0, 0.0)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/props", timeout=10) as r:
            assert json.loads(r.read())["default_generation_settings"]["n_ctx"] == 4096
        with urllib.request.urlopen(base + "/health", timeout=10) as r:
            assert json.loads(r.read()) == {"status": "ok"}
        assert json.loads(post(base + "/tokenize", {"content": "abcdefgh"})) == {"tokens": [0, 0]}
        warm = json.loads(post(base + "/v1/chat/completions", {"messages": [], "max_tokens": 1}))
        assert warm["choices"][0]["message"]["content"] == "The"
        asked = {"messages": [{"role": "user", "content": PROMPTS[1]}], "stream": True}
        events = post(base + "/v1/chat/completions", asked).decode().split("\n\n")
        text = "".join(
            json.loads(e.removeprefix("data: "))["choices"][0]["delta"].get("content", "")
            for e in events
            if e.startswith("data: {")
        )
        assert text == REPLIES[PROMPTS[1]]
        assert events[-2] == "data: [DONE]"
        with pytest.raises(urllib.error.HTTPError):
            post(base + "/nothing", {})
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/nothing", timeout=10)
    finally:
        server.shutdown()


def write_wav(path: Path, samples: np.ndarray) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.astype("<i2").tobytes())


def test_silences(tmp_path: Path) -> None:
    t = np.arange(int(RATE * 0.5)) / RATE
    tone = 8000 * np.sin(2 * np.pi * 220 * t)
    path = tmp_path / "a.wav"
    write_wav(path, np.concatenate([np.zeros(int(RATE * 0.2)), tone, np.zeros(int(RATE * 0.3))]))
    seconds, lead, trail = silences(path)
    assert seconds == pytest.approx(1.0)
    assert lead == pytest.approx(0.2, abs=0.006)
    assert trail == pytest.approx(0.3, abs=0.006)
    write_wav(path, np.zeros(RATE))
    assert silences(path) == (1.0, 1.0, 0.0)
    write_wav(path, np.zeros(10))
    assert silences(path)[1:] == (10 / RATE, 0.0)


def test_silences_match_the_app_s_voice_heard(tmp_path: Path) -> None:
    # Quiet noise, quieter speech and a short loud part: the loud level is the loudest 2 %
    # (mouth_sync.heard's 98th percentile), so the noise, 49 dB below it, is silence, though
    # it is only 30 dB below the speech (a 95th percentile would have heard it).
    def tone(amplitude: float, seconds: float) -> np.ndarray:
        return amplitude * np.sin(2 * np.pi * 220 * np.arange(int(RATE * seconds)) / RATE)

    samples = np.concatenate([tone(100, 0.2), tone(3000, 1.0), tone(30000, 0.05), tone(100, 0.2)])
    path = tmp_path / "a.wav"
    write_wav(path, samples)
    _, lead, trail = silences(path)
    windows = np.flatnonzero(heard(samples.astype("<i2") / 32768.0, RATE))
    assert lead == pytest.approx(windows[0] * 0.005)
    assert trail == pytest.approx(1.45 - (windows[-1] + 1) * 0.005)
    assert lead == pytest.approx(0.2, abs=0.006) and trail == pytest.approx(0.2, abs=0.006)


def test_clip_row(tmp_path: Path) -> None:
    path = tmp_path / "1.wav"
    write_wav(path, 8000 * np.ones(RATE // 2))
    row = clip_row("clips-abc", 1, "**Hi** there.", "Hi there.", path)
    assert row["reply"] == "abc" and row["n"] == 1 and row["words"] == 2
    assert row["wav_s"] == 0.5 and row["lead_silence_s"] == 0.0
    assert row["sentence"] == "**Hi** there."


def test_note_clips_wraps_the_voice_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from imageskin import reply_video

    wav = tmp_path / "1.wav"
    write_wav(wav, 8000 * np.ones(RATE))

    def speak(self: Any, n: int, sentence: str, sentence_at: float) -> Any:
        return None if sentence == "😀" else reply_video.Spoken(n, wav, sentence_at)

    monkeypatch.setattr(reply_video.SentenceClips, "_speak", speak)
    out = tmp_path / "clips.jsonl"
    note_clips(out)
    clips = type("Clips", (), {"folder": tmp_path / "clips-r1"})()
    spoken = reply_video.SentenceClips._speak(clips, 1, "Hello *there*.", 0.0)  # type: ignore[arg-type]
    assert spoken is not None and spoken.wav == wav
    assert reply_video.SentenceClips._speak(clips, 2, "😀", 0.0) is None  # type: ignore[arg-type]
    # Sentences 3 and 4 spoken as one clip (R130): its line is clip 2's.
    reply_video.SentenceClips._speak(clips, 3, "Three. Four.", 0.0)  # type: ignore[arg-type]
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["n"] for r in rows] == [1, 2]
    assert (
        rows[0]["reply"] == "r1" and rows[0]["text"] == "Hello there." and rows[0]["wav_s"] == 1.0
    )


def test_run_writes_the_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import long_reply

    from imageskin import cli, time_reply

    noted = tmp_path / "clips.jsonl"
    noted.write_text('{"old": true}\n', encoding="utf-8")  # an earlier run's, left out

    def measure(base: str, prompt: str) -> str:
        with noted.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"reply": "r", "n": 1, **note("Hello there.")}) + "\n")
        return prompt

    def summarize(prompt: str) -> dict[str, Any]:
        return {**summary([clip(1, first_byte_ms=3000, plays_ms=3000)]), "prompt": prompt}

    spoken: list[str] = []

    class Speaker:
        def speak(self, voice: str, text: str) -> Speech:
            spoken.append(text)
            quiet = np.zeros(RATE // 4)
            tone = 8000 * np.sin(2 * np.pi * 220 * np.arange(RATE // 2) / RATE)
            pcm = np.concatenate([quiet, tone, quiet]).astype("<i2").tobytes()
            return Speech(pcm, RATE, [])

    def voice_engine(voice: str, sample: Path | None) -> tuple[Speaker, str]:
        assert voice == "af_heart" and sample is None
        return Speaker(), voice

    monkeypatch.setattr(time_reply, "ask", lambda url, timeout=30: {"status": "ok"})
    monkeypatch.setattr(time_reply, "measure", measure)
    monkeypatch.setattr(time_reply, "summarize", summarize)
    monkeypatch.setattr(cli, "voice_engine", voice_engine)
    out = tmp_path / "out"
    code = long_reply.main([str(noted), "One?", "Two?", "-o", str(out), "--label", "t"])
    assert code == 0
    data = json.loads((out / "long-reply-t.json").read_text(encoding="utf-8"))
    assert [r["prompt"] for r in data["results"]] == ["One?", "Two?"]
    # 2 words in 0.5 s of speech, the 0.25 s of silence either side left out.
    assert data["results"][0]["own_rate_wpm"] == 240 and data["results"][0]["words"] == 2
    assert spoken == ["Hello there.", "Hello there."]
    assert "Reply 2: Two?" in (out / "long-reply-t.md").read_text(encoding="utf-8")


def test_run_without_the_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import long_reply

    from imageskin import time_reply

    def down(url: str, timeout: float = 30) -> dict[str, Any]:
        raise OSError("refused")

    monkeypatch.setattr(time_reply, "ask", down)
    assert long_reply.run("http://x", ["p"], tmp_path / "c", tmp_path, "t", "af_heart", None) == 1


def test_sentences_of() -> None:
    assert sentences_of(" One. Two? Three!  Four ") == ["One.", "Two?", "Three!", "Four"]
    assert sentences_of("") == []


def test_wait_for_app(monkeypatch: pytest.MonkeyPatch) -> None:
    from imageskin import time_reply

    answers: list[bool] = [False, False, True]

    def ask(url: str, timeout: float = 30) -> dict[str, Any]:
        if not answers.pop(0):
            raise OSError("refused")
        return {"status": "ok"}

    slept: list[float] = []
    monkeypatch.setattr(time_reply, "ask", ask)
    assert wait_for_app("http://x", 60, slept.append)
    assert slept == [3, 3]
    answers[:] = [False]
    assert not wait_for_app("http://x", 0, slept.append)  # no time left: one try only


def test_run_stops_when_the_chat_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import long_reply

    from imageskin import time_reply

    sent: list[str] = []
    locked = "The chat is locked until you accept a sample video at the end of setup."
    monkeypatch.setattr(time_reply, "ask", lambda url, timeout=30: {"status": "ok"})
    monkeypatch.setattr(time_reply, "measure", lambda base, prompt: sent.append(prompt))
    monkeypatch.setattr(
        time_reply,
        "summarize",
        lambda m: {**summary([]), "status": 409, "error": locked},
    )
    code = long_reply.run("http://x", ["One?", "Two?"], tmp_path / "c", tmp_path, "t", "v", None)
    assert code == 1 and sent == ["One?"]
    assert "The app refused the prompt (409)" in capsys.readouterr().out
