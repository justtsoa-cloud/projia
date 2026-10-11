"""Règle de version : chaque chiffre de 0 à 9 (0.2.9 → 0.3.0, 0.9.9 → 1.0.0)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"
_spec = importlib.util.spec_from_file_location("bump_version", _PATH)
assert _spec and _spec.loader
bv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bv)


@pytest.mark.parametrize(("now", "nxt"), [("0.2.8", "0.2.9"), ("0.2.9", "0.3.0"),
                                          ("0.9.9", "1.0.0"), ("1.4.9", "1.5.0")])
def test_next_version(now: str, nxt: str) -> None:
    assert bv.fmt(bv.next_version(bv.parse(now))) == nxt


def test_allowed_jumps() -> None:
    allowed = {bv.fmt(v) for v in bv.allowed_after(bv.parse("0.4.7"))}
    assert allowed == {"0.4.8", "0.5.0", "1.0.0"}
    assert {bv.fmt(v) for v in bv.allowed_after(bv.parse("0.9.9"))} == {"1.0.0"}
    with pytest.raises(ValueError):
        bv.parse("0.2.10")


def test_repository_versions_agree() -> None:
    found, build = bv.current()
    assert len(set(found.values())) == 1 and build > 0
