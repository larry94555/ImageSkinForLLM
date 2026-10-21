from imageskin import reply_times
from imageskin.reply_times import ReplyTimes, note, note_llm, note_now


def test_nothing_is_kept_without_a_prompt_being_timed() -> None:
    note(first_token_at=1.0)
    note_llm({"prompt_n": 3})
    assert reply_times.current.get() is None


def test_the_first_token_and_sentence_are_kept_and_the_last_token_moves_on() -> None:
    times = ReplyTimes(received_at=0.0)
    token = reply_times.current.set(times)
    try:
        note(first_token_at=1.0, last_token_at=1.0, history_tokens=40)
        note(first_token_at=2.0, last_token_at=2.0, history_tokens=99)
        note_now("first_sentence_at")
        later = times.first_sentence_at
        note_now("first_sentence_at")
    finally:
        reply_times.current.reset(token)
    assert times.first_token_at == 1.0 and times.last_token_at == 2.0
    assert times.history_tokens == 40
    assert later is not None and times.first_sentence_at == later


def test_only_llama_servers_timings_are_kept() -> None:
    times = ReplyTimes(received_at=0.0)
    token = reply_times.current.set(times)
    try:
        note_llm("not a dict")
        assert times.llm is None
        note_llm({"prompt_n": 30, "cache_n": 100, "predicted_per_second": 6.2, "n_ctx": 4096})
    finally:
        reply_times.current.reset(token)
    assert times.llm == {"prompt_n": 30, "cache_n": 100, "predicted_per_second": 6.2}
    assert times.as_dict()["llm"] == times.llm
    assert times.as_dict()["received_at"] == 0.0
