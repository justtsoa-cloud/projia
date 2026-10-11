// Statistiques : données anonymes uniquement, rien n'est envoyé sans configuration.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/core/stats.dart';

void main() {
  test('payload limité aux champs anonymes', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    final p = Stats.payload(prefs);
    expect(p.keys.toSet(),
        {'install_id', 'app_version', 'platform', 'os_version', 'abi', 'app_locale', 'country', 'messages'});
    expect(Stats.configured, isFalse); // aucune adresse fournie à la compilation des tests
  });

  test('compteur de messages local', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    Stats.countMessage(prefs);
    Stats.countMessage(prefs);
    expect(Stats.payload(prefs)['messages'], 2);
  });
}
