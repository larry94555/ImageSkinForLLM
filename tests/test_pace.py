from imageskin.pace import MAX_HOLD_S, ClipPlay, heard, hold_s


def test_the_next_reply_is_held_by_the_recent_replies_gaps() -> None:
    assert hold_s([]) == 0  # nothing measured yet
    assert hold_s([2.0, 6.5, 3.0]) == 3.0
    assert hold_s([135.0, 190.0]) == MAX_HOLD_S  # a slow voice still starts soon


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
