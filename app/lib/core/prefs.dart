// Préférences locales de l'application (non sensibles).

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class Prefs extends ChangeNotifier {
  Prefs(this._sp);

  final SharedPreferences _sp;

  static Future<Prefs> load() async => Prefs(await SharedPreferences.getInstance());

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

  bool get onboarded => _sp.getBool('onboarded') ?? false;
  set onboarded(bool v) => _set(() => _sp.setBool('onboarded', v));

  bool get autoUpdate => _sp.getBool('autoUpdate') ?? true;
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

  int get lastUpdateCheck => _sp.getInt('lastUpdateCheck') ?? 0;
  set lastUpdateCheck(int v) => _sp.setInt('lastUpdateCheck', v);

  void _set(Future<bool> Function() write) {
    write();
    notifyListeners();
  }
}
