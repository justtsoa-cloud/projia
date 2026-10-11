// Statistiques anonymes d'utilisation, envoyées au plus une fois par jour vers la base de
// l'auteur (Supabase, insertion seule). Aucun message, aucune image, aucune clé, aucun nom :
// un identifiant d'installation aléatoire, la version, le système, la langue, le pays de la
// langue du téléphone et le nombre de messages envoyés depuis le dernier envoi.
// Désactivable dans Réglages ; inactif si l'adresse de la base n'est pas configurée.

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'prefs.dart';
import 'updater.dart' show appVersion;

const _statsUrl = String.fromEnvironment('TONTOLO_STATS_URL');
const _statsKey = String.fromEnvironment('TONTOLO_STATS_KEY');

class Stats {
  Stats._();

  static bool get configured => _statsUrl.startsWith('https://') && _statsKey.isNotEmpty;

  /// Un message envoyé (compteur local, transmis lors du prochain envoi quotidien).
  static void countMessage(Prefs prefs) => prefs.usageCount = prefs.usageCount + 1;

  static String _newId() {
    final r = Random.secure();
    return List.generate(16, (_) => r.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
  }

  /// Données envoyées (exposées pour les tests et l'écran « Voir ce qui est envoyé »).
  static Map<String, Object> payload(Prefs prefs) {
    final locale = Platform.localeName; // ex. fr_MG
    final parts = locale.split(RegExp('[_.-]'));
    return {
      'install_id': prefs.installId,
      'app_version': appVersion,
      'platform': Platform.operatingSystem,
      'os_version': _osMajor(),
      'abi': _abi(),
      'app_locale': prefs.locale,
      'country': parts.length > 1 && parts[1].length == 2 ? parts[1].toUpperCase() : '',
      'messages': prefs.usageCount,
    };
  }

  static String _osMajor() {
    // « Android 14 », « Linux » : sans modèle d'appareil ni numéro de build.
    final v = Platform.operatingSystemVersion;
    if (Platform.isAndroid) {
      final m = RegExp(r'(\d+)').firstMatch(v);
      return m == null ? 'Android' : 'Android ${m.group(1)}';
    }
    return Platform.operatingSystem[0].toUpperCase() + Platform.operatingSystem.substring(1);
  }

  static String _abi() {
    final m = RegExp(r'on "\w+_(\w+)"').firstMatch(Platform.version);
    return m?.group(1) ?? '';
  }

  /// Envoi quotidien (au démarrage). Silencieux en cas d'échec : réessayé le lendemain.
  static Future<void> maybeSend(Prefs prefs) async {
    if (!configured || !prefs.shareStats) return;
    final today = DateTime.now().toUtc().difference(DateTime.utc(2026)).inDays;
    if (prefs.lastStatsDay == today) return;
    if (prefs.installId.isEmpty) prefs.installId = _newId();
    try {
      final r = await http
          .post(Uri.parse('$_statsUrl/rest/v1/pings'),
              headers: {
                'apikey': _statsKey,
                'Authorization': 'Bearer $_statsKey',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
              },
              body: jsonEncode(payload(prefs)))
          .timeout(const Duration(seconds: 15));
      if (r.statusCode >= 200 && r.statusCode < 300) {
        prefs.lastStatsDay = today;
        prefs.usageCount = 0;
      }
    } catch (e) {
      debugPrint('Statistiques non envoyées : $e');
    }
  }
}
