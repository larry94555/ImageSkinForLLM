import numpy as np
import pytest

from imageskin.expression import openness
from imageskin.mouth_sync import (
    LOOK_AHEAD_S,
    LOOK_BACK_S,
    heard,
    mouth_lead_ms,
    mouth_opens,
    mouth_weights,
    rest_in_silence,
    start_at_voice,
    voice_onsets,
    voice_start,
)
from imageskin.visemes import ShapeTiming, frame_weights

RATE = 16000
FPS = 30.0


def voice(seconds: float, spans: list[tuple[float, float]]) -> np.ndarray:
    """Silence with a 220 Hz tone, the voice, in each span."""
    t = np.arange(int(seconds * RATE)) / RATE
    x = np.zeros_like(t)
    for a, b in spans:
        on = (t >= a) & (t < b)
        x[on] = 0.3 * np.sin(2 * np.pi * 220 * t[on])
    return x


def test_the_voice_is_heard_only_where_it_is_loud() -> None:
    loud = heard(voice(1.0, [(0.4, 0.6)]), RATE)
    assert len(loud) == 200  # 5 ms windows
    assert not loud[:80].any() and loud[80:120].all() and not loud[120:].any()


def test_nothing_is_heard_in_silence_or_in_no_audio() -> None:
    assert not heard(np.zeros(RATE), RATE).any()
    assert len(heard(np.zeros(10), RATE)) == 0


def test_a_late_timing_moves_back_to_where_the_voice_starts() -> None:
    loud = heard(voice(1.0, [(0.4, 0.6)]), RATE)
    assert voice_start(loud, 0.46, 0.0) == pytest.approx(0.4)  # Kokoro's timings start late


def test_an_early_timing_moves_on_to_where_the_voice_starts() -> None:
    loud = heard(voice(1.0, [(0.4, 0.6)]), RATE)
    assert voice_start(loud, 0.33, 0.0) == pytest.approx(0.4)  # the aligner's start early


def test_a_timing_with_no_voice_or_silence_near_it_is_kept() -> None:
    loud = heard(voice(2.0, [(0.2, 1.0)]), RATE)
    # Already heard back past LOOK_BACK_S, or back to the sound before: a quiet "s" running on.
    assert voice_start(loud, 0.2 + LOOK_BACK_S + 0.1, 0.0) is None
    assert voice_start(loud, 0.5, 0.45) is None
    # Nothing heard within LOOK_AHEAD_S.
    assert voice_start(loud, 1.5 - LOOK_AHEAD_S, 0.0) is None
    assert voice_start(loud, 3.0, 0.0) is None  # past the audio's end
    # Heard from the clip's very start.
    assert voice_start(heard(voice(1.0, [(0.0, 0.5)]), RATE), 0.05, 0.0) == 0.0


def test_each_word_after_a_pause_starts_where_its_voice_does() -> None:
    samples = voice(1.6, [(0.3, 0.6), (0.92, 1.3)])
    shapes = [
        ShapeTiming("rest", 0.0, 0.36),
        ShapeTiming("AA", 0.36, 0.6),  # late, as Kokoro's
        ShapeTiming("rest", 0.6, 0.85),
        ShapeTiming("EE", 0.85, 1.0),  # early, as the aligner's
        ShapeTiming("OO", 1.0, 1.3),  # straight after a sound: left alone
        ShapeTiming("rest", 1.3, 1.6),
    ]
    assert start_at_voice(shapes, samples, RATE) == [
        ShapeTiming("rest", 0.0, 0.3),
        ShapeTiming("AA", 0.3, 0.6),
        ShapeTiming("rest", 0.6, 0.92),
        ShapeTiming("EE", 0.92, 1.0),
        ShapeTiming("OO", 1.0, 1.3),
        ShapeTiming("rest", 1.3, 1.6),
    ]


def test_a_word_is_left_alone_when_its_voice_is_already_where_it_starts() -> None:
    samples = voice(1.0, [(0.3, 0.6)])
    shapes = [ShapeTiming("rest", 0.0, 0.3), ShapeTiming("AA", 0.3, 0.6)]
    assert start_at_voice(shapes, samples, RATE) == shapes
    # A voice heard only after the sound's end doesn't move it past its end.
    late = [ShapeTiming("rest", 0.0, 0.2), ShapeTiming("AA", 0.2, 0.25)]
    assert start_at_voice(late, samples, RATE) == late


def test_a_word_after_a_gap_in_the_timings_moves_too() -> None:
    samples = voice(1.0, [(0.3, 0.6)])
    shapes = [ShapeTiming("AA", 0.35, 0.6)]  # no rest before it
    assert start_at_voice(shapes, samples, RATE) == [ShapeTiming("AA", 0.3, 0.6)]


def test_the_mouth_never_opens_before_the_voice() -> None:
    """R128's test: a clip with a known silence at its start, its timings 100 ms early, opens
    its mouth within 80 ms of the first sound, and not before it."""
    samples = voice(1.5, [(0.5, 1.0)])
    shapes = [
        ShapeTiming("rest", 0.0, 0.4),
        ShapeTiming("AA", 0.4, 1.0),
        ShapeTiming("rest", 1.0, 1.5),
    ]
    n = round(1.5 * FPS)
    before = mouth_lead_ms(frame_weights(shapes, n, FPS), samples, RATE, FPS)
    lead = mouth_lead_ms(mouth_weights(shapes, samples, RATE, n, FPS), samples, RATE, FPS)
    assert before is not None and before > 80  # the frames alone follow the early timings
    assert lead is not None and -80 <= lead <= 0


def test_the_lead_is_the_largest_over_the_clip() -> None:
    track_open = [{"rest": 1.0}] * 30 + [{"AA": 1.0}] * 15  # opens at 1.0 s
    samples = voice(1.5, [(1.05, 1.5)])
    assert mouth_lead_ms(track_open, samples, RATE, FPS) == 50
    # A mouth that never opens has no lead, nor a clip with no voice.
    assert mouth_lead_ms([{"rest": 1.0}] * 45, samples, RATE, FPS) is None
    assert mouth_lead_ms([{"rest": 1.0}] * 45, np.zeros(RATE), RATE, FPS) is None


def test_voice_onsets_are_the_start_and_each_word_after_a_pause() -> None:
    samples = voice(2.0, [(0.2, 0.5), (0.55, 0.8), (1.2, 1.5)])  # 50 ms, then 400 ms apart
    onsets = [(round(a, 3), round(b, 3)) for a, b in voice_onsets(samples, RATE)]
    assert onsets == [(0.0, 0.2), (0.8, 1.2)]


def test_the_mouth_opens_on_the_first_open_frame_after_a_closed_one() -> None:
    assert mouth_opens([0.0, 0.0, 0.5, 0.5], FPS, 0.0, 0.07) == pytest.approx(2 / FPS)
    assert mouth_opens([0.5, 0.5, 0.5, 0.5], FPS, 0.0, 0.07) == 0.0  # open through the silence
    assert mouth_opens([0.0, 0.0, 0.0, 0.0], FPS, 0.0, 0.07) is None  # never opens


def test_a_pause_shortened_by_a_late_timing_still_keeps_the_mouth_closed() -> None:
    # Kokoro's "time, a": the comma's 125 ms rest becomes 75 ms once "a" moves back to its
    # voice, under PAUSE_S, but the mouth still waits for the voice (found measuring R128).
    samples = voice(2.0, [(0.9, 1.175), (1.525, 1.8)])
    shapes = [
        ShapeTiming("AA", 0.9, 1.175),
        ShapeTiming("MBP", 1.175, 1.45),
        ShapeTiming("rest", 1.45, 1.575),
        ShapeTiming("AA", 1.575, 1.8),
        ShapeTiming("rest", 1.8, 2.0),
    ]
    weights = mouth_weights(shapes, samples, RATE, 60, FPS)
    assert all(w.get("AA", 0) < 0.01 for w in weights[40:46])  # from 1.33 s until 1.525 s
    assert weights[46]["AA"] > 0.5


def test_the_mouth_closes_in_a_pause_the_timings_leave_out() -> None:
    """Codex's review: the audio has a 250 ms silence between two words, but the timings run
    the first word's last sound on into it and leave only 50 ms before the next one, under
    visemes.PAUSE_S. The mouth still closes in the silence and opens no earlier than the voice."""
    samples = voice(2.0, [(0.2, 0.7), (0.95, 1.5)])
    shapes = [
        ShapeTiming("rest", 0.0, 0.2),
        ShapeTiming("AA", 0.2, 0.85),  # runs 150 ms on into the silence
        ShapeTiming("rest", 0.85, 0.9),
        ShapeTiming("EH", 0.9, 1.5),  # starts 50 ms before the voice comes back
        ShapeTiming("rest", 1.5, 2.0),
    ]
    n = round(2.0 * FPS)
    before = mouth_lead_ms(frame_weights(shapes, n, FPS), samples, RATE, FPS)
    weights = mouth_weights(shapes, samples, RATE, n, FPS)
    track = [openness(w) for w in weights]
    assert min(track[round(0.7 * FPS) : round(0.95 * FPS)]) < 0.1  # closed in the silence
    lead = mouth_lead_ms(weights, samples, RATE, FPS)
    assert before is not None and before >= 250  # open through the whole pause, before
    assert lead is not None and -80 <= lead <= 0


def test_sounds_in_a_silence_are_cut_to_either_side_of_it() -> None:
    shapes = [
        ShapeTiming("AA", 0.0, 0.5),
        ShapeTiming("IH", 0.5, 0.6),  # wholly in the silence
        ShapeTiming("rest", 0.6, 0.62),
        ShapeTiming("EE", 0.62, 1.0),
    ]
    assert rest_in_silence(shapes, [(0.4, 0.7)]) == [
        ShapeTiming("AA", 0.0, 0.4),
        ShapeTiming("rest", 0.6, 0.62),
        ShapeTiming("EE", 0.7, 1.0),
    ]


def test_a_mouth_open_through_a_pause_leads_by_the_whole_pause() -> None:
    samples = voice(1.5, [(0.1, 0.5), (1.0, 1.4)])
    assert mouth_lead_ms([{"AA": 1.0}] * 45, samples, RATE, FPS) == 500
    assert mouth_opens([0.5] * 10, FPS, 0.2, 0.25) == 0.2
