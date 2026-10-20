"""Index sémantique local, commun à la mémoire et au cache de réponses.

Un seul principe pour deux usages :
- **qui est l'utilisateur** (mémoire : faits durables, consignes) ;
- **ce qu'on lui a déjà répondu** (cache : question → réponse).

Vecteurs creux de mots (racines tronquées) et de trigrammes de caractères, normalisés
(sans accents) : aucune dépendance, aucun réseau, quelques microsecondes par texte, et ils
rapprochent « Qu'est-ce que la photosynthèse ? » de « explique la photosynthese » en français,
anglais ou malgache. Rien ne sort de l'appareil.

Cache de réponses, prudent par construction :
- **réutilisation** seulement pour une question autonome (pas « et pour le Japon ? »), sans
  lien avec le moment (actualité, météo, prix…), sans « je / mon », sans photo, aux mêmes
  nombres, quasi identique (cosinus ≥ REUSE) et récente ;
- **aide** : une question proche (≥ RELATED) apporte l'ancienne réponse en contexte, à vérifier ;
- Régénérer ne passe jamais par le cache ; effacer une discussion efface ses réponses.
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
import zlib
from typing import Any

REUSE = 0.93          # quasi la même question
RELATED = 0.62        # question voisine : ancienne réponse donnée en contexte
MAX_AGE = 30 * 86400  # au-delà, une réponse n'est plus réutilisée telle quelle
MAX_ANSWERS = 2000    # taille de l'index (les plus anciennes et moins utiles partent)
MIN_ANSWER = 40

_STOP = frozenset(" ".join((
    "le la les un une des de du et ou a au aux en pour par sur avec dans que qui quoi est "
    "sont ce cet cette ces se sa son ses the an of to in is are and or for on with it be "
    "this that what how ny sy ary ho amin izay dia "
    # mots de question ou de politesse : ils ne disent rien du sujet
    "qu quel quelle quels quelles c explique expliquer expliques dis donne peux peut tu vous "
    "moi stp svp please could can you tell explain define definition which who why when "
    "inona ahoana iza azafady hazavao",
)).split())

# Dépend du moment : jamais réutilisé tel quel.
_TIME = re.compile(
    r"\b(aujourd'?hui|demain|hier|maintenant|actuel\w*|actualit\w*|derni[eè]re?s?|r[ée]cent\w*|"
    r"cette (semaine|ann[ée]e|saison)|ce (mois|matin|soir)|en ce moment|prix|cours|tarif\w*|"
    r"m[ée]t[ée]o|score|r[ée]sultats? (du|des|de la)|today|tomorrow|yesterday|now|current\w*|"
    r"latest|news|recent\w*|this (week|year|month)|price\w*|weather|anio|ankehitriny|"
    r"rahampitso|omaly|vaovao|toetr'?andro|vidiny|\d{4}-\d{2}-\d{2})\b", re.I)
# Dépend de la personne ou du fil : la même question n'appelle pas la même réponse.
_PERSONAL = re.compile(
    r"\b(je|j'|mon|ma|mes|nous|notre|nos|my|mine|we|our|aho|ahy)\b|"
    r"\b(ce|cet|cette|ces|celui|celle|ceux|cela|[çc]a|il|elle|ils|elles|le m[êe]me|"
    r"aussi|encore|pareil|idem|continue\w*|suite|this|that|these|those|it|them|same|also|"
    r"again|ity|ireo|izany|io)\b", re.I)
_I_CASE = re.compile(r"(?:^|\s)I(?:\s|'|$)")  # « I » anglais (sensible à la casse : « i » malgache)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _h(feature: str) -> int:
    return zlib.crc32(feature.encode("utf-8"))  # stable d'un lancement à l'autre


def vector(text: str) -> dict[int, float]:
    """Vecteur creux normalisé (norme 1) d'un texte."""
    words = [w for w in re.findall(r"[a-z0-9]+", _norm(text)) if w not in _STOP]
    feats: dict[int, float] = {}
    for w in words:
        stem = w[:6]  # racine grossière : photosynthese / photosynthesis / photosynthèse
        feats[_h("w:" + stem)] = feats.get(_h("w:" + stem), 0.0) + 2.0
        padded = f"#{w}#"
        for i in range(len(padded) - 2):
            k = _h("t:" + padded[i:i + 3])
            feats[k] = feats.get(k, 0.0) + 1.0
    if not feats:
        return {}
    for k, v in feats.items():
        feats[k] = 1.0 + math.log(v)
    norm = math.sqrt(sum(v * v for v in feats.values()))
    return {k: v / norm for k, v in feats.items()}


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def similarity(a: str, b: str) -> float:
    return cosine(vector(a), vector(b))


def time_sensitive(text: str) -> bool:
    return bool(_TIME.search(text or ""))


def reusable_question(text: str) -> bool:
    """Question qu'on peut servir depuis le cache : autonome, intemporelle, impersonnelle."""
    t = (text or "").strip()
    # « Qu'est-ce que… », « explique-moi… » restent des questions impersonnelles.
    probe = re.sub(r"est[- ]ce|-moi\b|-me\b", " ", t, flags=re.I)
    return (8 <= len(t) <= 600 and len(re.findall(r"\w+", t)) >= 2
            and not time_sensitive(t) and not _PERSONAL.search(probe) and not _I_CASE.search(t))


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", _norm(text)) if w not in _STOP}


def same_wording(a: str, b: str) -> bool:
    """Mêmes mots (à l'accent près) : une question en anglais ne reçoit jamais la réponse
    française d'une question voisine, même si les trigrammes se ressemblent."""
    wa, wb = words(a), words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.6


def same_numbers(a: str, b: str) -> bool:
    """« 2 + 3 » et « 2 + 4 » sont très proches mais n'ont pas la même réponse."""
    return _NUM.findall(a) == _NUM.findall(b)


def dumps(vec: dict[int, float]) -> str:
    return json.dumps({str(k): round(v, 4) for k, v in vec.items()})


def loads(raw: str) -> dict[int, float]:
    try:
        return {int(k): float(v) for k, v in json.loads(raw).items()}
    except (ValueError, TypeError, AttributeError):
        return {}


class AnswerIndex:
    """Réponses déjà données, cherchées par proximité de la question (en mémoire, adossé à la
    base). Chargé à la première utilisation."""

    def __init__(self, db: Any) -> None:
        self.db = db
        self._rows: list[dict[str, Any]] | None = None

    async def _load(self) -> list[dict[str, Any]]:
        if self._rows is None:
            rows = await self.db.list_answers()
            for r in rows:
                r["vec"] = loads(r["vec"])
            self._rows = rows
        return self._rows

    def invalidate(self) -> None:
        self._rows = None

    async def best(self, question: str, *, exclude_cid: str | None = None
                   ) -> tuple[dict[str, Any] | None, float]:
        q = vector(question)
        if not q:
            return None, 0.0
        best, score = None, 0.0
        for r in await self._load():
            if exclude_cid and r["conversation_id"] == exclude_cid:
                continue
            s = cosine(q, r["vec"])
            if s > score:
                best, score = r, s
        return best, score

    async def reusable(self, question: str) -> dict[str, Any] | None:
        """Réponse à réutiliser telle quelle, ou None."""
        if not reusable_question(question):
            return None
        row, score = await self.best(question)
        if (row is None or score < REUSE or not same_numbers(question, row["question"])
                or not same_wording(question, row["question"])
                or time.time() - float(row["created_at"]) > MAX_AGE):
            return None
        await self.db.touch_answer(int(row["id"]))
        return row

    async def related(self, question: str, cid: str) -> dict[str, Any] | None:
        """Réponse antérieure à une question voisine (autre discussion), pour le contexte."""
        if time_sensitive(question):
            return None
        row, score = await self.best(question, exclude_cid=cid)
        return row if row is not None and score >= RELATED else None

    async def add(self, cid: str, question: str, answer: str, model: str) -> bool:
        if (not reusable_question(question) or len(answer.strip()) < MIN_ANSWER
                or time_sensitive(answer[:300])):
            return False
        vec = vector(question)
        if not vec:
            return False
        await self.db.add_answer(cid, question[:2000], answer[:20000], model, dumps(vec),
                                 MAX_ANSWERS)
        self.invalidate()
        return True


def context_block(row: dict[str, Any]) -> dict[str, Any]:
    when = time.strftime("%Y-%m-%d", time.localtime(float(row["created_at"])))
    return {"role": "system", "content": (
        f"Réponse déjà donnée à l'utilisateur le {when} à une question proche (« "
        f"{row['question'][:300]} »). Réutilise ce qui est juste et pertinent, corrige ce qui "
        "ne l'est plus, sans la recopier si la demande diffère :\n" + row["answer"][:1500])}
