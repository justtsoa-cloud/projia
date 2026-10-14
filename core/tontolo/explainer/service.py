"""De la demande au scénario : complétion, contexte de la discussion, rédaction, repli."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from tontolo.agent import imagebrief
from tontolo.explainer import storyboard, writer
from tontolo.explainer.intent import Brief, ExplainerIntent, complete

WRITE_TIMEOUT = 240.0   # budget total de la course entre modèles
WRITE_PER_TRY = 150.0   # par modèle : les gratuits à réflexion sont lents

_TEXT = {
    "fr": {"intro": "Voici une vidéo explicative de {s} secondes : « {t} ».",
           "choices": "J'ai choisi pour vous : {c}. Dites-moi si vous voulez autre chose.",
           "fallback": "Le scénario complet n'a pas pu être écrit à l'instant : voici une "
                       "version simplifiée tirée de l'explication.",
           "failed": "Je n'ai pas réussi à écrire la vidéo pour l'instant (modèles gratuits "
                     "saturés). Réessayez dans un moment, ou demandez d'abord une explication "
                     "écrite : je pourrai ensuite la transformer en vidéo."},
    "en": {"intro": "Here is a {s}-second explainer video: “{t}”.",
           "choices": "I chose for you: {c}. Tell me if you want something different.",
           "fallback": "The full storyboard could not be written right now: here is a "
                       "simplified version taken from the explanation.",
           "failed": "I could not write the video right now (free models are busy). Try again "
                     "in a moment, or ask for a written explanation first: I can then turn it "
                     "into a video."},
    "mg": {"intro": "Ity ny horonan-tsary fampianarana {s} segondra: « {t} ».",
           "choices": "Nofidiko ho anao: {c}. Lazao raha te hafa ianao.",
           "fallback": "Tsy vita ny tantara feno ankehitriny: ity ny dikan-teny tsotra avy "
                       "amin'ny fanazavana.",
           "failed": "Tsy vita ny horonan-tsary ankehitriny (be loatra ny mpampiasa ireo "
                     "modely maimaim-poana). Andramo indray afaka kelikely."},
}
_NOTES = {
    "fr": {"durée d'environ 1 min 15": "une durée d'environ 1 min 15",
           "une seule notion centrale choisie": "une seule notion centrale"},
    "en": {"durée d'environ 1 min 15": "a length of about 1 min 15",
           "une seule notion centrale choisie": "one central notion"},
    "mg": {"durée d'environ 1 min 15": "faharetana 1 min 15 eo ho eo",
           "une seule notion centrale choisie": "hevitra afovoany iray"},
}


def level_of(mode: str) -> str:
    """« learn:college » → « college » (le niveau du mode Apprendre)."""
    return mode.partition(":")[2] or "lycee"


def message_for(story: dict[str, Any], brief: Brief, *, fallback: bool = False) -> str:
    """Texte de la réponse : une phrase, les choix faits pour l'utilisateur, le bloc lu par
    l'application."""
    lang = brief.language if brief.language in _TEXT else "fr"
    t = _TEXT[lang]
    parts = [t["intro"].format(s=round(story["seconds"]), t=story["title"])]
    if fallback:
        parts.append(t["fallback"])
    # La durée « choisie » n'est annoncée que si la vidéo s'en approche (le modèle écrit court).
    near = abs(story["seconds"] - brief.duration_s) <= 0.4 * brief.duration_s
    notes = [_NOTES[lang].get(n, n) for n in brief.notes
             if near or not n.startswith("durée d'environ")]
    if notes:
        parts.append(t["choices"].format(c=", ".join(notes)))
    return "\n\n".join(parts) + "\n\n```explainer\n" + json.dumps(
        story, ensure_ascii=False, separators=(",", ":")) + "\n```"


def failure_message(language: str) -> str:
    return _TEXT.get(language, _TEXT["fr"])["failed"]


async def produce(core: Any, text: str, history: list[dict[str, Any]], intent: ExplainerIntent,
                  mode: str) -> tuple[dict[str, Any] | None, Brief, str, bool]:
    """(scénario, demande complétée, modèle, repli ?). Scénario None si tout a échoué."""
    topic_hint, summary = imagebrief.digest(history)
    context_topic = imagebrief.subject_of(topic_hint) if topic_hint else ""
    brief = complete(text, level=level_of(mode), language=core.settings.language,
                     topic=context_topic if intent.from_context or not intent.topic else "")
    if not brief.topic:
        brief.topic = context_topic
    model = {"name": ""}

    async def ask(messages: list[dict[str, Any]], accept: Callable[[str], bool]) -> str:
        # Plusieurs modèles gratuits en course (les meilleurs en rédaction d'abord) : le premier
        # dont le JSON passe la validation gagne ; temps généreux, ce sont des modèles lents.
        out = await core.router.quick(messages, 3500, accept, per_try=WRITE_PER_TRY,
                                      budget=WRITE_TIMEOUT, quality="writing", stagger=6.0)
        if not out:
            raise TimeoutError("aucun modèle n'a fourni de scénario valide")
        return out

    try:
        return await writer.write(brief, ask, context=summary), brief, model["name"], False
    except Exception:  # modèle absent, délai, JSON invalide deux fois
        pass
    # Dernière chance avant le repli : une vidéo plus courte (4 scènes), tous modèles gratuits
    # confondus, c'est plus facile à écrire pour un petit modèle.
    light = Brief(brief.topic or context_topic, brief.level, brief.language, 45, brief.broad,
                  [n for n in brief.notes if not n.startswith("durée d'environ")])

    async def ask_light(messages: list[dict[str, Any]], accept: Callable[[str], bool]) -> str:
        out = await core.router.quick(messages, 2500, accept, per_try=60, budget=100,
                                      stagger=4.0)
        if not out:
            raise TimeoutError("aucun modèle n'a fourni de scénario valide")
        return out

    try:
        return await writer.write(light, ask_light, context=summary), light, "", False
    except Exception:
        simple = storyboard.fallback_from_text(brief.topic or context_topic, summary,
                                               brief.language)
        return simple, brief, "", simple is not None
