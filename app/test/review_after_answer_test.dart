// La réponse complète rend la main tout de suite ; la relecture arrive ensuite, sous la réponse.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:projia/core/backend.dart';
import 'package:projia/core/chat_controller.dart';
import 'package:projia/core/prefs.dart';

class _StreamBackend extends Backend {
  _StreamBackend(super.prefs);
  final events = StreamController<Map<String, dynamic>>();

  @override
  Stream<Map<String, dynamic>> sse(String path, Object? body, {String method = 'POST'}) => events.stream;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('done : la main est rendue ; la relecture arrive après et s\'ajoute', () async {
    SharedPreferences.setMockInitialValues({});
    final backend = _StreamBackend(await Prefs.load());
    final chat = ChatController(backend);
    final sending = chat.send('Combien font 17 × 23 ?');
    backend.events.add({'type': 'conversation', 'id': 'c1'});
    backend.events.add({'type': 'route', 'model': 'm', 'name': 'Modèle'});
    backend.events.add({'type': 'delta', 'content': '391'});
    await Future<void>.delayed(Duration.zero);
    expect(chat.busy, isTrue);
    backend.events.add({'type': 'done', 'message': {'role': 'assistant', 'content': '391'},
        'model': 'm', 'name': 'Modèle', 'uid': 'u1'});
    await Future<void>.delayed(Duration.zero);
    expect(chat.busy, isFalse); // l'utilisateur peut déjà écrire la suite
    backend.events.add({'type': 'step', 'step': 'answer_reviewing'});
    backend.events.add({'type': 'review', 'ok': true, 'name': 'Autre modèle', 'issues': <String>[]});
    await Future<void>.delayed(Duration.zero);
    expect(chat.messages.any((m) => m.role == 'notice' && m.text.startsWith('review|1|')), isTrue);
    await backend.events.close();
    await sending;
    chat.dispose();
  });
}
