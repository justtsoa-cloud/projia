// Langue au premier lancement : celle du téléphone (fr, en, mg ; sinon anglais), confirmée à
// l'accueil. Plus de « français » imposé à tout le monde (cela faussait les statistiques).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:projia/core/account.dart';
import 'package:projia/core/activity.dart';
import 'package:projia/core/backend.dart';
import 'package:projia/core/chat_controller.dart';
import 'package:projia/core/cloud_sync.dart';
import 'package:projia/core/prefs.dart';
import 'package:projia/core/updater.dart';
import 'package:projia/main.dart';
import 'package:projia/ui/onboarding.dart';

class _Core extends Backend {
  _Core(super.prefs);
  final sent = <Object?>[];
  @override
  Future<dynamic> sendJson(String method, String path, [Object? body]) async {
    sent.add(body);
    return <String, dynamic>{};
  }
}

void main() {
  test('langue du téléphone → langue de l\'application', () {
    expect(Prefs.localeFor('fr'), 'fr');
    expect(Prefs.localeFor('MG'), 'mg');
    expect(Prefs.localeFor('en'), 'en');
    expect(Prefs.localeFor('de'), 'en');
    expect(Prefs.localeFor(''), 'en');
  });

  test('première installation : langue enregistrée ; mise à jour : rien ne change', () async {
    SharedPreferences.setMockInitialValues({});
    final fresh = await Prefs.load();
    expect(fresh.locale, 'en'); // le banc de test a un téléphone en anglais
    SharedPreferences.setMockInitialValues({'onboarded': true}); // utilisateur existant sans choix
    expect((await Prefs.load()).locale, 'fr'); // il gardait le français : pas de changement surprise
    SharedPreferences.setMockInitialValues({'onboarded': true, 'locale': 'mg'});
    expect((await Prefs.load()).locale, 'mg');
  });

  testWidgets('accueil : choix de la langue, appliqué tout de suite', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    final core = _Core(prefs);
    final chat = ChatController(core);
    final cloud = CloudSync(core, Account());
    await tester.pumpWidget(AppScope(
      prefs: prefs,
      backend: core,
      updater: Updater(prefs),
      chat: chat,
      account: Account(),
      cloud: cloud,
      activity: ActivityWatcher(core, cloud, chat),
      child: const MaterialApp(home: Onboarding()),
    ));
    await tester.pump();
    expect(find.text('English'), findsOneWidget);
    await tester.tap(find.text('Malagasy'));
    await tester.pump();
    expect(prefs.locale, 'mg');
    expect(core.sent.single, {'language': 'mg'}); // le cœur répond aussi dans cette langue
    expect(find.text('Hanomboka'), findsNothing); // (texte d'exemple : aucune erreur de rendu)
    expect(tester.takeException(), isNull);
  });
}
