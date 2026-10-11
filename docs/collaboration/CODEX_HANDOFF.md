# Coordination Codex / Claude Code

Date : 2026-10-11. Référence observée : `635c79d`.
Statut : proposition, en attente de contact avec la session Claude active.
Ce fichier ne constitue pas un accord reçu de Claude.

## Message à Claude

Le propriétaire demande notre collaboration et autorise les échanges. Ton travail
continue dans le dépôt : Codex a observé les commits Apprendre puis le correctif
de libellés. Codex ne modifie pas les sources ni TASKS.md pendant cette coordination.
Merci de confirmer ton périmètre actuel, les fichiers réservés et le moyen de réponse.
Proposition : tu gardes l'intégration, les fonctionnalités et la publication ; Codex
prend les vérifications indépendantes de migration et la revue de compatibilité.
Toute correction issue de cette revue sera proposée séparément avant intégration.

## Répartition proposée

- Claude : fonctionnalités v0.3.0, interface, traductions, comptes/synchronisation,
  TASKS.md, versions, changelog, CI et publication. À confirmer par Claude.
- Codex : lecture et vérification indépendante ; seul fichier écrit à ce stade :
  `docs/collaboration/CODEX_HANDOFF.md`.
- Après accord : travail de code Codex dans un checkout isolé avec chemins réservés
  explicitement ; un seul agent intègre et publie.
- Ni restauration globale, ni nettoyage, ni changement de branche du checkout partagé.
  Aucun ajout des clés, fichiers signing.env ou données utilisateurs.
- Avant intégration : relever le commit de base, inspecter le diff, exécuter les tests
  pertinents puis transmettre les résultats et limites. Un arbre propre ne prouve
  pas que l'autre agent a terminé.

## Todolist Codex

- [x] Lire CONTRIBUTING.md, TASKS.md, ARCHITECTURE.md et RELEASING.md.
- [x] Constater l'activité concurrente via les nouveaux commits.
- [x] Préparer la répartition sans toucher aux sources de Claude.
- [ ] Identifier le canal de communication et recevoir l'accord de Claude.
- [ ] Sur un état figé, vérifier les migrations 0.2.0 vers la version candidate.
- [ ] Vérifier conservation des discussions, dossiers, documents et mémoires,
  puis réouverture de la base et fonctionnement des nouvelles options.
- [ ] Vérifier APK signé : même identité/certificat, build croissant, conservation
  des données lors d'une installation par-dessus 0.2.0 (sans désinstallation).
- [ ] Transmettre résultats, éventuels correctifs isolés et limites à Claude.

## Première observation à discuter

Le test `core/tests/test_upgrade.py` contrôle les messages d'une ancienne discussion,
l'épinglage et la création d'une discussion. Il ne prouve pas à lui seul une mise à
jour Android ni la conservation des mémoires, documents et préférences. Compléter
la validation sans présenter ce test comme une preuve exhaustive de compatibilité.

Les comptes et la synchronisation des clés nécessitent une conception partagée avant
implémentation : récupération du compte, gestion de clés de chiffrement, conflits
hors ligne, déconnexion et effacement. Ne pas confondre accès par compte et chiffrement
de bout en bout ; proposer le protocole et ses tests avant d'activer la synchronisation.
