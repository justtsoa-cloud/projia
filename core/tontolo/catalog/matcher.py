"""Résolution d'identité des modèles entre sources.

Un même modèle s'appelle « google/gemma-4-31b-it:free » chez OpenRouter,
« Gemma 4 31B » chez Artificial Analysis et « gemma-4-31b-it » chez LMArena.
On réduit chaque nom à une **clé canonique** (minuscules, sans organisation,
sans suffixes de variante ou de date), puis on apparie :

1. par égalité de clé ;
2. sinon par jetons, en exigeant que les numéros de version, les gammes
   (mini, flash, pro…) et, s'ils sont présents des deux côtés, les tailles
   (31b, a12b…) concordent, et que les mots du nom le plus court soient tous
   contenus dans l'autre.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Jetons sans incidence sur l'identité du modèle.
_NOISE = {
    "it", "instruct", "chat", "preview", "latest", "exp", "experimental", "hf", "free",
    "fp8", "fp16", "bf16", "int4", "int8", "awq", "gguf", "beta", "online", "api", "model",
    "base", "versatile", "fast",
}
# Variantes d'effort : la meilleure note est retenue pour le modèle de base.
_EFFORT = {"high", "low", "minimal", "xhigh", "thinking", "nothinking", "reasoning",
           "nonreasoning", "adaptive"}
# Gammes : elles distinguent des modèles différents d'une même famille.
_TIERS = {"mini", "nano", "micro", "tiny", "flash", "lite", "pro", "plus", "ultra", "super",
          "small", "medium", "large", "max", "air", "turbo", "coder", "code", "vision", "vl",
          "omni", "haiku", "sonnet", "opus", "scout", "maverick", "distill", "edit", "image",
          "audio", "tts", "realtime", "search", "math", "guard", "safety", "embed", "rp"}
_DATE = re.compile(r"^(20\d{2}(0[1-9]|1[0-2])\d{2}|\d{4})$")
_ORG_PREFIX = re.compile(r"^[\w .&-]{1,40}:\s+")


def tokens(name: str) -> list[str]:
    s = name.strip().lower()
    s = _ORG_PREFIX.sub("", s)            # « Google: Gemma 4 » → « gemma 4 »
    s = s.split("/")[-1]                  # « google/gemma-4 » → « gemma-4 »
    s = re.sub(r":(free|beta|extended|thinking|nitro|floor|online)$", "", s)
    s = s.replace("non-reasoning", "nonreasoning")
    s = re.sub(r"(\d)\.(\d)", r"\1-\2", s)  # « 3.5 » → « 3-5 »
    out: list[str] = []
    for t in re.split(r"[^a-z0-9]+", s):
        if not t or t in _NOISE or t in _EFFORT:
            continue
        if _DATE.match(t):
            continue
        if re.fullmatch(r"v\d+", t):     # « v4 » → « 4 »
            t = t[1:]
        out.append(t)
    return out


def canonical(name: str) -> str:
    return "-".join(tokens(name))


@dataclass(frozen=True)
class _Parts:
    toks: frozenset[str]
    numbers: frozenset[str]  # numéros purs (version)
    sizes: frozenset[str]    # tailles mixtes (31b, a12b, 16e…)
    tiers: frozenset[str]
    words: frozenset[str]

    @classmethod
    def of(cls, toks: Iterable[str]) -> _Parts:
        t = frozenset(toks)
        numbers = frozenset(x for x in t if x.isdigit())
        sizes = frozenset(x for x in t if not x.isdigit() and any(c.isdigit() for c in x))
        tiers = frozenset(x for x in t if x in _TIERS)
        words = t - numbers - sizes - tiers
        return cls(t, numbers, sizes, tiers, words)

    def compatible(self, other: _Parts) -> float:
        if self.numbers != other.numbers or self.tiers != other.tiers:
            return 0.0
        if self.sizes and other.sizes and self.sizes != other.sizes:
            return 0.0
        small, big = sorted((self.words, other.words), key=len)
        if not small or not small <= big:
            return 0.0
        return len(self.toks & other.toks) / len(self.toks | other.toks)


@dataclass
class MatchResult:
    key: str
    score: float


class Matcher:
    """Index de noms canoniques → identifiant de classement."""

    def __init__(self) -> None:
        self._exact: dict[str, str] = {}
        self._parts: dict[str, _Parts] = {}

    def add(self, ident: str, names: Iterable[str]) -> None:
        for n in names:
            toks = tokens(n)
            if not toks:
                continue
            c = "-".join(toks)
            self._exact.setdefault(c, ident)
            self._parts.setdefault(c, _Parts.of(toks))

    def match(self, *names: str | None) -> MatchResult | None:
        best: MatchResult | None = None
        for n in names:
            if not n:
                continue
            toks = tokens(n)
            if not toks:
                continue
            c = "-".join(toks)
            if c in self._exact:
                return MatchResult(self._exact[c], 1.0)
            parts = _Parts.of(toks)
            for key, kp in self._parts.items():
                score = parts.compatible(kp)
                if score > 0 and (best is None or score > best.score):
                    best = MatchResult(self._exact[key], score)
        return best


def family(name: str) -> str:
    """Famille approximative (« gemma-4-31b » → « gemma-4 »), pour les scores provisoires."""
    toks = tokens(name)
    words = [t for t in toks if not any(c.isdigit() for c in t) and t not in _TIERS]
    nums = [t for t in toks if t.isdigit()]
    return "-".join(words[:1] + nums[:1]) if words else (toks[0] if toks else "")
