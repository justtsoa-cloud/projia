// Statistiques : données anonymes uniquement, rien n'est envoyé sans configuration.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/core/stats.dart';

void main() {
  ratingsOptIn();
  test('payload limité aux champs anonymes', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    final p = Stats.payload(prefs);
    expect(p.keys.toSet(),
        {'app_version', 'app_locale', 'country'});
    expect(Stats.configured, isFalse); // aucune adresse fournie à la compilation des tests
  });

  test('compteur de messages local', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    Stats.countMessage(prefs);
    Stats.countMessage(prefs);
    expect(prefs.usageCount, 2);
    expect(Stats.payload(prefs).containsKey('messages'), isFalse);
  });
  test('envoi exact, anciennes notes jamais transmises, une tentative par jour', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    prefs.shareStats = true;
    prefs.installId = 'FAUSSE_CLE_IDENTIFIANT';
    prefs.pendingRatings = '[{"answer_id":"FAUSSE_CLE_NOTE","rating":1}]';
    prefs.usageCount = 42;
    var requests = 0;
    final client = MockClient((request) async {
      requests++;
      expect(request.url.path, '/rest/v1/pings_minimal');
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body.keys.toSet(), {'app_version', 'app_locale', 'country'});
      expect(request.body, isNot(contains('FAUSSE_CLE')));
      expect(request.body, isNot(contains('42')));
      return http.Response('', 503); // même en échec, pas de boucle d'envoi
    });
    for (var i = 0; i < 2; i++) {
      await Stats.maybeSend(prefs, client: client,
          statsUrl: 'https://stats.example', statsKey: 'public-anon');
    }
    expect(requests, 1);
    expect(prefs.pendingRatings, '[]');
    client.close();
  });

  test('aucun envoi si les statistiques sont désactivées', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    prefs.shareStats = false;
    var requests = 0;
    final client = MockClient((_) async {
      requests++;
      return http.Response('', 200);
    });
    await Stats.maybeSend(prefs, client: client,
        statsUrl: 'https://stats.example', statsKey: 'public-anon');
    expect(requests, 0);
    client.close();
  });
}

void ratingsOptIn() {
  test('notes 👍/👎 : gardées seulement si l\'option est activée', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    final id = 'a' * 32;
    Stats.queueRating(prefs, answerId: id, model: 'groq:llama', category: 'code', rating: 1);
    expect(Stats.pendingRatings(prefs), isEmpty); // option désactivée : rien en attente
    prefs.shareRatings = true;
    Stats.queueRating(prefs, answerId: id, model: 'groq:llama', category: 'code', rating: -1, reason: 'too_long');
    expect(Stats.pendingRatings(prefs).single.keys.toSet(),
        {'answer_id', 'model', 'category', 'rating', 'reason', 'cached'});
    Stats.queueRating(prefs, answerId: '../x', model: 'm', category: 'chat', rating: 1);
    expect(Stats.pendingRatings(prefs), hasLength(1)); // identifiant invalide refusé
  });
}
