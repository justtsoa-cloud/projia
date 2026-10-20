// Écran des réglages, avec un cœur simulé (réponses réelles enregistrées dans
// fixtures/core_get.json) : les deux onglets s'affichent sans erreur et un choix est envoyé.
import 'dart:convert';
import 'dart:io';

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
import 'package:projia/l10n/strings.dart';
import 'package:projia/main.dart';
import 'package:projia/ui/settings_screen.dart';

class FakeCore extends Backend {
  FakeCore(super.prefs, this.data) {
    state = BackendState.ready;
  }
  final Map<String, dynamic> data;
  final sent = <(String, String, Object?)>[];

  dynamic _answer(String path) => jsonDecode(jsonEncode(data[path.replaceFirst('/projia/', '')]));

  @override
  Future<dynamic> getJson(String path, [Map<String, dynamic>? query]) async => _answer(path);

  @override
  Future<dynamic> sendJson(String method, String path, [Object? body]) async {
    sent.add((method, path, body));
    if (path == '/projia/settings' && body is Map) {
      (data['settings'] as Map<String, dynamic>).addAll(body.cast<String, dynamic>());
    }
    return _answer(path) ?? <String, dynamic>{};
  }
}

void main() {
  late FakeCore core;

  void expectSent(String method, String path, Map<String, dynamic> body) {
    final (m, p, b) = core.sent.last;
    expect((m, p), (method, path));
    expect(b, body);
  }

  Future<void> open(WidgetTester tester, {String locale = 'fr'}) async {
    SharedPreferences.setMockInitialValues({'locale': locale});
    final prefs = await Prefs.load();
    core = FakeCore(prefs, jsonDecode(File('test/fixtures/core_get.json').readAsStringSync()) as Map<String, dynamic>);
    final chat = ChatController(core);
    final account = Account();
    final cloud = CloudSync(core, account);
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(AppScope(
      prefs: prefs,
      backend: core,
      updater: Updater(prefs),
      chat: chat,
      account: account,
      cloud: cloud,
      activity: ActivityWatcher(core, cloud, chat),
      child: const MaterialApp(home: SettingsScreen()),
    ));
    await tester.pumpAndSettle();
  }

  testWidgets('onglet Simple : tâches en plusieurs parties envoyées au cœur', (tester) async {
    await open(tester);
    expect(find.text('Simple'), findsWidgets);
    final multi = find.text('Plusieurs modèles');
    await tester.scrollUntilVisible(multi, 300, scrollable: find.byType(Scrollable).first);
    await Scrollable.ensureVisible(tester.element(multi), alignment: 0.5);
    await tester.pumpAndSettle();
    await tester.tap(multi);
    await tester.pumpAndSettle();
    expectSent('PUT', '/projia/settings', {'task_planning': true, 'orchestrate': true});
    expect(find.textContaining('confiées en même temps à plusieurs modèles'), findsOneWidget);
    await tester.tap(find.descendant(of: find.byType(SegmentedButton<String>), matching: find.text('Simple')));
    await tester.pumpAndSettle();
    expectSent('PUT', '/projia/settings', {'task_planning': false, 'orchestrate': false});
  });

  testWidgets('onglet Avancé : affiché sans erreur, dans les trois langues', (tester) async {
    for (final (locale, tab) in [('fr', 'Avancé'), ('en', 'Advanced'), ('mg', 'Mandroso')]) {
      await open(tester, locale: locale);
      final adv = find.text(tab);
      if (adv.evaluate().isEmpty) fail('onglet « $tab » introuvable ($locale)');
      await tester.tap(adv);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text(tr(locale, 'mode')), findsOneWidget);
      expect(find.text(tr(locale, 'mode_local')), findsWidgets);
      await tester.pumpWidget(const SizedBox());
    }
  });
}
