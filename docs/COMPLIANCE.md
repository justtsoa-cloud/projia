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
