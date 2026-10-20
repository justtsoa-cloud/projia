"""Détection d'un « refus » d'image par un modèle de texte : « je ne peux pas générer
d'images ». Sert au basculement automatique vers la génération d'image."""

from __future__ import annotations

import re

_REFUSAL = re.compile(
    r"(je ne (peux|suis|saurais|sais) pas( directement| vraiment)?( en mesure de| capable de)? "
    r"(g[ée]n[ée]rer|cr[ée]er|produire|dessiner|fournir|afficher)[^.\n]{0,50}"
    r"(image|photo|illustration|dessin|visuel)"
    r"|je n'ai pas (la capacit[ée]|la possibilit[ée]|les moyens) de "
    r"(g[ée]n[ée]rer|cr[ée]er)[^.\n]{0,40}(image|photo|illustration)"
    r"|(ne|n') ?(peux|puis|suis|sais)[^.\n]{0,20}pas[^.\n]{0,30}"
    r"(g[ée]n[ée]rer|cr[ée]er)[^.\n]{0,15}d'?images?"
    r"|(je )?(ne )?g[ée]n[èe]re pas d'images?"
    r"|prompt (pr[êe]t|[àa] coller|[àa] copier)[^.\n]{0,80}"
    r"(midjourney|dall|stable diffusion|leonardo)"
    r"|coll(er|ez)[^.\n]{0,60}g[ée]n[ée]rateur d'images?"
    r"|(i (can't|cannot|can not|am unable to|'m unable to|do not|don't) (directly )?"
    r"(generate|create|produce|make|draw)[^.\n]{0,30}(images?|pictures?|photos?))"
    r"|as an ai[^.\n]{0,80}(can't|cannot|unable)[^.\n]{0,30}images?"
    r"|(?:\[m[ée]dia:[^\]]*\])[^.\n]{0,30}placeholder)",
    re.I,
)
_IMAGE_WORDS = re.compile(
    r"\b(images?|photos?|dessins?|illustrations?|logos?|affiches?|visuels?|portraits?|paysages?|"
    r"pictures?|wallpapers?|fonds? d'[ée]cran|sary)\b", re.I)


# Le modèle de texte *prétend* avoir créé l'image (« I've generated an image… ») alors qu'il
# ne sait produire que du texte : c'est un échec déguisé, à traiter comme un refus.
_FALSE_CLAIM = re.compile(
    r"\b(i(?:'ve| have)|i've just|i just) (generated|created|drawn|made|produced|rendered)"
    r"[^.\n]{0,25}\b(images?|pictures?|illustrations?|drawings?|photos?)"
    r"|here(?:'s| is) (the|your|an?) (generated )?(images?|pictures?|illustrations?|drawings?)"
    r"|j'ai (g[ée]n[ée]r[ée]|cr[ée][ée]|dessin[ée]|r[ée]alis[ée])[^.\n]{0,25}"
    r"\b(images?|photos?|illustrations?|dessins?)"
    r"|voici (l'|votre |ton |une )?(image|illustration|dessin|photo)\b",
    re.I,
)


def looks_like_image_refusal(answer: str) -> bool:
    """Refus explicite, ou fausse affirmation d'avoir généré l'image."""
    return bool(answer and (_REFUSAL.search(answer) or _FALSE_CLAIM.search(answer)))


def mentions_image(text: str) -> bool:
    return bool(text and _IMAGE_WORDS.search(text))


_PRESERVE = re.compile(
    r"sans (rien )?(changer|modifier|alt[ée]rer|toucher|d[ée]former)|ne (change|modifie|touche|"
    r"d[ée]forme)\w* pas|\b(garde|gardez|conserve|conservez|respecte|pr[ée]serve)\b|"
    r"identique|inchang[ée]|m[êe]me (personne|visage|photo|composition|cadrage)|fid[èe]le|"
    r"without changing|keep the (same|person)|don't change|do not change", re.I)


def preserves_subject(text: str) -> bool:
    """La consigne demande de conserver la personne / la composition de la photo."""
    return bool(text and _PRESERVE.search(text))
