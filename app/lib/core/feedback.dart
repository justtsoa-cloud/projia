// Retours d'expérience (P4) : une carte discrète, rarement, jamais pendant une tâche.
//  - elle n'apparaît qu'après plusieurs vraies discussions ET une semaine d'usage ;
//  - ignorée, elle revient 30 puis 60 jours plus tard, puis plus jamais ;
//  - le retour reste sur l'appareil ; l'envoi à l'auteur est proposé à chaque fois (décoché).
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'prefs.dart';
import 'stats.dart';
import 'updater.dart' show appVersion;

const _day = 24 * 3600 * 1000;

class AppFeedback {
  AppFeedback._();

  static const minConversations = 5;
  static const minDays = 7;
  static const reasons = ['slow', 'wrong', 'language', 'interface', 'missing', 'other'];

  /// Faut-il montrer la carte maintenant ? Fonction pure, testée.
  static bool shouldAsk({
    required int nowMs,
    required int firstSeenMs,
    required int conversations,
    required int lastAskedMs,
    required int dismissals,
    required bool done,
    bool busy = false,
  }) {
    if (done || busy || dismissals >= 3) return false;
    if (conversations < minConversations) return false;
    if (nowMs - firstSeenMs < minDays * _day) return false;
    if (lastAskedMs == 0) return true;
    final wait = dismissals == 0 ? 30 : (dismissals == 1 ? 30 : 60);
    return nowMs - lastAskedMs >= wait * _day;
  }

  static bool ask(Prefs prefs, int conversations, {bool busy = false}) => shouldAsk(
        nowMs: DateTime.now().millisecondsSinceEpoch,
        firstSeenMs: prefs.firstSeen,
        conversations: conversations,
        lastAskedMs: prefs.fbLastAsked,
        dismissals: prefs.fbDismissals,
        done: prefs.fbDone,
        busy: busy,
      );

  /// « Plus tard » ou fermeture : repoussée de 30 puis 60 jours, puis plus jamais.
  static void dismiss(Prefs prefs) {
    prefs.fbLastAsked = DateTime.now().millisecondsSinceEpoch;
    prefs.fbDismissals = prefs.fbDismissals + 1;
  }

  /// Champs envoyés (liste blanche exacte) : jamais de texte de discussion ni d'identifiant.
  static Map<String, Object> payload({required int mood, List<String> why = const [],
      String note = '', int rating = 0, required String locale}) {
    return {
      'mood': mood.clamp(1, 3),
      'reasons': [for (final r in why) if (reasons.contains(r)) r],
      'note': note.length > 280 ? note.substring(0, 280) : note,
      'rating': rating.clamp(0, 5),
      'app_version': appVersion,
      'app_locale': {'fr', 'en', 'mg'}.contains(locale) ? locale : 'en',
    };
  }

  /// Garde le retour sur l'appareil (au plus 20) ; l'envoi est une décision séparée.
  static void keep(Prefs prefs, Map<String, Object> entry) {
    final list = (jsonDecode(prefs.fbLog) as List).cast<Map<String, dynamic>>()
      ..add({...entry, 'at': DateTime.now().millisecondsSinceEpoch});
    prefs.fbLog = jsonEncode(list.length > 20 ? list.sublist(list.length - 20) : list);
    prefs.fbLastAsked = DateTime.now().millisecondsSinceEpoch;
    if (entry['mood'] != null) prefs.fbDone = true;
  }

  /// Envoi à l'auteur, uniquement si l'utilisateur l'a accepté pour CE retour.
  static Future<bool> send(Map<String, Object> entry,
      {http.Client? client, String? statsUrl, String? statsKey}) async {
    final url = statsUrl ?? Stats.url, key = statsKey ?? Stats.key;
    if (!url.startsWith('https://') || key.isEmpty) return false;
    final transport = client ?? http.Client();
    try {
      final r = await transport.post(Uri.parse('$url/rest/v1/feedback'),
          headers: {'apikey': key, 'Authorization': 'Bearer $key',
            'Content-Type': 'application/json', 'Prefer': 'return=minimal'},
          body: jsonEncode(entry)).timeout(const Duration(seconds: 15));
      return r.statusCode >= 200 && r.statusCode < 300;
    } catch (_) {
      return false;
    } finally {
      if (client == null) transport.close();
    }
  }
}
