"""« Ouvre le navigateur et montre-moi un site » hors mode Agent.

Le navigateur piloté par Tontolo (outils `browser_*`) n'existe qu'en mode Agent. Hors de ce
mode, une demande d'ouverture reçoit quand même une vraie réponse : le modèle donne UN lien
direct et l'application affiche sous la réponse un bouton « Ouvrir » (navigateur de
l'appareil), au lieu du refus « je suis une IA textuelle »."""

from __future__ import annotations

import re

_OPEN = re.compile(
    r"\b(ouvr\w*|affich\w*|montr\w*|lance\w*|open|show|launch|go to|sokafy|asehoy|alefaso)\b"
    r".{0,45}?\b(navigateur|browser|site|sites|lien|liens|link|links|page web|url|"
    r"tranonkala|rohy|pejy)\b", re.I | re.S)
_URL = re.compile(r"https?://[^\s<>\")\]]+", re.I)

HINT = (
    "L'utilisateur veut qu'on ouvre un site dans son navigateur. Tu ne pilotes pas le "
    "navigateur toi-même (c'est le rôle du mode Agent), MAIS l'application affiche sous ta "
    "réponse un bouton « Ouvrir » pour le lien que tu donnes. Donne donc UN lien direct "
    "(https://…) bien choisi, avec une courte phrase, et ne dis jamais que tu ne peux pas "
    "l'ouvrir ni que tu n'es qu'une IA textuelle. S'il veut naviguer dans les pages, "
    "précise une seule fois que le mode Agent le permet."
)


def wants_open(text: str) -> bool:
    return bool(text) and len(text) < 600 and _OPEN.search(text) is not None


def links_in(answer: str, limit: int = 3) -> list[str]:
    """Premiers liens distincts de la réponse (sans ponctuation finale)."""
    out: list[str] = []
    for m in _URL.finditer(answer or ""):
        url = m.group(0).rstrip(".,;:!?»'")
        if url not in out:
            out.append(url)
        if len(out) >= limit:
            break
    return out
