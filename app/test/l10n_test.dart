// Toutes les langues de l'interface sont complètes : aucune chaîne française restante.

import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/l10n/strings.dart';

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
}
