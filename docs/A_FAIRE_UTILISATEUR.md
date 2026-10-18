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
- [ ] Valider les termes malgaches des affiches du 2026-10-14 (press/campaigns/2026-10-14/campaign.json) : « Manaova horonan-tsary… », « Ataovy sary izany », « Tadidio fa… », « Fintinio ny resaka », « Mitenena, i Tontolo dia mamaly », « Fomba mitsitsy », « Fanamboarana manokana ».
- [ ] Valider les termes malgaches de la v0.7.1 et des affiches du 2026-10-16/18 : « Hevitra ho anao », « Tsy ho ahy », « Fampahatsiahivana mangina », « Vaovao ao amin'ny sehatrao », « Ahoana ny fizotran'ny zavatra… », « Manomeza naoty », « Resaho miaraka amin'i Tontolo », « Valiny haingana kokoa ».
- [ ] Valider les textes malgaches de fdroid/metadata/mg/ (description courte et longue).
