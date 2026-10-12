import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/account.dart';
import 'package:tontolo/core/activity.dart';
import 'package:tontolo/core/backend.dart';
import 'package:tontolo/core/chat_controller.dart';
import 'package:tontolo/core/cloud_sync.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/l10n/strings.dart';

void main() {
  test('pastilles : attend > ici > autre appareil, et badge « ailleurs »', () async {
    SharedPreferences.setMockInitialValues({});
    final backend = Backend(await Prefs.load());
    final chat = ChatController(backend);
    final cloud = CloudSync(backend, Account());
    final a = ActivityWatcher(backend, cloud, chat);
    chat.conversationId = 'courante';

    expect(a.dotFor('x'), isNull);
    expect(a.elsewhere, isNull);

    a.running = {'x', 'courante'};
    expect(a.dotFor('x'), Dot.local);
    expect(a.elsewhere, Dot.local); // x tourne pendant qu'on regarde « courante »

    a.waiting = {'x': {'reason': 'question', 'title': 'X'}};
    expect(a.dotFor('x'), Dot.waiting); // l'attente passe devant « en cours »
    expect(a.elsewhere, Dot.waiting);

    a.running = {'courante'};
    a.waiting = {};
    expect(a.elsewhere, isNull); // ce qui se passe ICI n'est pas « ailleurs »
  });

  test('textes des pastilles et avertissements dans les trois langues', () {
    for (final l in ['fr', 'en', 'mg']) {
      for (final k in ['dot_waiting', 'dot_local', 'dot_remote', 'attention_question', 'attention_tool', 'attention_paid']) {
        expect(tr(l, k, {'t': 'X'}), isNot(k));
      }
    }
    expect(tr('fr', 'attention_question', {'t': 'Maths'}), '« Maths » vous pose une question');
  });
}
