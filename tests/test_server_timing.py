from imageskin import server_timing


def test_steps_are_collected_added_up_and_sent_as_a_header() -> None:
    with server_timing.collecting() as steps:
        with server_timing.step("convert"):
            pass
        with server_timing.step("faces"):
            pass
        with server_timing.step("faces"):  # a step timed twice is added up
            pass
    assert list(steps) == ["convert", "faces"]
    steps.update(convert=12.34, faces=402.0)
    assert server_timing.header(steps) == "convert;dur=12.3, faces;dur=402.0"
    assert server_timing.parse(server_timing.header(steps)) == {"convert": 12.3, "faces": 402.0}


def test_a_step_outside_a_request_is_not_kept() -> None:
    with server_timing.step("faces"):
        pass
    with server_timing.collecting() as steps:
        pass
    assert steps == {}


def test_entries_without_a_time_are_left_out() -> None:
    header = 'cache;desc="hit", db;dur=53, bad;dur=x, ;dur=1, app;desc=a;dur=47.5'
    assert server_timing.parse(header) == {"db": 53.0, "app": 47.5}
    assert server_timing.parse(None) == {}
