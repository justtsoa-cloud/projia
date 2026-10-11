# Sources consultées

Toutes les intégrations ont été vérifiées sur la documentation officielle ou sur la réponse
réelle de l'API, à la date indiquée. Les quotas et catalogues changent souvent : **rien de
tout cela n'est codé en dur**, tout est relu en ligne à chaque utilisation (cache de 6 h).

| Source | Point d'accès / document | Vérifié le | Remarques |
|---|---|---|---|
| OpenRouter — modèles | `GET https://openrouter.ai/api/v1/models?output_modalities=all` | 2026-10-10 | Sans clé. Champs `pricing`, `architecture`, `supported_parameters`, `created`, `benchmarks.artificial_analysis` (indices AA intégrés). 659 modèles, 19 gratuits en texte. |
| OpenRouter — nouveautés | `GET …/models?use_rss=true` | 2026-10-10 | Flux RSS « New Models ». |
| OpenRouter — limites | `GET https://openrouter.ai/api/v1/key` | 2026-10-10 | Avec clé ; HTTP 401 sans clé. |
| OpenRouter — images | `POST /api/v1/images` (`b64_json`) | 2026-10-10 | Les modèles image/vidéo affichent un prix texte nul mais sont facturés à l'unité : seuls les `:free` sont traités comme gratuits. |
| OpenRouter — audio | `chat/completions`, `modalities: ["text","audio"]`, `stream: true` | 2026-10-10 | `delta.audio.data` en base64. |
| OpenRouter — CGU | https://openrouter.ai/terms (mise à jour du 2026-08-31) | 2026-10-10 | Voir COMPLIANCE.md. |
| Artificial Analysis | `GET https://artificialanalysis.ai/api/v2/data/llms/models`, `/data/media/*` | 2026-10-10 | En-tête `x-api-key`, 1000 req/jour, attribution obligatoire. |
| LMArena | Jeu HF `lmarena-ai/leaderboard-dataset`, lu via `https://datasets-server.huggingface.co/filter` | 2026-10-10 | Configs `text`, `vision`, `webdev`, `search`, `agent`, `text_to_image`, `image_edit`, `text_to_video` ; catégories `overall`, `coding`, `math`… CC BY 4.0. L'API datasets-server est parfois instable (502) : 3 essais puis cache. |
| Fournisseurs gratuits | `https://raw.githubusercontent.com/mnfst/awesome-free-llm-apis/main/data.json` | 2026-10-10 | CC0-1.0. 16 fournisseurs, 101 modèles. **Remplace `cheahjs/free-llm-api-resources`, introuvable (HTTP 404) à cette date.** |
| Pollinations | `GET https://text.pollinations.ai/models` (`tier: anonymous`), `POST https://text.pollinations.ai/openai`, `GET https://image.pollinations.ai/prompt/{prompt}` | 2026-10-10 | Sans clé, débit limité. Permet le « mode sans clé ». |
| Hugging Face — Space `Lightricks/ltx-video-distilled` | `GET /config`, `POST /gradio_api/upload`, `POST /gradio_api/queue/join`, flux `GET /gradio_api/queue/data` | 2026-10-11 | Vidéo (texte → vidéo, photo → vidéo) sans clé ; quota GPU partagé (ZeroGPU) de quelques vidéos par jour, plus large avec une clé Hugging Face gratuite. Pollinations propose aussi des modèles vidéo, mais tous payants (`paid_only`). |
| Hugging Face — Spaces `black-forest-labs/FLUX.1-schnell`, `FLUX.1-dev`, `stabilityai/stable-diffusion-3.5-large-turbo` | `GET /config`, `POST /gradio_api/queue/join`, flux `GET /gradio_api/queue/data` (point d'entrée `infer`) | 2026-10-11 | Images sans clé ; même quota ZeroGPU partagé que la vidéo, Pollinations prend le relais quand il est épuisé. |
| Serveurs payants directs : OpenAI, Anthropic, DeepSeek, xAI | `GET {base}/models` avec la clé de l'utilisateur ; prix et scores repris du catalogue OpenRouter | 2026-10-11 | Utilisés seulement avec la clé de l'utilisateur et un plafond de dépense ; un modèle sans prix connu n'est jamais proposé. |
| Partage Claude / ChatGPT / Gemini (import) | `claude.ai/api/chat_snapshots/{id}` (via la vue web), page `chatgpt.com/share/{id}` (données « turbo-stream »), page Gemini (vue web) | 2026-10-11 | Import d'une discussion à la demande de l'utilisateur ; formats non documentés, susceptibles de changer (repli : texte collé). |
| DuckDuckGo | `ddgs` 9.16 (Linux) ; `POST https://html.duckduckgo.com/html/` (repli Android) | 2026-10-10 | Recherche sans clé. |
| MCP | SDK `mcp` 2.3.0 ; transport Streamable HTTP (protocole `2025-06-18`) | 2026-10-10 | Client léger maison sous Android. |
| serious_python | pub.dev 5.0.0 (README) | 2026-10-10 | CPython 3.12/3.13/3.14 (défaut 3.14) ; roues natives Android sur `pypi.flet.dev` (pydantic-core, pyyaml…). |
| LiteLLM | PyPI 1.104.2 | 2026-10-10 | Optionnel sous Linux ; non embarqué sur Android (trop lourd). |
