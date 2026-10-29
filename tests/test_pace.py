import logging
from pathlib import Path

import pytest

from imageskin.pace import (
    FIXED_S,
    KEEP_CLIPS,
    KEEP_REPLIES,
    LLM_WORDS_PER_S,
    PER_SPEECH_S,
    REPLY_WORDS,
    SPEECH_S_PER_WORD,
    ClipPlay,
    Machine,
    PaceStore,
    fit,
    gaps_ahead,
    heard,
)


def test_a_clip_s_time_is_a_fixed_cost_and_a_cost_per_second_of_speech() -> None:
    machine = Machine(fixed_s=1.0, per_speech_s=2.0, speech_s_per_word=0.5)
    assert machine.make_s(4) == 5.0  # 1 s, and twice its 2 s of speech


def test_the_machine_s_pace_is_fitted_from_its_clips() -> None:
    assert fit([]) == (FIXED_S, PER_SPEECH_S, SPEECH_S_PER_WORD)  # nothing measured yet
    # 0.5 s each, and 0.8 s per second of speech
    fixed, per_speech, per_word = fit([(2.1, 2.0, 5), (4.5, 5.0, 15), (8.5, 10.0, 30)])
    assert fixed == pytest.approx(0.5) and per_speech == pytest.approx(0.8)
    assert per_word == pytest.approx(17 / 50)


def test_clips_all_alike_are_fitted_as_a_cost_per_second() -> None:
    fixed, per_speech, per_word = fit([(3.0, 2.0, 6), (3.0, 2.0, 6)])
    assert (fixed, per_speech) == (0.0, 1.5) and per_word == pytest.approx(2 / 6)
    # A fit with a negative fixed cost (a large one per second) is all per second too.
    fixed, per_speech, _ = fit([(1.0, 2.0, 6), (9.0, 6.0, 18)])
    assert fixed == 0.0 and per_speech == 1.25


def test_clips_too_alike_in_length_are_fitted_as_a_cost_per_second() -> None:
    # The hosted machine's first reply with Pocket (R161): a line through these two gives
    # 1.72 s and 0.4 s a second of speech, so a 5.35 s clip foreseen at 3.9 s took 7.4 s.
    fixed, per_speech, _ = fit([(2.301, 1.435, 4), (2.723, 2.485, 6)])
    assert fixed == 0.0 and per_speech == pytest.approx(5.024 / 3.92)
    assert Machine(fixed, per_speech, 0.392, 1.0, 10).make_s(12) == pytest.approx(6.03, abs=0.01)


def test_the_pace_is_kept_across_restarts(tmp_path: Path) -> None:
    path = tmp_path / "replies" / "pace.json"
    store = PaceStore(path)
    assert store.machine() == Machine()  # nothing measured yet: R129's figures
    assert store.machine().reply_words == REPLY_WORDS
    assert store.machine().llm_words_per_s == LLM_WORDS_PER_S
    store.add([(2.1, 2.0, 5), (4.5, 5.0, 15), (8.5, 10.0, 30)], words=200, rate=3.0)
    again = PaceStore(path).machine()  # after a restart
    assert again.fixed_s == pytest.approx(0.5) and again.per_speech_s == pytest.approx(0.8)
    assert again.reply_words == 200 and again.llm_words_per_s == 3.0


def test_only_the_latest_clips_and_replies_are_kept(tmp_path: Path) -> None:
    store = PaceStore(tmp_path / "pace.json")
    for n in range(KEEP_REPLIES + 2):
        store.add([(2.0, 2.0, 6)] * 10, words=n, rate=0.0)
    store = PaceStore(tmp_path / "pace.json")
    assert len(store.clips) == KEEP_CLIPS and len(store.replies) == KEEP_REPLIES
    assert store.replies[-1] == (KEEP_REPLIES + 1, 0.0)
    assert store.machine().llm_words_per_s == LLM_WORDS_PER_S  # no rate measured


def test_a_pace_file_that_can_t_be_read_or_saved_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "pace.json"
    path.write_text("not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        store = PaceStore(path)
        assert store.machine() == Machine()
        path.unlink()
        path.mkdir()  # a folder in its place: it can't be written
        store.add([(2.0, 2.0, 6)], words=6, rate=3.0)
    assert caplog.messages == ["Could not read the reply pace", "Could not save the reply pace"]
    assert store.replies == [(6, 3.0)]  # still used in this run


def test_no_gaps_are_foreseen_when_the_reply_is_ready_or_made_fast_enough() -> None:
    fast = Machine(fixed_s=0.2, per_speech_s=0.5, speech_s_per_word=0.4, llm_words_per_s=4.0)
    # All of it ready to play.
    assert (
        gaps_ahead(
            fast, ahead_s=10, making=None, waiting_words=0, words_to_come=0, llm_words_per_s=4
        )
        == 0
    )
    # 6 s ready, 25 words waiting (made in 5.2 s), 25 to come (written in 6.25 s).
    assert (
        gaps_ahead(
            fast, ahead_s=6, making=None, waiting_words=25, words_to_come=25, llm_words_per_s=4
        )
        == 0
    )


def test_gaps_are_foreseen_when_clips_are_made_slower_than_they_play() -> None:
    slow = Machine(fixed_s=0.5, per_speech_s=1.5, speech_s_per_word=0.4)
    gaps = gaps_ahead(
        slow, ahead_s=2, making=None, waiting_words=10, words_to_come=50, llm_words_per_s=10
    )
    assert gaps > 5
    # The clip being made counts what is left of its time: begun 3 s ago, 6.5 s in all.
    making = gaps_ahead(
        slow, ahead_s=2, making=(3.0, 10), waiting_words=0, words_to_come=0, llm_words_per_s=10
    )
    assert making == pytest.approx(1.5)


def test_gaps_are_foreseen_when_the_llm_writes_slower_than_the_voice_speaks() -> None:
    fast = Machine(fixed_s=0.0, per_speech_s=0.1, speech_s_per_word=0.4)
    # 25 words for the next clip at 1 word a second: 25 s, against 2 s ready.
    gaps = gaps_ahead(
        fast, ahead_s=2, making=None, waiting_words=0, words_to_come=25, llm_words_per_s=1
    )
    assert gaps == pytest.approx(25 + 0.1 * 10 - 2)


def clip(sentence_at: float, started_at: float, listed_at: float, whole_at: float) -> ClipPlay:
    return ClipPlay(sentence_at, started_at, listed_at, whole_at, speech_s=2.0, words=6)


def test_a_reply_that_keeps_up_has_no_gaps() -> None:
    clips = [clip(0, 0, 1, 2), clip(0.5, 2, 2.5, 3.5), clip(1, 3.5, 4, 5)]
    pace = heard(clips, start=1)
    assert pace.gaps == []
    assert pace.words == 18 and pace.heard_s == 6 and pace.wpm == 180


def test_each_gap_has_its_cause() -> None:
    clips = [
        clip(0, 0, 1, 2),  # plays 1 to 3
        clip(0.5, 2, 4, 5),  # made behind the first: queued, 1 s gap
        clip(5.5, 5.5, 6.5, 7),  # its text came after the one before began: text late
        clip(6, 6.1, 9, 10),  # neither: slow to make
    ]
    gaps = heard(clips, start=1).gaps
    assert [(g.clip, g.seconds, g.cause) for g in gaps] == [
        (2, 1.0, "queued"),
        (3, 0.5, "text late"),
        (4, 0.5, "slow to make"),
    ]


def test_a_clip_played_while_written_ends_no_sooner_than_it_is_whole() -> None:
    clips = [clip(0, 0, 1, 5)]
    assert heard(clips, start=1).heard_s == 4
