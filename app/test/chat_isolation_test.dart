// Une lecture retardée ne doit jamais compléter la discussion suivante.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/backend.dart';
import 'package:tontolo/core/chat_controller.dart';
import 'package:tontolo/core/prefs.dart';

class DelayedBackend extends Backend {
  DelayedBackend(super.prefs);
  final responses = <String, Completer<dynamic>>{};

  @override
  Future<dynamic> getJson(String path, [Map<String, dynamic>? query]) {
    if (path.endsWith('/documents')) return Future.value(<dynamic>[]);
    return (responses[path.split('?').first] ??= Completer<dynamic>()).future;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('ouvrir B pendant le chargement de A ne mélange pas les messages', () async {
    SharedPreferences.setMockInitialValues({});
    final backend = DelayedBackend(await Prefs.load());
    final chat = ChatController(backend);
    final first = chat.open('a');
    final second = chat.open('b');
    backend.responses['/tontolo/conversations/b']!.complete({
      'messages': [{'role': 'user', 'content': 'Sujet B'}],
    });
    await second;
    backend.responses['/tontolo/conversations/a']!.complete({
      'messages': [{'role': 'user', 'content': 'Sujet A'}],
    });
    await first;
    expect(chat.conversationId, 'b');
    expect(chat.messages.map((m) => m.text), ['Sujet B']);
    expect(chat.busy, isFalse);
    chat.dispose();
  });

  test('nouvelle discussion pendant une lecture média annule son affichage tardif', () async {
    SharedPreferences.setMockInitialValues({});
    final backend = DelayedBackend(await Prefs.load());
    final chat = ChatController(backend);
    final opening = chat.open('a');
    backend.responses['/tontolo/conversations/a']!.complete({
      'messages': [{'role': 'assistant', 'content': '[média:aa]'}],
    });
    // La première lecture déclenche le chargement du média.
    await Future<void>.delayed(Duration.zero);
    expect(backend.responses.containsKey('/tontolo/media/aa'), isTrue);
    chat.newChat();
    backend.responses['/tontolo/media/aa']!.complete({'id': 'aa', 'status': 'done'});
    await opening;
    expect(chat.conversationId, isNull);
    expect(chat.messages, isEmpty);
    expect(chat.busy, isFalse);
    chat.dispose();
  });

  test('fil long : fenêtre récente, puis messages précédents ajoutés en tête', () async {
    SharedPreferences.setMockInitialValues({});
    final backend = DelayedBackend(await Prefs.load());
    final chat = ChatController(backend);
    final opening = chat.open('a');
    backend.responses['/tontolo/conversations/a']!.complete({
      'total': 4,
      'messages': [
        {'role': 'user', 'content': 'trois', '_meta': {'seq': 3}},
        {'role': 'assistant', 'content': 'quatre', '_meta': {'seq': 4}},
      ],
    });
    await opening;
    expect(chat.earlierLeft, 2);
    backend.responses['/tontolo/conversations/a'] = Completer<dynamic>()
      ..complete({
        'total': 4,
        'messages': [
          {'role': 'user', 'content': 'un', '_meta': {'seq': 1}},
          {'role': 'assistant', 'content': 'deux', '_meta': {'seq': 2}},
        ],
      });
    await chat.loadEarlier();
    expect(chat.messages.map((m) => m.text), ['un', 'deux', 'trois', 'quatre']);
    expect(chat.earlierLeft, 0);
    chat.dispose();
  });

  test('question restée sans réponse ni tour en cours : message clair, jamais un écran muet', () async {
    SharedPreferences.setMockInitialValues({});
    final backend = DelayedBackend(await Prefs.load());
    final chat = ChatController(backend);
    final opening = chat.open('a');
    backend.responses['/tontolo/conversations/a']!.complete({
      'active': false,
      'messages': [{'role': 'user', 'content': 'Quelles sont les actualités importantes aujourd\'hui ?'}],
    });
    await opening;
    expect(chat.messages.last.role, 'notice');
    expect(chat.messages.last.text, startsWith('errorc|no_answer'));
    chat.dispose();
  });
}
