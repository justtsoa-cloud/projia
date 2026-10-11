import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/l10n/strings.dart';
import 'package:tontolo/ui/home_view.dart';

void main() {
  test('salutation selon l\'heure', () {
    expect(greetingKey(DateTime(2026, 10, 12, 8)), 'greet_morning');
    expect(greetingKey(DateTime(2026, 10, 12, 14)), 'greet_afternoon');
    expect(greetingKey(DateTime(2026, 10, 12, 20)), 'greet_evening');
    expect(greetingKey(DateTime(2026, 10, 12, 2)), 'greet_night');
    expect(tr('fr', 'greet_name', {'g': tr('fr', 'greet_evening'), 'n': 'Antsa'}), 'Bonsoir Antsa');
  });

  test('suggestions selon le moment et le mode, toutes traduites', () {
    final sunday = DateTime(2026, 10, 11, 19);
    final pool = suggestionPool(sunday, agent: true, random: Random(1));
    final keys = pool.map((s) => s.key).toSet();
    expect(keys, containsAll(['hs_dinner', 'hs_outing', 'hs_agent_report']));
    expect(keys.contains('hs_breakfast'), isFalse);
    final general = suggestionPool(DateTime(2026, 10, 12, 9), agent: false).map((s) => s.key);
    expect(general, contains('hs_breakfast'));
    expect(general.any((k) => k.startsWith('hs_agent')), isFalse);
    for (final s in pool) {
      for (final l in ['fr', 'en', 'mg']) {
        expect(tr(l, s.key), isNot(s.key));
      }
    }
  });
}
