"""Only the laptops listed on the host can sign in as the administrator (roadmap R163)."""

import base64
import logging
import os
import re
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient

from imageskin import admin, admin_laptops
from imageskin.admin import AdminRefused, AdminSignIns, Secret, hash_password
from imageskin.admin_laptops import (
    AdminLaptops,
    LaptopProof,
    laptop_id,
    read_laptops,
    verify,
)
from imageskin.app import create_app
from imageskin.config import ConfigError, load_settings

ROOT = Path(__file__).resolve().parent.parent


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    # A new modification time each write, as an editor's save would make, even within one tick.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


@pytest.fixture(autouse=True)
def quick_dummy(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cheaper dummy hash, as in test_admin.py, so the many sign-ins here run quickly."""
    monkeypatch.setattr(admin, "SCRYPT_N", 2**4)
    cheap = Secret("hash", hash_password("never typed"))
    monkeypatch.undo()
    monkeypatch.setattr(admin, "_dummy", lambda: cheap)


class Laptop:
    """A laptop's browser: a P-256 key, as WebCrypto makes it (R164)."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.spki = self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.id = laptop_id(self.spki)

    def prove(self, challenge: str) -> LaptopProof:
        # WebCrypto's ECDSA signature is r and s, 32 bytes each, not DER.
        r, s = decode_dss_signature(self.key.sign(challenge.encode(), ec.ECDSA(hashes.SHA256())))
        raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return LaptopProof(
            base64.b64encode(self.spki).decode(), challenge, base64.b64encode(raw).decode()
        )

    def body(self, challenge: str) -> dict[str, str]:
        proof = self.prove(challenge)
        return {
            "public_key": proof.public_key,
            "challenge": proof.challenge,
            "signature": proof.signature,
        }


def listing(*laptops: Laptop) -> str:
    return "".join(
        f'[[laptop]]\nname = "laptop {n}"\nid = "{lt.id}"\n' for n, lt in enumerate(laptops)
    )


@pytest.fixture
def home(tmp_path: Path) -> Path:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    return tmp_path


def refused_reasons(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [
        {k: getattr(r, k, None) for k in ("reason", "laptop", "password_ok")}
        for r in caplog.records
        if r.getMessage() == "Admin sign-in refused"
    ]


# The laptop ID and the proof


def test_the_laptop_id_is_the_keys_fingerprint_in_groups_of_four() -> None:
    laptop = Laptop()
    assert re.fullmatch(r"LT(-[A-Z2-7]{4}){5}", laptop.id)
    assert laptop.id == laptop_id(laptop.spki)
    assert Laptop().id != laptop.id
    # Fixed for a fixed key, so R164's browser code can be checked against the same value.
    assert laptop_id(b"a public key") == "LT-BNZU-R6QD-RFYM-JDWA-PTLT"


def test_a_good_proof_gives_the_laptops_id() -> None:
    laptop = Laptop()
    assert verify(laptop.prove("a challenge")) == laptop.id


@pytest.mark.parametrize("change", ["challenge", "signature", "key", "not base64", "rsa", "short"])
def test_a_bad_proof_is_refused(change: str) -> None:
    laptop = Laptop()
    proof = laptop.prove("a challenge")
    if change == "challenge":
        proof = LaptopProof(proof.public_key, "another challenge", proof.signature)
    elif change == "signature":
        proof = LaptopProof(
            proof.public_key, proof.challenge, Laptop().prove("a challenge").signature
        )
    elif change == "key":
        proof = LaptopProof(Laptop().prove("x").public_key, proof.challenge, proof.signature)
    elif change == "not base64":
        proof = LaptopProof("not base64!", proof.challenge, proof.signature)
    elif change == "rsa":
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=1024).public_key()
        der = rsa_key.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        proof = LaptopProof(base64.b64encode(der).decode(), proof.challenge, proof.signature)
    else:
        proof = LaptopProof(proof.public_key, proof.challenge, base64.b64encode(b"x" * 10).decode())
    with pytest.raises(ValueError):
        verify(proof)


# The file


def test_no_file_lets_any_laptop_in(tmp_path: Path) -> None:
    assert read_laptops(tmp_path / "admin-laptops.toml") is None
    laptops = AdminLaptops(tmp_path / "admin-laptops.toml")
    assert laptops.check(None) == (None, None)
    assert laptops.still_allowed(None)


def test_the_file_lists_laptops_by_id(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "admin-laptops.toml"
    write(path, '[[laptop]]\nname = "home"\nid = "lt-aaaa-bbbb "\n[[laptop]]\nname = "no id"\n')
    assert read_laptops(path) == frozenset({"LT-AAAA-BBBB"})
    assert "Admin laptops file has an entry with no id" in caplog.text


@pytest.mark.parametrize("text", ["", "not = [toml", "laptop = 3\n"])
def test_an_empty_or_broken_file_lets_no_laptop_in(
    tmp_path: Path, text: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "admin-laptops.toml"
    write(path, text)
    assert read_laptops(path) == frozenset()
    if text:
        assert "Could not read the admin laptops file" in caplog.text


def test_a_folder_in_place_of_the_file_lets_no_laptop_in(tmp_path: Path) -> None:
    path = tmp_path / "admin-laptops.toml"
    path.mkdir()
    assert read_laptops(path) == frozenset()


def test_the_file_is_read_again_only_when_it_changes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "admin-laptops.toml"
    laptops = AdminLaptops(path)
    one, two = Laptop(), Laptop()
    with caplog.at_level(logging.INFO):
        assert laptops.allowed() is None
        write(path, listing(one))
        assert laptops.allowed() == frozenset({one.id})
        assert laptops.allowed() == frozenset({one.id})
        write(path, listing(one, two))
        assert laptops.allowed() == frozenset({one.id, two.id})
    reads = [r for r in caplog.records if r.getMessage() == "Admin laptops file read"]
    assert [(r.laptops, r.changed) for r in reads] == [(1, True), (2, True)]  # type: ignore[attr-defined]


def test_the_committed_example_lists_no_laptop() -> None:
    assert read_laptops(ROOT / "admin-laptops.example.toml") == frozenset()
    assert "admin-laptops.toml" in (ROOT / ".gitignore").read_text().splitlines()


# Challenges


def test_a_challenge_is_good_once_and_for_a_minute(tmp_path: Path) -> None:
    clock = Clock()
    laptop = Laptop()
    path = tmp_path / "admin-laptops.toml"
    write(path, listing(laptop))
    laptops = AdminLaptops(path, clock=clock)
    challenge = laptops.challenge()
    assert laptops.check(laptop.prove(challenge)) == (None, laptop.id)
    assert laptops.check(laptop.prove(challenge)) == ("challenge expired", None)  # reused
    late = laptops.challenge()
    clock.now += 61
    assert laptops.check(laptop.prove(late)) == ("challenge expired", None)
    assert laptops.check(laptop.prove("made up")) == ("challenge expired", None)


def test_many_challenges_are_not_all_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin_laptops, "CHALLENGES_KEPT", 3)
    clock = Clock()
    laptops = AdminLaptops(tmp_path / "admin-laptops.toml", clock=clock)
    old = [laptops.challenge() for _ in range(3)]
    clock.now += 61
    newest = laptops.challenge()
    assert list(laptops._challenges) == [newest]
    for _ in range(5):
        laptops.challenge()
    assert len(laptops._challenges) <= 3 and old[0] not in laptops._challenges


# Signing in


def test_a_listed_laptop_signs_in(home: Path) -> None:
    laptop = Laptop()
    write(home / "admin-laptops.toml", listing(laptop))
    sign_ins = AdminSignIns(home / "admin.toml")
    token = sign_ins.sign_in("first secret", "1.2.3.4", laptop.prove(sign_ins.laptops.challenge()))
    assert sign_ins.signed_in(token)


def test_an_unlisted_laptop_is_refused_even_with_the_right_password(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    listed, other = Laptop(), Laptop()
    write(home / "admin-laptops.toml", listing(listed))
    sign_ins = AdminSignIns(home / "admin.toml")
    with pytest.raises(AdminRefused) as refused:
        sign_ins.sign_in("first secret", "1.2.3.4", other.prove(sign_ins.laptops.challenge()))
    assert str(refused.value) == f"Admin login failed with error code {refused.value.code}."
    with pytest.raises(AdminRefused):
        sign_ins.sign_in("a guess", "1.2.3.4", other.prove(sign_ins.laptops.challenge()))
    assert refused_reasons(caplog) == [
        {"reason": "laptop not listed", "laptop": other.id, "password_ok": True},
        {"reason": "laptop not listed", "laptop": other.id, "password_ok": False},
    ]


def test_each_laptop_cause_is_logged(home: Path, caplog: pytest.LogCaptureFixture) -> None:
    laptop = Laptop()
    write(home / "admin-laptops.toml", listing(laptop))
    sign_ins = AdminSignIns(home / "admin.toml", clock=Clock())
    challenge = sign_ins.laptops.challenge()
    bad = LaptopProof(
        laptop.prove(challenge).public_key, challenge, Laptop().prove(challenge).signature
    )
    for proof in [None, laptop.prove("made up"), bad]:
        with pytest.raises(AdminRefused):
            sign_ins.sign_in("first secret", f"10.0.0.{len(caplog.records)}", proof)
    assert [r["reason"] for r in refused_reasons(caplog)] == [
        "no laptop proof",
        "challenge expired",
        "bad laptop proof",
    ]


def test_an_empty_file_lets_no_laptop_in(home: Path) -> None:
    write(home / "admin-laptops.toml", "# no laptops yet\n")
    sign_ins = AdminSignIns(home / "admin.toml")
    with pytest.raises(AdminRefused) as refused:
        sign_ins.sign_in("first secret", "1.2.3.4", Laptop().prove(sign_ins.laptops.challenge()))
    assert refused.value.reason == "laptop not listed"


def test_laptop_failures_count_towards_the_wait(home: Path) -> None:
    write(home / "admin-laptops.toml", listing(Laptop()))
    sign_ins = AdminSignIns(home / "admin.toml", clock=Clock())
    for _ in range(5):
        with pytest.raises(AdminRefused):
            sign_ins.sign_in("first secret", "1.2.3.4")
    with pytest.raises(AdminRefused) as refused:
        sign_ins.sign_in("first secret", "1.2.3.4")
    assert refused.value.reason == "waiting"


def test_a_laptop_taken_out_of_the_file_is_signed_out_at_once(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    one, two = Laptop(), Laptop()
    path = home / "admin-laptops.toml"
    write(path, listing(one, two))
    sign_ins = AdminSignIns(home / "admin.toml")
    token = sign_ins.sign_in("first secret", "1.2.3.4", one.prove(sign_ins.laptops.challenge()))
    kept = sign_ins.sign_in("first secret", "1.2.3.5", two.prove(sign_ins.laptops.challenge()))
    write(path, listing(two))
    with caplog.at_level(logging.INFO):
        assert not sign_ins.signed_in(token)
    assert sign_ins.ended(token) == "laptop removed"
    assert sign_ins.signed_in(kept)
    assert "laptop removed" in [getattr(r, "why", None) for r in caplog.records]


def test_a_list_made_while_signed_in_ends_a_sign_in_made_with_none(home: Path) -> None:
    sign_ins = AdminSignIns(home / "admin.toml")
    token = sign_ins.sign_in("first secret", "1.2.3.4")
    write(home / "admin-laptops.toml", listing(Laptop()))
    assert not sign_ins.signed_in(token)
    assert sign_ins.ended(token) == "laptop removed"


# The API


def test_the_api_signs_in_only_a_listed_laptop(
    home: Path, caplog: pytest.LogCaptureFixture
) -> None:
    listed, other = Laptop(), Laptop()
    write(home / "admin-laptops.toml", listing(listed))
    app = create_app(home)
    browser = TestClient(app, client=("198.51.100.7", 40001))

    def sign_in(laptop: Laptop | None, password: str = "first secret") -> dict[str, object]:
        body: dict[str, object] = {"password": password}
        if laptop:
            body["laptop"] = laptop.body(browser.get("/api/admin/challenge").json()["challenge"])
        response = browser.post("/api/admin/sign-in", json=body)
        assert response.status_code in (200, 401)
        return response.json()  # type: ignore[no-any-return]

    failed = [sign_in(other), sign_in(None)]
    for answer in failed:
        assert set(answer) == {"detail", "code"}
        assert answer["detail"] == f"Admin login failed with error code {answer['code']}."
    assert sign_in(listed) == {"signed_in": True}
    session = browser.get("/api/admin/session").json()
    assert session["signed_in"] is True and "laptop" not in str(session)
    assert [r["reason"] for r in refused_reasons(caplog)] == [
        "laptop not listed",
        "no laptop proof",
    ]


def test_the_api_lets_any_laptop_in_with_no_file(home: Path) -> None:
    browser = TestClient(create_app(home))
    assert browser.post("/api/admin/sign-in", json={"password": "first secret"}).json() == {
        "signed_in": True
    }


def test_the_api_reads_the_laptops_file_from_the_config(tmp_path: Path) -> None:
    write(tmp_path / "admin.toml", 'password = "first secret"\n')
    elsewhere = tmp_path / "elsewhere.toml"
    write(elsewhere, "# none listed\n")
    browser = TestClient(create_app(tmp_path, admin_laptops_file=elsewhere))
    refused = browser.post("/api/admin/sign-in", json={"password": "first secret"})
    assert refused.status_code == 401


def test_the_config_takes_a_laptops_file(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('admin_laptops_file = "/etc/imageskin/admin/admin-laptops.toml"\n')
    assert load_settings(config).admin_laptops_file == "/etc/imageskin/admin/admin-laptops.toml"
    config.write_text("admin_laptops_file = 3\n")
    with pytest.raises(ConfigError, match="admin_laptops_file"):
        load_settings(config)
