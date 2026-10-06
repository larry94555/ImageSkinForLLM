import pytest
from lip_shapes import SHAPES, mix, soften, top_two

from imageskin.visemes import CONTACT
from imageskin.visemes import SHAPES as SHAPE_NAMES


def test_every_app_shape_has_a_liveportrait_edit() -> None:
    assert set(SHAPES) == set(SHAPE_NAMES)
    assert all(SHAPES[name].ratio is not None for name in CONTACT)


def test_mix_uses_photo_ratio_for_rest() -> None:
    controls, ratio = mix({"rest": 0.5, "OO": 0.5}, photo_ratio=0.2)
    assert ratio == pytest.approx(0.5 * 0.2 + 0.5 * SHAPES["OO"].ratio)  # type: ignore[operator]
    assert controls == {"purse": pytest.approx(12.0)}


def test_top_two() -> None:
    assert top_two({"AA": 1.0}) == ("AA", "AA", 0.0)
    a, b, t = top_two({"AA": 0.6, "OO": 0.3, "EE": 0.1})
    assert (a, b) == ("AA", "OO")
    assert t == pytest.approx(1 / 3)


def test_soften_moves_part_way_from_rest() -> None:
    controls, ratio = soften("OH", 0.5, photo_ratio=0.1)
    assert controls == {"purse": pytest.approx(7.0)}
    assert ratio == pytest.approx(0.1 + 0.5 * (0.30 - 0.1))
    assert soften("OH", 1.0, 0.1) == (SHAPES["OH"].controls, pytest.approx(0.30))
    assert soften("rest", 0.4, 0.2) == ({}, pytest.approx(0.2))


def test_soften_keeps_lip_contact() -> None:
    controls, ratio = soften("MBP", 0.4, photo_ratio=0.2)
    assert ratio == 0.0
    assert controls == {"open": pytest.approx(-6.0)}


def test_soften_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        soften("AA", 1.5, 0.0)


def test_mix_applies_strength() -> None:
    controls, ratio = mix({"OO": 1.0}, photo_ratio=0.0, strength=0.5)
    assert controls == {"purse": pytest.approx(12.0)}
    assert ratio == pytest.approx(0.06)
