// Retours d'expérience : rares, discrets, envoyés seulement si la personne l'accepte.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:projia/core/feedback.dart';
import 'package:projia/l10n/strings.dart';

const day = 24 * 3600 * 1000;

bool ask({int days = 10, int convs = 6, int last = 0, int dismissals = 0, bool done = false, bool busy = false}) =>
    AppFeedback.shouldAsk(
      nowMs: 100 * day,
      firstSeenMs: (100 - days) * day,
      conversations: convs,
      lastAskedMs: last,
      dismissals: dismissals,
      done: done,
      busy: busy,
    );

void main() {
  test('seulement après 5 discussions ET 7 jours', () {
    expect(ask(), isTrue);
    expect(ask(convs: 4), isFalse);
    expect(ask(days: 6), isFalse);
  });

  test('jamais pendant une tâche, ni une fois le retour donné', () {
    expect(ask(busy: true), isFalse);
    expect(ask(done: true), isFalse);
  });

  test('ignorée : revient après 30 jours, puis 60, puis plus jamais', () {
    expect(ask(dismissals: 1, last: 80 * day), isFalse); // 20 jours
    expect(ask(dismissals: 1, last: 65 * day), isTrue); // 35 jours
    expect(ask(dismissals: 2, last: 65 * day), isFalse); // 35 < 60
    expect(ask(dismissals: 2, last: 35 * day), isTrue); // 65 jours
    expect(ask(dismissals: 3, last: 1 * day), isFalse); // plus jamais
  });

  test('liste blanche des champs envoyés', () {
    final p = AppFeedback.payload(mood: 1, why: ['slow', 'pirate'], note: 'x' * 400, rating: 9, locale: 'de');
    expect(p.keys.toSet(), {'mood', 'reasons', 'note', 'rating', 'app_version', 'app_locale'});
    expect(p['reasons'], ['slow']); // raison inconnue écartée
    expect((p['note'] as String).length, 280);
    expect(p['rating'], 5);
    expect(p['app_locale'], 'en');
  });

  test('envoi : rien sans adresse configurée ; corps exact sinon', () async {
    final entry = AppFeedback.payload(mood: 3, locale: 'fr');
    expect(await AppFeedback.send(entry, statsUrl: '', statsKey: ''), isFalse);
    var calls = 0;
    final client = MockClient((request) async {
      calls++;
      expect(request.url.path, '/rest/v1/feedback');
      expect((jsonDecode(request.body) as Map).keys.toSet(), entry.keys.toSet());
      return http.Response('', 201);
    });
    expect(await AppFeedback.send(entry, client: client, statsUrl: 'https://s.example', statsKey: 'anon'), isTrue);
    expect(calls, 1);
  });

  test('textes dans les trois langues', () {
    for (final k in ['fb_question', 'fb_bad', 'fb_ok', 'fb_great', 'fb_later', 'fb_thanks', 'fb_why', 'fb_r_slow',
      'fb_r_wrong', 'fb_r_language', 'fb_r_interface', 'fb_r_missing', 'fb_r_other', 'fb_note', 'fb_send',
      'fb_send_help', 'fb_done', 'rate_app', 'rate_app_help', 'fb_send_rating', 'fb_sent', 'fb_star', 'fb_share_help']) {
      for (final l in ['fr', 'en', 'mg']) {
        expect(tr(l, k), isNot(k), reason: '$l/$k');
      }
    }
  });
}
