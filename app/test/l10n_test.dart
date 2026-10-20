// Toutes les langues de l'interface sont complètes : aucune chaîne française restante.

import 'package:flutter_test/flutter_test.dart';
import 'package:projia/core/key_guides.dart';
import 'package:projia/l10n/strings.dart';

void main() {
  for (final locale in ['en', 'mg']) {
    test('traductions complètes : $locale', () {
      expect(missingKeys(locale), isEmpty);
    });
  }

  test('les variables {…} sont conservées dans chaque langue', () {
    final vars = RegExp(r'\{(\w+)\}');
    for (final locale in ['en', 'mg']) {
      for (final key in allKeys()) {
        final fr = vars.allMatches(tr('fr', key)).map((m) => m[1]).toSet();
        final other = vars.allMatches(tr(locale, key)).map((m) => m[1]).toSet();
        expect(other, fr, reason: '$locale/$key');
      }
    }
  });

  test('chaque aide de clé a ses textes traduits', () {
    final keys = allKeys().toSet();
    for (final g in keyGuides.values) {
      expect(keys, contains('kg_cost_${g.cost}'));
      if (g.note != null) expect(keys, contains(g.note));
      expect(g.url, startsWith('https://'));
    }
  });
}
