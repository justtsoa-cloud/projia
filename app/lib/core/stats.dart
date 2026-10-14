// Statistiques minimales : langue, région de la langue du téléphone et version seulement.
// Aucun identifiant, compteur, note, texte, nom, clé personnelle ni position.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'prefs.dart';
import 'updater.dart' show appVersion;

const _statsUrl = String.fromEnvironment('TONTOLO_STATS_URL');
const _statsKey = String.fromEnvironment('TONTOLO_STATS_KEY');

class Stats {
  Stats._();

  static bool get configured => _statsUrl.startsWith('https://') && _statsKey.isNotEmpty;

  /// Compteur strictement local ; absent du corps envoyé.
  static void countMessage(Prefs prefs) => prefs.usageCount = prefs.usageCount + 1;

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
  static Future<void> maybeSend(Prefs prefs, {http.Client? client,
      String statsUrl = _statsUrl, String statsKey = _statsKey}) async {
    prefs.pendingRatings = '[]';
    prefs.sentRatings = [];
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
    } catch (_) {
      debugPrint('Statistiques non envoyées.');
    } finally {
      if (client == null) transport.close();
    }
  }
}
