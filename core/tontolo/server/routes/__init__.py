"""Routeurs du serveur, enregistrés dans cet ordre par `create_app` (l'ordre compte pour
la correspondance des chemins)."""

from tontolo.server.routes import (
    browser,
    catalog,
    chat,
    data,
    documents,
    explainer,
    media,
    openai_compat,
    realtime,
    settings,
    system,
)

ROUTERS = (openai_compat, documents, chat, catalog, settings, media, data, browser, system,
           realtime, explainer)
