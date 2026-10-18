// Mise en route du rappel subtil : à la mise en arrière-plan on prépare UN titre récent et on
// programme UNE notification locale ; au retour on l'annule. Tout reste sur l'appareil.
import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'backend.dart';
import 'comeback.dart';
import 'notifier.dart';
import 'prefs.dart';

class ComebackRunner {
  ComebackRunner._();

  static const _topic = 'comeback';

  /// L'application passe en arrière-plan.
  static Future<void> onPause(Prefs prefs, Backend backend) async {
    if (!prefs.cbEnabled) return;
    final now = DateTime.now();
    final last = prefs.cbLastFired == 0 ? null : DateTime.fromMillisecondsSinceEpoch(prefs.cbLastFired);
    final at = Comeback.fireTime(pausedAt: now, lastFired: last, enabled: true);
    if (at == null || backend.state != BackendState.ready) return;
    try {
      final home = await backend.getJson('/tontolo/home') as Map<String, dynamic>;
      final topics = [for (final t in (home['tracks'] as List? ?? const [])) '${(t as Map)['topic']}'];
      if (topics.isEmpty) return; // pas de centre d'intérêt connu : aucun rappel creux
      final headline = await Comeback.fetch(topics, prefs.locale, now);
      if (headline == null) return; // rien de chaud et de pertinent : on ne dérange pas
      prefs.cbNews = jsonEncode({'title': headline.title, 'link': headline.link, 'at': now.millisecondsSinceEpoch});
      final ok = await Notifier.scheduleAt(at, _topic, _tr(prefs.locale, 'title'), headline.title);
      prefs.cbFireAt = ok ? at.millisecondsSinceEpoch : 0;
    } catch (e) {
      debugPrint('Rappel non préparé : $e');
    }
  }

  /// Retour au premier plan : rien ne doit plus partir ; on note si un rappel était déjà parti.
  static Future<void> onResume(Prefs prefs) async {
    final fire = prefs.cbFireAt;
    if (fire != 0 && fire <= DateTime.now().millisecondsSinceEpoch) prefs.cbLastFired = fire;
    prefs.cbFireAt = 0;
    await Notifier.cancel(_topic);
  }

  static String _tr(String lang, String key) => const {
        'fr': {'title': 'Une actualité dans votre domaine'},
        'en': {'title': 'News in your field'},
        'mg': {'title': 'Vaovao amin\'ny sehatrao'},
      }[lang]?[key] ?? 'Tontolo';
}
