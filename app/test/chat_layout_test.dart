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

class _Core extends Backend {
  _Core(super.prefs) {
    state = BackendState.ready;
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
  Future<ChatController> open(WidgetTester tester, double width) async {
    SharedPreferences.setMockInitialValues({'locale': 'fr'});
    final prefs = await Prefs.load();
    final core = _Core(prefs);
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
}
