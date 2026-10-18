// Statistiques minimales : langue, région de la langue du téléphone et version seulement.
// Aucun identifiant, compteur, texte, nom, clé personnelle ni position.
// Les notes 👍/👎 (modèle, type de demande, note, raison ; jamais le texte) ne sont partagées que
// si l'utilisateur active l'option « Partager mes notes » ; elles portent alors un identifiant
// aléatoire d'installation, pour qu'une réponse ne compte qu'une fois.
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'backend.dart';
import 'prefs.dart';
import 'updater.dart' show appVersion;

const _statsUrl = String.fromEnvironment('TONTOLO_STATS_URL');
const _statsKey = String.fromEnvironment('TONTOLO_STATS_KEY');

class Stats {
  Stats._();

  static String get url => _statsUrl;
  static String get key => _statsKey;

  static bool get configured => _statsUrl.startsWith('https://') && _statsKey.isNotEmpty;

  /// Compteur strictement local ; absent du corps envoyé.
  static void countMessage(Prefs prefs) => prefs.usageCount = prefs.usageCount + 1;

  // --- Notes 👍 / 👎 : modèle, type de demande, note, raison. Jamais de texte. -------------

  static List<Map<String, dynamic>> pendingRatings(Prefs prefs) {
    try {
      return (jsonDecode(prefs.pendingRatings) as List).cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  /// Ajoute (ou remplace, si l'avis change avant l'envoi) la note d'une réponse ; 0 l'annule.
  static void queueRating(Prefs prefs, {required String answerId, required String model,
      required String category, required int rating, String reason = '', bool cached = false}) {
    final list = pendingRatings(prefs)..removeWhere((r) => r['answer_id'] == answerId);
    if (!prefs.shareRatings) return; // option désactivée : l'avis reste local
    if (prefs.sentRatings.contains(answerId)) return; // déjà partagée : l'avis local suffit
    if (rating != 0 && RegExp(r'^[0-9a-f]{32}$').hasMatch(answerId) && model.isNotEmpty) {
      list.add({
        'answer_id': answerId, 'model': model, 'category': category, 'rating': rating,
        'reason': reason, 'cached': cached,
      });
    }
    prefs.pendingRatings = jsonEncode(list.length > 500 ? list.sublist(list.length - 500) : list);
  }

  static String _newId() {
    final r = Random.secure();
    return List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }

  static Map<String, String> get _headers => {
        'apikey': _statsKey,
        'Authorization': 'Bearer $_statsKey',
        'Content-Type': 'application/json',
      };

  /// Envoie les notes en attente : d'un bloc ; en cas de refus (doublon), une par une.
  static Future<void> _sendRatings(Prefs prefs) async {
    final list = pendingRatings(prefs);
    if (list.isEmpty) return;
    final base = {
      'install_id': prefs.installId, 'app_version': appVersion,
      'platform': Platform.operatingSystem, 'app_locale': prefs.locale,
    };
    Future<int> post(Object body) async => (await http
            .post(Uri.parse('$_statsUrl/rest/v1/ratings'),
                headers: {..._headers, 'Prefer': 'return=minimal'}, body: jsonEncode(body))
            .timeout(const Duration(seconds: 20)))
        .statusCode;
    final sent = <String>[];
    final status = await post([for (final x in list) {...base, ...x}]);
    if (status >= 200 && status < 300) {
      sent.addAll(list.map((x) => '${x['answer_id']}'));
    } else if (status == 409 || status == 400) {
      for (final x in list) {
        final s = await post({...base, ...x});
        if (s < 500) sent.add('${x['answer_id']}'); // acceptée, ou refusée pour de bon
      }
    }
    if (sent.isEmpty) return;
    final all = [...prefs.sentRatings, ...sent];
    prefs.sentRatings = all.length > 2000 ? all.sublist(all.length - 2000) : all;
    prefs.pendingRatings = jsonEncode(pendingRatings(prefs)..removeWhere((r) => sent.contains(r['answer_id'])));
  }

  /// Notes collectives (solde des appareils par modèle et type de demande), transmises au cœur
  /// qui en tire un bonus ou malus borné.
  static Future<void> _pullScores(Backend backend) async {
    final r = await http
        .post(Uri.parse('$_statsUrl/rest/v1/rpc/model_scores'), headers: _headers, body: '{}')
        .timeout(const Duration(seconds: 20));
    if (r.statusCode != 200) return;
    final rows = jsonDecode(utf8.decode(r.bodyBytes));
    if (rows is List && backend.state == BackendState.ready) {
      await backend.sendJson('PUT', '/tontolo/feedback/global', {'scores': rows});
    }
  }

  /// Liste blanche exacte, également montrée dans les réglages.
  static Map<String, Object> payload(Prefs prefs) {
    final parts = Platform.localeName.split(RegExp('[_.-]'));
    final country = parts.length > 1 ? parts[1].toUpperCase() : '';
    return {
      'app_version': appVersion,
      'app_locale': {'fr', 'en', 'mg'}.contains(prefs.locale) ? prefs.locale : 'en',
      'country': RegExp(r'^[A-Z]{2}$').hasMatch(country) ? country : '',
    };
  }

  /// Une tentative par jour au plus, sans envoi de la file de notes des anciennes versions.
  static Future<void> maybeSend(Prefs prefs, {http.Client? client, Backend? backend,
      String statsUrl = _statsUrl, String statsKey = _statsKey}) async {
    if (!prefs.shareRatings) {
      prefs.pendingRatings = '[]'; // option désactivée : rien n'est gardé pour l'envoi
      prefs.sentRatings = [];
    }
    if (!statsUrl.startsWith('https://') || statsKey.isEmpty || !prefs.shareStats) return;
    final today = DateTime.now().toUtc().difference(DateTime.utc(2026)).inDays;
    if (prefs.lastStatsDay == today) return;
    prefs.lastStatsDay = today;
    final transport = client ?? http.Client();
    try {
      await transport.post(Uri.parse('$statsUrl/rest/v1/pings_minimal'),
          headers: {'apikey': statsKey, 'Authorization': 'Bearer $statsKey',
            'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
          body: jsonEncode(payload(prefs))).timeout(const Duration(seconds: 15));
      if (prefs.shareRatings && client == null) {
        if (prefs.installId.isEmpty) prefs.installId = _newId();
        await _sendRatings(prefs).catchError((Object e) => debugPrint('Notes non envoyées : $e'));
        if (backend != null) {
          await _pullScores(backend).catchError((Object e) => debugPrint('Notes collectives : $e'));
        }
      }
    } catch (_) {
      debugPrint('Statistiques non envoyées.');
    } finally {
      if (client == null) transport.close();
    }
  }
}
