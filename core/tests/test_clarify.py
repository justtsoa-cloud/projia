"""Les questions de précision ne sont posées que si l'information manque vraiment."""

from __future__ import annotations

import pytest

from tontolo.creator.clarify import questions_for


def asked(kind: str, text: str) -> list[str]:
    return [q["question"] for q in questions_for(kind, text)]


@pytest.mark.parametrize("text", [
    "Fais un sujet de révision en PDF de deux pages pour la classe de sixième",
    "Un PDF de deux pages sur les fractions pour les élèves de 6ème",
    "Make a two-page PDF on fractions for 9th grade students",
    "Ataovy PDF pejy roa momba ny ampahany ho an'ny mpianatra",
    "Un document court pour des CM2 sur le cycle de l'eau",
])
def test_precise_requests_are_not_questioned(text: str) -> None:
    assert asked("pdf", text) == []


def test_only_the_missing_piece_is_asked() -> None:
    # La longueur est dite (en lettres), le public manque : une seule question.
    assert asked("pdf", "Un sujet de révision en PDF de deux pages sur les fractions") == [
        "Pour quel public ?"]
    # Le public est dit, la longueur manque.
    assert asked("pdf", "Un PDF sur les fractions pour la classe de cinquième") == [
        "Quelle longueur ?"]
    # Rien n'est dit : les deux.
    assert len(asked("pdf", "Un PDF sur les fractions")) == 2
