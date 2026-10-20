# Audit de sécurité (2026-10-12)

Analyse statique : `uvx bandit -r core/projia -ll` (sévérité moyenne et plus). Aucune
alerte haute.

## Corrigé

- **Mises à jour Linux signées** (2026-10-13) : `SHA256SUMS` est signé en Ed25519 par la CI
  (clé privée uniquement dans un secret GitHub) ; l'AppImage n'est remplacée que si la signature
  est valide avec la clé publique embarquée, puis si l'empreinte du fichier correspond. Une
  release GitHub compromise ne suffit donc plus à pousser une mise à jour Linux.

| Point | Avant | Après |
|---|---|---|
| `secrets.json` (repli sans trousseau) | clés en clair (mode 0600) | chiffré : Fernet si `cryptography` est présent, sinon HMAC-SHA256 en mode compteur + étiquette ; ancien fichier migré à la première lecture ; fichiers temporaires distincts (bogue trouvé par les tests) |
| `/projia/ws` | connexions illimitées | 16 clients au plus, 30 tentatives par minute et par adresse (code 4429) ; file d'événements déjà bornée |
| Terminal (`/projia/terminal/{cid}/ws`) | messages illimités | 64 Ko par message (code 1009), 200 messages par seconde |
| MCP (`PUT /projia/mcp`) | toute commande stdio acceptée en local | interpréteurs de commandes, élévation de droits, outils destructeurs ou réseau brut refusés ; code en ligne (`python -c`, `node -e`…) refusé ; variables `LD_*`, `NODE_OPTIONS`… refusées ; 20 serveurs, 64 Ko, sorties d'outils de 100 000 caractères et 100 outils par serveur au plus ; depuis un autre appareil, serveurs HTTP seulement en HTTPS public (pas de SSRF) ; un fichier modifié à la main est revérifié au chargement ; sous Linux, serveur stdio lancé sous bubblewrap s'il est installé (système en lecture seule, dossier personnel, `/run` et données Projia masqués, seuls les dossiers passés en arguments ouverts ; `sandbox: false` pour s'en passer) |
| XML des docx générés | analysé sans garde | DTD et entités refusées, comme pour tous les XML reçus |

Clé du fichier chiffré : sur le même disque. Cela protège contre la fuite du seul fichier
(sauvegarde, synchronisation, partage par erreur), pas contre un accès complet au dossier de
données ; le trousseau du système reste la voie préférée.

## Faux positifs vérifiés

- `storage/db.py` (B608, trois requêtes) : seuls des fragments constants sont assemblés
  (`c.deleted = 0`, `AND c.folder = ?`, liste fixe de colonnes) ; toutes les valeurs sont des
  paramètres liés.
- XML marqués `# nosec B314/B318` : DTD et entités refusées juste avant l'analyse.
- `agent/mcp_client.py` (B108) : `/tmp` y est un point de montage vide *dans* le bac à sable bubblewrap (`--tmpfs /tmp`), aucun fichier n'y est écrit par le cœur.
- `agent/browser.py` (B104) : simple comparaison de texte, aucune écoute réseau.
