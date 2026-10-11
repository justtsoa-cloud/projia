# Conformité aux conditions des fournisseurs

**Principe : clés personnelles uniquement (BYOK).** Tontolo est une application cliente
installée par chaque utilisateur, qui appelle les fournisseurs avec **ses propres clés**.
Aucun service hébergé, aucun proxy avec une clé partagée, aucune revente d'accès.

| Fournisseur | Point d'attention | Vérifié le |
|---|---|---|
| OpenRouter | CGU (2026-08-31), section 7(4) : interdiction de revendre l'accès aux modèles ou de développer un service concurrent ; section 3.2 : confidentialité des clés. Tontolo n'héberge rien et ne revend rien : chaque utilisateur utilise sa clé. **N'exposez pas votre serveur Tontolo (mode client-serveur) à des tiers avec votre clé.** | 2026-10-10 |
| Google AI Studio (Gemini) | Niveau gratuit : les requêtes peuvent servir à améliorer les produits Google ; restrictions régionales signalées (EEE, Suisse, Royaume-Uni) par des sources secondaires — à vérifier par l'utilisateur. | 2026-10-10 |
| Mistral AI | Mode gratuit : les requêtes peuvent servir à l'entraînement sauf refus explicite (selon awesome-free-llm-apis). | 2026-10-10 |
| Cohere | Clé « Trial » : usage non commercial uniquement (selon awesome-free-llm-apis). | 2026-10-10 |
| Pollinations | Niveau anonyme à débit limité ; usage raisonnable, pas de contournement des limites. | 2026-10-10 |
| Artificial Analysis | API gratuite : 1000 requêtes/jour, attribution obligatoire (affichée dans « À propos »). | 2026-10-10 |
| LMArena | CC BY 4.0 : attribution (affichée dans « À propos » et ATTRIBUTIONS.md). | 2026-10-10 |

Mesures techniques :
- respect de `Retry-After` et des en-têtes `x-ratelimit-*` ; aucune requête de sondage ;
- compteurs locaux pour ne pas dépasser les limites publiées ;
- en-têtes d'identification OpenRouter (`HTTP-Referer`, `X-Title`) ;
- les conditions propres à chaque modèle (section 5.1 des CGU OpenRouter) s'appliquent à
  l'utilisateur.

## Vie privée des photos

- **Retouche de photo** (« édite cette photo », filtres, style professionnel…) : appliquée
  **sur l'appareil**, la photo n'est envoyée à aucun service.
- **Questions sur une photo** (« que vois-tu ? ») et **réinterprétation créative** : la photo est
  envoyée au fournisseur d'IA gratuit choisi (Kilo Code, OVHcloud, LLM7, OpenRouter…), comme
  pour toute fonction de vision ; consultez ses conditions. Tontolo l'indique dans le message
  qui accompagne l'image créée.
- **Vidéo** (« crée une vidéo… », « anime cette photo ») : la description et, le cas échéant,
  la photo sont envoyées au Space public LTX-Video (Lightricks) hébergé par Hugging Face, qui
  les traite sur son GPU partagé ; consultez les conditions de Hugging Face. N'animez pas la
  photo d'une personne sans son accord.
- Si la consigne demande de **ne pas changer la personne**, Tontolo ne recrée jamais une autre
  image : retouche locale, ou refus explicite.
