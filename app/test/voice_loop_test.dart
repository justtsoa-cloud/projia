// Conversation vocale : détection de la parole et boucle écouter → répondre → réécouter.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:projia/core/voice_loop.dart';

/// Niveaux sonores simulés, un échantillon toutes les 100 ms.
List<double> signal({int quiet = 8, int speech = 12, int pause = 20}) =>
    [for (var i = 0; i < quiet; i++) -62.0, for (var i = 0; i < speech; i++) -22.0, for (var i = 0; i < pause; i++) -60.0];

void main() {
  test('détecteur : bruit de fond, phrase, silence → fin de phrase', () {
    final d = SilenceDetector();
    final events = <VadEvent>[];
    var t = 0;
    for (final db in signal()) {
      events.add(d.feed(db, t));
      t += 100;
    }
    expect(events.where((e) => e == VadEvent.speechStarted), hasLength(1));
    expect(events, contains(VadEvent.speechEnded)); // la boucle s'arrête dès le premier
    expect(events.indexOf(VadEvent.speechStarted), lessThan(events.indexOf(VadEvent.speechEnded)));
    expect(d.threshold, lessThan(-30)); // seuil adapté au bruit de fond (~ -62 + 14)
  });

  test('détecteur : un claquement bref n\'est pas une phrase', () {
    final d = SilenceDetector();
    var t = 0;
    final events = <VadEvent>[];
    for (final db in [for (var i = 0; i < 8; i++) -62.0, -20.0, -20.0, for (var i = 0; i < 30; i++) -62.0]) {
      events.add(d.feed(db, t));
      t += 100;
    }
    expect(events, everyElement(VadEvent.none));
  });

  test('détecteur : bruit de fond fort, la parole reste détectée', () {
    final d = SilenceDetector();
    var t = 0;
    final events = <VadEvent>[];
    for (final db in [for (var i = 0; i < 8; i++) -40.0, for (var i = 0; i < 12; i++) -20.0, for (var i = 0; i < 20; i++) -40.0]) {
      events.add(d.feed(db, t));
      t += 100;
    }
    expect(events, contains(VadEvent.speechStarted));
    expect(events, contains(VadEvent.speechEnded));
  });

  test('détecteur : personne ne parle → délai dépassé', () {
    final d = SilenceDetector(maxWaitMs: 3000);
    var t = 0;
    final events = <VadEvent>[];
    for (var i = 0; i < 60; i++) {
      events.add(d.feed(-65, t));
      t += 100;
    }
    expect(events, contains(VadEvent.timedOut));
  });

  test('boucle : question → réponse lue → la conversation reprend, puis s\'arrête sans voix', () async {
    final log = <String>[];
    var clock = 0;
    var round = 0;
    final loop = VoiceLoop(
      clock: () => clock,
      begin: () async {
        round++;
        log.add('écoute $round');
        // 1er tour : une phrase ; 2e tour : rien (silence).
        final levels = round == 1 ? signal() : [for (var i = 0; i < 200; i++) -66.0];
        return Stream<double>.periodic(const Duration(milliseconds: 1), (i) {
          clock += 100;
          return levels[i % levels.length];
        }).take(levels.length);
      },
      finish: () async => '/tmp/voix.wav',
      transcribe: (path) async => 'Quelle est la capitale du Japon ?',
      ask: (text) async => log.add('question: $text'),
      answer: () => 'Tokyo.',
      speak: (text) async => log.add('lecture: $text'),
      stopSpeaking: () async {},
    );
    final states = <VoiceState>[];
    loop.addListener(() => states.add(loop.state));
    await loop.start();
    expect(log, ['écoute 1', 'question: Quelle est la capitale du Japon ?', 'lecture: Tokyo.', 'écoute 2']);
    expect(states, containsAllInOrder([VoiceState.listening, VoiceState.hearing, VoiceState.transcribing, VoiceState.thinking, VoiceState.speaking, VoiceState.listening, VoiceState.off]));
    expect(loop.state, VoiceState.off);
    expect(loop.lastError, isNull);
  });

  test('boucle : micro refusé, arrêt manuel et réponse vide', () async {
    final denied = VoiceLoop(
      begin: () async => null,
      finish: () async => null,
      transcribe: (_) async => '',
      ask: (_) async {},
      answer: () => null,
      speak: (_) async {},
      stopSpeaking: () async {},
    );
    await denied.start();
    expect(denied.lastError, 'mic_denied');
    expect(denied.state, VoiceState.off);

    final controller = StreamController<double>();
    final loop = VoiceLoop(
      begin: () async => controller.stream,
      finish: () async => null,
      transcribe: (_) async => '',
      ask: (_) async {},
      answer: () => null,
      speak: (_) async {},
      stopSpeaking: () async {},
    );
    final running = loop.start();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    expect(loop.state, VoiceState.listening);
    await loop.stop();
    await running;
    expect(loop.state, VoiceState.off);
    await controller.close();
  });
}
