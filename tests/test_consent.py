import json
import logging
from pathlib import Path

import pytest

from imageskin.consent import FILENAME, Consent, load_consent, save_consent


def test_no_file_means_not_agreed(tmp_path: Path) -> None:
    assert load_consent(tmp_path) == Consent(agreed=False)


def test_saved_consent_is_loaded(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="imageskin.consent"):
        saved = save_consent(tmp_path / "new-home")
    assert saved.agreed and saved.agreed_at
    assert load_consent(tmp_path / "new-home") == saved
    assert any(r.getMessage() == "Consent recorded" for r in caplog.records)


@pytest.mark.parametrize("text", ["not json", "[]", json.dumps({"agreed_at": 5})])
def test_unreadable_file_means_not_agreed(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / FILENAME).write_text(text)
    with caplog.at_level(logging.ERROR, logger="imageskin.consent"):
        assert load_consent(tmp_path) == Consent(agreed=False)
    assert caplog.records
