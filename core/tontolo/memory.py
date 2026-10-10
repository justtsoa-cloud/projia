"""Mémoire à long terme, locale, qui se compacte automatiquement.

Inspirée de la « mémoire » des assistants grand public, mais entièrement locale :

- **Capture explicite** : « souviens-toi que… », « retiens que… », « remember that… »,
  « tadidio fa… » → enregistré immédiatement.
- **Capture automatique** : tous les quelques échanges, un petit modèle gratuit extrait
  les faits durables (préférences, contexte, projets). Les secrets (clés, mots de passe,
  numéros de carte) ne sont jamais mémorisés.
- **Rappel** : les souvenirs les plus pertinents pour la demande en cours (recouvrement
  de mots, usage récent) sont injectés dans le contexte, dans un budget de caractères.
- **Compactage automatique** : au-delà de `memory_max_items` souvenirs, les doublons
  sont fusionnés localement, puis un petit modèle regroupe et résume ; sans modèle
  disponible, les souvenirs les moins utiles sont retirés.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

from tontolo.config import Settings
from tontolo.storage.db import Database

log = logging.getLogger(__name__)

Quick = Callable[[list[dict[str, Any]]], Awaitable[str | None]]

EXTRACT_EVERY = 4          # extraction automatique tous les N messages utilisateur
SIMILAR = 0.75             # seuil de fusion de deux souvenirs

_EXPLICIT = re.compile(
    r"^\s*(?:souviens[- ]toi|rappelle[- ]toi|retiens|m[ée]morise|note|n'oublie pas)\s+"
    r"(?:bien\s+)?(?:que\s+|qu'|de\s+|ceci\s*:\s*)?(?P<fr>.+)$"
    r"|^\s*(?:remember|note)\s+(?:that\s+)?(?P<en>.+)$"
    r"|^\s*(?:tadidio|aza adino)\s+(?:fa\s+)?(?P<mg>.+)$",
    re.I | re.S,
)
_SECRET = re.compile(
    r"(sk-|gsk_|nvapi-|hf_|AIza|ghp_|gho_|xox[bp]-)[A-Za-z0-9_\-]{8,}"
    r"|\b(?:\d[ -]?){13,19}\b|mot de passe|password|passwd|\bpin\b|cvv|iban",
    re.I,
)
_STOP_WORDS = (
    "le la les un une des de du et ou à au aux en pour par sur avec dans que qui quoi est "
    "sont je tu il elle on nous vous ils elles mon ma mes ton ta tes son sa ses ce cet cette "
    "ces the a an of to in is are and or for on with my your me i it be this that"
)
_STOP = set(_STOP_WORDS.split(" "))

EXTRACT_PROMPT = (
    "Tu extrais des souvenirs utiles et durables sur l'utilisateur à partir de la "
    "conversation : préférences, langue, niveau, métier, projets en cours, consignes "
    "de style. Ignore ce qui est ponctuel. N'inclus JAMAIS de secret (clé, mot de passe, "
    "numéro de carte), ni de donnée de santé. Réponds uniquement en JSON : "
    '{"memories": ["phrase courte à la 3e personne", ...]} (liste vide si rien).'
)
COMPACT_PROMPT = (
    "Voici des souvenirs sur un utilisateur. Fusionne les doublons, supprime ce qui est "
    "contradictoire ou obsolète (garde le plus récent), et reformule en phrases courtes. "
    "Garde au plus {n} éléments, les plus utiles. Réponds uniquement en JSON : "
    '{{"memories": ["…", …]}}'
)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", _norm(text)) if w not in _STOP}


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def explicit_memory(text: str) -> str | None:
    """« Souviens-toi que je préfère le tutoiement » → « je préfère le tutoiement »."""
    m = _EXPLICIT.match(text or "")
    if not m:
        return None
    value = (m.group("fr") or m.group("en") or m.group("mg") or "").strip().rstrip(".")
    return value if 3 <= len(value) <= 500 else None


def is_safe(text: str) -> bool:
    return not _SECRET.search(text)


def _parse_list(text: str | None) -> list[str]:
    if not text:
        return []
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0)).get("memories", [])
    except (ValueError, AttributeError):
        return []
    return [str(i).strip() for i in items if isinstance(i, str) and 3 <= len(i.strip()) <= 300]


class MemoryService:
    def __init__(self, settings: Settings, db: Database, quick: Quick | None = None) -> None:
        self.settings = settings
        self.db = db
        self.quick = quick
        self._counts: dict[str, int] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.memory_enabled

    async def remember(self, text: str, kind: str = "fact", source: str | None = None) -> bool:
        """Ajoute ou fusionne un souvenir. Refuse les secrets. Vrai si enregistré."""
        text = text.strip()
        if not text or not is_safe(text):
            return False
        for mem in await self.db.list_memories():
            if similarity(mem["text"], text) >= SIMILAR:
                # Le plus récent l'emporte (mise à jour d'une préférence).
                await self.db.update_memory(int(mem["id"]), text)
                return True
        await self.db.add_memory(text, kind, source)
        await self.maybe_compact()
        return True

    async def recall(self, query: str) -> list[dict[str, Any]]:
        """Souvenirs pertinents pour `query`, dans le budget de caractères."""
        if not self.enabled:
            return []
        mems = await self.db.list_memories()
        if not mems:
            return []
        q = tokens(query)
        now = time.time()

        def score(m: dict[str, Any]) -> float:
            overlap = len(q & tokens(m["text"])) / (len(q) or 1)
            recency = 1.0 / (1.0 + (now - float(m["updated_at"])) / (30 * 86400))
            base = 1.0 if m["kind"] == "instruction" else 0.0
            return base + 2.0 * overlap + 0.3 * recency + 0.05 * min(int(m["uses"]), 10)

        chosen: list[dict[str, Any]] = []
        used = 0
        for m in sorted(mems, key=score, reverse=True):
            if used + len(m["text"]) > self.settings.memory_budget_chars:
                continue
            chosen.append(m)
            used += len(m["text"])
        await self.db.touch_memories([int(m["id"]) for m in chosen])
        return chosen

    def system_block(self, memories: list[dict[str, Any]]) -> dict[str, Any] | None:
        parts = []
        if self.settings.custom_instructions.strip():
            parts.append("Instructions de l'utilisateur :\n"
                         + self.settings.custom_instructions.strip()[:2000])
        if memories:
            parts.append("Ce que tu sais de l'utilisateur (mémoire locale, à utiliser avec tact, "
                         "sans le répéter) :\n" + "\n".join(f"- {m['text']}" for m in memories))
        return {"role": "system", "content": "\n\n".join(parts)} if parts else None

    async def after_turn(self, conversation_id: str, history: list[dict[str, Any]]) -> None:
        """Extraction automatique périodique (à lancer en arrière-plan)."""
        if not self.enabled or self.quick is None:
            return
        n = self._counts.get(conversation_id, 0) + 1
        self._counts[conversation_id] = n
        if n % EXTRACT_EVERY:
            return
        recent = [m for m in history if m.get("role") in ("user", "assistant")
                  and isinstance(m.get("content"), str)][-8:]
        convo = "\n".join(f"{m['role']}: {m['content'][:1500]}" for m in recent)
        out = await self.quick([{"role": "system", "content": EXTRACT_PROMPT},
                                {"role": "user", "content": convo}])
        for item in _parse_list(out)[:5]:
            await self.remember(item, source=conversation_id)

    async def maybe_compact(self, force: bool = False) -> int:
        """Compactage automatique. Renvoie le nombre de souvenirs après compactage."""
        mems = await self.db.list_memories()
        limit = max(10, self.settings.memory_max_items)
        if not force and len(mems) <= limit:
            return len(mems)
        # 1. Fusion locale des doublons (sans réseau).
        kept: list[dict[str, Any]] = []
        for m in sorted(mems, key=lambda x: float(x["updated_at"]), reverse=True):
            if any(similarity(m["text"], k["text"]) >= SIMILAR for k in kept):
                continue
            kept.append(m)
        target = limit // 2 if (force or len(kept) > limit) else len(kept)
        # 2. Regroupement par un petit modèle gratuit.
        if len(kept) > target and self.quick is not None:
            out = await self.quick([
                {"role": "system", "content": COMPACT_PROMPT.format(n=target)},
                {"role": "user", "content": "\n".join(f"- {m['text']}" for m in kept)},
            ])
            merged = [t for t in _parse_list(out) if is_safe(t)][:target]
            if merged:
                instructions = [m for m in kept if m["kind"] == "instruction"]
                items = [{"text": m["text"], "kind": "instruction"} for m in instructions]
                items += [{"text": t} for t in merged]
                await self.db.replace_memories(items)
                log.info("Mémoire compactée : %d → %d", len(mems), len(items))
                return len(items)
        # 3. Repli sans modèle : garder les plus utiles.
        if len(kept) > target:
            kept.sort(key=lambda m: (m["kind"] == "instruction", int(m["uses"]),
                                     float(m["updated_at"])), reverse=True)
            kept = kept[:target]
        if len(kept) != len(mems):
            await self.db.replace_memories(kept)
        return len(kept)
