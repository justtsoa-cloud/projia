// Préférences locales de l'application (non sensibles).

import 'dart:math';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class Prefs extends ChangeNotifier {
  Prefs(this._sp);

  final SharedPreferences _sp;

  static Future<Prefs> load() async {
    final sp = await SharedPreferences.getInstance();
    // Mise à jour depuis une version qui ne mémorisait pas la dernière version vue :
    // on la considère comme 0.2.0 pour présenter les nouveautés (et non « 1re installation »).
    if ((sp.getBool('onboarded') ?? false) && (sp.getString('lastSeenVersion') ?? '').isEmpty) {
      await sp.setString('lastSeenVersion', '0.2.0');
    }
    return Prefs(sp);
  }

  ThemeMode get themeMode => ThemeMode.values[_sp.getInt('theme') ?? 0];
  set themeMode(ThemeMode m) => _set(() => _sp.setInt('theme', m.index));

  double get textScale => _sp.getDouble('textScale') ?? 1.0;
  set textScale(double v) => _set(() => _sp.setDouble('textScale', v));

  bool get reduceMotion => _sp.getBool('reduceMotion') ?? false;
  set reduceMotion(bool v) => _set(() => _sp.setBool('reduceMotion', v));

  String get locale => _sp.getString('locale') ?? 'fr';
  set locale(String v) => _set(() => _sp.setString('locale', v));

  /// URL du serveur distant ; vide = mode local (cœur embarqué).
  String get remoteUrl => _sp.getString('remoteUrl') ?? '';
  set remoteUrl(String v) => _set(() => _sp.setString('remoteUrl', v));

  /// Vitesse de lecture à voix haute (0.3 lent → 0.8 rapide).
  double get speechRate => _sp.getDouble('speechRate') ?? 0.5;
  set speechRate(double v) => _set(() => _sp.setDouble('speechRate', v));

  /// Dernière version dont les nouveautés ont été présentées (« Quoi de neuf »).
  String get lastSeenVersion => _sp.getString('lastSeenVersion') ?? '';
  set lastSeenVersion(String v) => _set(() => _sp.setString('lastSeenVersion', v));

  /// Version de mise à jour dont l'annonce a déjà été affichée (une seule fois par version).
  String get promptedUpdate => _sp.getString('promptedUpdate') ?? '';
  set promptedUpdate(String v) => _set(() => _sp.setString('promptedUpdate', v));

  bool get onboarded => _sp.getBool('onboarded') ?? false;
  set onboarded(bool v) => _set(() => _sp.setBool('onboarded', v));

  bool get autoUpdate => _sp.getBool('autoUpdate') ?? true;
  // Statistiques anonymes d'utilisation (activées par défaut, annoncées, désactivables).
  bool get shareStats => _sp.getBool('shareStats') ?? true;
  set shareStats(bool v) => _set(() => _sp.setBool('shareStats', v));
  String get installId => _sp.getString('installId') ?? '';
  set installId(String v) => _sp.setString('installId', v);
  int get lastStatsDay => _sp.getInt('lastStatsDay') ?? 0;
  set lastStatsDay(int v) => _sp.setInt('lastStatsDay', v);
  int get usageCount => _sp.getInt('usageCount') ?? 0;
  set usageCount(int v) => _sp.setInt('usageCount', v);
  set autoUpdate(bool v) => _set(() => _sp.setBool('autoUpdate', v));

  bool get notifyNewFree => _sp.getBool('notifyNewFree') ?? false;
  set notifyNewFree(bool v) => _set(() => _sp.setBool('notifyNewFree', v));

  /// Serveur Tontolo avec lequel synchroniser l'historique (mode local).
  String get syncUrl => _sp.getString('syncUrl') ?? '';
  set syncUrl(String v) => _set(() => _sp.setString('syncUrl', v));

  bool get syncEnabled => _sp.getBool('syncEnabled') ?? false;
  set syncEnabled(bool v) => _set(() => _sp.setBool('syncEnabled', v));

  double get lastSync => _sp.getDouble('lastSync') ?? 0;
  set lastSync(double v) => _sp.setDouble('lastSync', v);

  /// Mode Apprendre pour les nouvelles discussions, et niveau scolaire choisi.
  bool get learnMode => _sp.getBool('learnMode') ?? false;
  set learnMode(bool v) => _set(() => _sp.setBool('learnMode', v));
  String get learnLevel => _sp.getString('learnLevel') ?? 'lycee';
  set learnLevel(String v) => _set(() => _sp.setString('learnLevel', v));

  // Synchronisation par compte (chiffrée de bout en bout).
  bool get cloudSync => _sp.getBool('cloudSync') ?? false;
  set cloudSync(bool v) => _set(() => _sp.setBool('cloudSync', v));
  double get cloudLastPush => _sp.getDouble('cloudLastPush') ?? 0;
  set cloudLastPush(double v) => _sp.setDouble('cloudLastPush', v);
  String get cloudLastPull => _sp.getString('cloudLastPull') ?? '';
  set cloudLastPull(String v) => _sp.setString('cloudLastPull', v);
  double get cloudCreationsPush => _sp.getDouble('cloudCreationsPush') ?? 0;
  set cloudCreationsPush(double v) => _sp.setDouble('cloudCreationsPush', v);
  /// Identifiant aléatoire de cet appareil (suivi en direct des tâches entre appareils).
  String get deviceId {
    var id = _sp.getString('deviceId');
    if (id == null) {
      final r = Random.secure();
      id = List.generate(12, (_) => r.nextInt(16).toRadixString(16)).join();
      _sp.setString('deviceId', id);
    }
    return id;
  }
  String get cloudKeysHash => _sp.getString('cloudKeysHash') ?? '';
  set cloudKeysHash(String v) => _sp.setString('cloudKeysHash', v);
  Set<String> get cloudMemories => (_sp.getStringList('cloudMemories') ?? const []).toSet();
  set cloudMemories(Set<String> v) => _sp.setStringList('cloudMemories', v.toList());

  int get lastUpdateCheck => _sp.getInt('lastUpdateCheck') ?? 0;
  set lastUpdateCheck(int v) => _sp.setInt('lastUpdateCheck', v);

  void _set(Future<bool> Function() write) {
    write();
    notifyListeners();
  }
}
