// Mise en page de l'écran de discussion : liste des discussions permanente sur très grand écran,
// tiroir sur téléphone et petite tablette.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/account.dart';
import 'package:tontolo/core/activity.dart';
import 'package:tontolo/core/backend.dart';
import 'package:tontolo/core/chat_controller.dart';
import 'package:tontolo/core/cloud_sync.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/core/updater.dart';
import 'package:tontolo/main.dart';
import 'package:tontolo/ui/chat_screen.dart';
import 'package:tontolo/ui/message_view.dart';

class _Core extends Backend {
  _Core(super.prefs) {
    state = BackendState.ready;
  }
  final sentBodies = <Object?>[];

  @override
  Stream<Map<String, dynamic>> sse(String path, Object? body, {String method = 'POST'}) {
    sentBodies.add(body);
    return const Stream.empty();
  }

  @override
  Future<dynamic> getJson(String path, [Map<String, dynamic>? query]) async {
    if (path == '/tontolo/conversations') {
      return [
        {'id': 'a', 'title': 'Plan de révision', 'updated_at': 1.0, 'count': 2, 'pinned': 0, 'folder': ''},
      ];
    }
    return <dynamic>[];
  }
}

void main() {
  late _Core core;

  Future<ChatController> open(WidgetTester tester, double width) async {
    SharedPreferences.setMockInitialValues({'locale': 'fr'});
    final prefs = await Prefs.load();
    core = _Core(prefs);
    final chat = ChatController(core);
    final account = Account();
    final cloud = CloudSync(core, account);
    tester.view.physicalSize = Size(width * 2, 1800);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(AppScope(
      prefs: prefs,
      backend: core,
      updater: Updater(prefs),
      chat: chat,
      account: account,
      cloud: cloud,
      activity: ActivityWatcher(core, cloud, chat),
      child: const MaterialApp(home: ChatScreen()),
    ));
    await tester.pump(const Duration(milliseconds: 300));
    return chat;
  }

  testWidgets('très grand écran : la liste des discussions reste affichée, sans bouton de tiroir', (tester) async {
    await open(tester, 1400);
    expect(find.byType(HistoryDrawer), findsOneWidget);
    expect(find.text('Plan de révision'), findsOneWidget);
    expect(find.byIcon(Icons.menu), findsNothing);
    await tester.tap(find.text('Plan de révision'));
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.byType(ChatScreen), findsOneWidget); // choisir une discussion ne ferme pas l'écran
    expect(tester.takeException(), isNull);
  });

  testWidgets('téléphone et petite tablette : tiroir, bouton de menu', (tester) async {
    await open(tester, 800);
    expect(find.byType(HistoryDrawer), findsNothing);
    expect(find.byIcon(Icons.menu), findsOneWidget);
    await tester.tap(find.byIcon(Icons.menu));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byType(HistoryDrawer), findsOneWidget);
  });

  testWidgets('« Demander à Tontolo » : le curseur arrive dans la saisie', (tester) async {
    final chat = await open(tester, 800);
    final field = find.byType(TextField);
    expect(tester.widget<TextField>(field).focusNode!.hasFocus, isFalse);
    chat.requestInputFocus();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.widget<TextField>(field).focusNode!.hasFocus, isTrue);
  });

  testWidgets('longue discussion (240 messages chargés par pages) : affichage paresseux et fluide', (tester) async {
    final chat = await open(tester, 800);
    // Le cœur ne livre qu'une page à la fois (« Messages précédents ») : 240 messages en mémoire
    // représentent déjà six pages ouvertes à la main.
    for (var i = 0; i < 240; i++) {
      chat.messages.add(ChatMessage(
          role: i.isEven ? 'user' : 'assistant',
          text: i.isEven
              ? 'Question $i sur les fractions ?'
              : 'Réponse $i : **gras**, \$\\frac{a}{b}\$ et une liste\n\n- un\n- deux\n\n```python\nprint($i)\n```'));
    }
    final clock = Stopwatch()..start();
    chat.requestInputFocus(); // reconstruit l'écran avec tous les messages
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50)); // saut en bas, puis correction d'étendue
    final opening = clock.elapsedMilliseconds;
    expect(tester.takeException(), isNull);
    expect(find.byType(MessageView).evaluate().length, lessThan(30)); // seuls les visibles
    clock.reset();
    final list = find.byType(Scrollable).first;
    for (var i = 0; i < 5; i++) {
      await tester.drag(list, const Offset(0, 600));
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(tester.takeException(), isNull);
    expect(find.byType(MessageView).evaluate().length, lessThan(30));
    // Mesuré en mode débogage (≈ 10 fois plus lent qu'en version publiée) et sur une machine
    // parfois chargée : large marge ; la vraie garde est le nombre de messages construits (< 30).
    expect(opening, lessThan(15000), reason: 'ouverture : $opening ms');
    expect(clock.elapsedMilliseconds, lessThan(15000), reason: 'défilement : ${clock.elapsedMilliseconds} ms');
  });

  testWidgets('sous la dernière réponse : raccourcis (plus de détails, exemple…), un toucher envoie', (tester) async {
    final chat = await open(tester, 800);
    chat.messages
      ..add(ChatMessage(role: 'user', text: 'Explique la photosynthèse'))
      ..add(ChatMessage(role: 'assistant', text: 'La photosynthèse est un processus. ' * 12));
    chat.requestInputFocus();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Plus de détails'), findsOneWidget);
    // Un bandeau « vérifié par… » après la réponse ne les fait pas disparaître.
    chat.messages.add(ChatMessage(role: 'notice', text: 'review|1|Autre modèle|'));
    chat.requestInputFocus();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Plus de détails'), findsOneWidget);
    await tester.tap(find.text('Un exemple'));
    await tester.pump();
    final body = core.sentBodies.single as Map;
    expect(body['content'], 'Donne un exemple concret.');
    // Réponse courte ou déjà en cours : pas de raccourcis.
    chat.messages
      ..clear()
      ..add(ChatMessage(role: 'assistant', text: 'Oui.'));
    chat.requestInputFocus();
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Plus de détails'), findsNothing);
  });
}
