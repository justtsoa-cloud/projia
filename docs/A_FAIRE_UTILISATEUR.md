# Vérifications réservées à l’utilisateur

Les essais sur appareils réels ont déjà été effectués et les bugs signalés
(confirmation du 2026-10-14). Cette campagne n’est pas redemandée.

- [ ] Valider la nouvelle formulation malgache du refus d’export MP4 :
  « Tsy misy bubblewrap: tsy afaka mamoaka MP4. Mbola azo jerena eto ny horonan-tsary. »
  Traduction provisoire, non validée.

La réconciliation des autres points de la feuille de route reste en cours ; cette
liste ne constitue pas encore le bilan final des phases A à E.

- [ ] Valider la formulation malgache du refus d’exécution isolée :
  « Tsy azo atao: mila bubblewrap ny fefy. » (provisoire).
- [ ] Dans Supabase › SQL Editor, exécuter `docs/stats/supabase_minimal.sql`,
  puis vérifier une insertion des trois champs et le refus d’une lecture avec la clé anon.
  La migration est préparée, pas exécutée sur le service distant ; les nouvelles versions
  n’enverront pas l’ancien format si cette table manque.
