"""Types du catalogue : un modèle tel que Tontolo le voit, toutes sources fusionnées."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Category(StrEnum):
    """Catégories de tâches (section 4.1 de la spécification)."""

    CHAT = "chat"
    CODE = "code"
    MATH = "math"
    REASONING = "reasoning"
    WRITING = "writing"
    TRANSLATION = "translation"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    AGENTIC = "agentic"
    SEARCH = "search"
    IMAGE_GEN = "image_gen"
    IMAGE_EDIT = "image_edit"
    STT = "stt"
    TTS = "tts"
    MUSIC_SFX = "music_sfx"
    VIDEO_GEN = "video_gen"


TEXT_CATEGORIES = frozenset({
    Category.CHAT, Category.CODE, Category.MATH, Category.REASONING, Category.WRITING,
    Category.TRANSLATION, Category.VISION, Category.LONG_CONTEXT, Category.AGENTIC,
    Category.SEARCH,
})
MEDIA_CATEGORIES = frozenset(set(Category) - TEXT_CATEGORIES)


class ModelInfo(BaseModel):
    """Un modèle appelable chez un fournisseur donné."""

    provider: str
    model_id: str
    name: str = ""
    family: str = ""
    created: float | None = None
    context_length: int = 0
    max_output: int | None = None
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    supports_tools: bool = False
    is_free: bool = False
    needs_key: bool = True
    # Prix en USD par token (texte) ; 0 si gratuit.
    price_in: float = 0.0
    price_out: float = 0.0
    rate_limit: str | None = None
    # Catégories médias servies (image_gen, stt, tts, video_gen…) ; le texte est implicite.
    media: list[str] = Field(default_factory=list)
    # Métriques brutes par source (« aa.coding », « lmarena.coding »…).
    metrics: dict[str, float] = Field(default_factory=dict)
    # Qualité normalisée [0, 1] par catégorie, calculée par le catalogue.
    quality: dict[str, float] = Field(default_factory=dict)
    speed: float | None = None  # normalisée [0, 1]
    provisional: bool = False

    @property
    def key(self) -> str:
        """Identifiant global unique : `fournisseur:id`."""
        return f"{self.provider}:{self.model_id}"

    @property
    def supports_vision(self) -> bool:
        return "image" in self.input_modalities

    @property
    def is_text(self) -> bool:
        return "text" in self.output_modalities and not self.media

    def serves(self, category: Category | str) -> bool:
        cat = Category(category)
        if cat in MEDIA_CATEGORIES:
            return cat.value in self.media
        if not self.is_text:
            return False
        if cat == Category.VISION:
            return self.supports_vision
        return True
