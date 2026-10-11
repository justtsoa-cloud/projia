// Compte Tontolo (facultatif) : connexion Google ou GitHub via Supabase Auth, flux PKCE.
// Le compte donne seulement l'ACCÈS à ses données synchronisées ; leur LECTURE exige la
// phrase secrète de synchronisation (voir cloud_sync.dart) : la base ne voit que des blobs
// chiffrés. Jetons conservés dans le stockage sécurisé du système.

import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart' as hash;
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_web_auth_2/flutter_web_auth_2.dart';
import 'package:http/http.dart' as http;

const supabaseUrl = String.fromEnvironment('TONTOLO_STATS_URL');
const supabaseKey = String.fromEnvironment('TONTOLO_STATS_KEY');

/// Retour de connexion : schéma de l'application (Android) ou serveur local (bureau).
const androidCallback = 'io.github.raantss18.tontolo://login-callback';
const desktopCallback = 'http://localhost:43823/';

class Session {
  Session(this.accessToken, this.refreshToken, this.expiresAt, this.userId, this.email, this.provider);

  final String accessToken;
  final String refreshToken;
  final int expiresAt; // secondes depuis l'époque
  final String userId;
  final String email;
  final String provider;

  bool get expired => DateTime.now().millisecondsSinceEpoch ~/ 1000 > expiresAt - 60;

  Map<String, dynamic> toJson() => {
        'access_token': accessToken, 'refresh_token': refreshToken, 'expires_at': expiresAt,
        'user_id': userId, 'email': email, 'provider': provider,
      };

  static Session fromJson(Map<String, dynamic> j) => Session('${j['access_token']}', '${j['refresh_token']}',
      (j['expires_at'] as num).toInt(), '${j['user_id']}', '${j['email'] ?? ''}', '${j['provider'] ?? ''}');

  /// Réponse de `/auth/v1/token`.
  static Session fromToken(Map<String, dynamic> t) {
    final user = (t['user'] as Map?)?.cast<String, dynamic>() ?? {};
    final meta = (user['app_metadata'] as Map?)?.cast<String, dynamic>() ?? {};
    final expiresAt = (t['expires_at'] as num?)?.toInt() ??
        DateTime.now().millisecondsSinceEpoch ~/ 1000 + ((t['expires_in'] as num?)?.toInt() ?? 3600);
    return Session('${t['access_token']}', '${t['refresh_token']}', expiresAt, '${user['id']}',
        '${user['email'] ?? ''}', '${meta['provider'] ?? ''}');
  }
}

class AccountError implements Exception {
  AccountError(this.code);
  final String code; // acc_not_configured | acc_cancelled | acc_failed | acc_provider_off
  @override
  String toString() => code;
}

class Account extends ChangeNotifier {
  Account({http.Client? client, FlutterSecureStorage? storage})
      : _http = client ?? http.Client(),
        _storage = storage ?? const FlutterSecureStorage();

  final http.Client _http;
  final FlutterSecureStorage _storage;
  static const _key = 'account_session';
  Session? session;

  static bool get configured => supabaseUrl.startsWith('https://') && supabaseKey.isNotEmpty;
  bool get signedIn => session != null;

  /// Méthodes de connexion activées par l'auteur dans Supabase (google, github) ; null tant
  /// qu'elles ne sont pas connues (hors ligne).
  Set<String>? providers;

  Future<void> loadProviders() async {
    if (!configured) return;
    try {
      final r = await _http.get(Uri.parse('$supabaseUrl/auth/v1/settings'), headers: {'apikey': supabaseKey}).timeout(const Duration(seconds: 10));
      if (r.statusCode != 200) return;
      final ext = ((jsonDecode(utf8.decode(r.bodyBytes)) as Map)['external'] as Map?) ?? {};
      providers = {for (final p in const ['google', 'github']) if (ext[p] == true) p};
      notifyListeners();
    } catch (_) {}
  }

  Future<void> load() async {
    try {
      final raw = await _storage.read(key: _key);
      if (raw != null) session = Session.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      session = null;
    }
    notifyListeners();
  }

  Future<void> _save(Session? s) async {
    session = s;
    if (s == null) {
      await _storage.delete(key: _key);
    } else {
      await _storage.write(key: _key, value: jsonEncode(s.toJson()));
    }
    notifyListeners();
  }

  static String _verifier() {
    final r = Random.secure();
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
    return List.generate(64, (_) => chars[r.nextInt(chars.length)]).join();
  }

  static String challengeOf(String verifier) =>
      base64Url.encode(hash.sha256.convert(utf8.encode(verifier)).bytes).replaceAll('=', '');

  /// Connexion avec `provider` (google | github) dans le navigateur du système.
  Future<void> signIn(String provider) async {
    if (!configured) throw AccountError('acc_not_configured');
    final verifier = _verifier();
    final callback = Platform.isAndroid ? androidCallback : desktopCallback;
    final url = Uri.parse('$supabaseUrl/auth/v1/authorize').replace(queryParameters: {
      'provider': provider,
      'redirect_to': callback,
      'code_challenge': challengeOf(verifier),
      'code_challenge_method': 's256',
    });
    String result;
    try {
      result = await FlutterWebAuth2.authenticate(
        url: url.toString(),
        callbackUrlScheme: Platform.isAndroid ? 'io.github.raantss18.tontolo' : 'http://localhost:43823',
      );
    } catch (e) {
      throw AccountError('acc_cancelled');
    }
    final back = Uri.parse(result);
    final params = {...back.queryParameters, ...Uri.splitQueryString(back.fragment)};
    if (params['error'] != null) {
      final desc = '${params['error_description']}'.toLowerCase();
      throw AccountError(desc.contains('provider is not enabled') || desc.contains('unsupported provider') ? 'acc_provider_off' : 'acc_failed');
    }
    final code = params['code'];
    if (code == null) throw AccountError('acc_failed');
    final r = await _http.post(Uri.parse('$supabaseUrl/auth/v1/token?grant_type=pkce'),
        headers: {'apikey': supabaseKey, 'Content-Type': 'application/json'},
        body: jsonEncode({'auth_code': code, 'code_verifier': verifier}));
    if (r.statusCode != 200) throw AccountError('acc_failed');
    await _save(Session.fromToken(jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>));
  }

  /// Jeton d'accès valide (rafraîchi si besoin) ; null si déconnecté ou session révoquée.
  Future<String?> token() async {
    final s = session;
    if (s == null) return null;
    if (!s.expired) return s.accessToken;
    final r = await _http.post(Uri.parse('$supabaseUrl/auth/v1/token?grant_type=refresh_token'),
        headers: {'apikey': supabaseKey, 'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': s.refreshToken}));
    if (r.statusCode == 200) {
      await _save(Session.fromToken(jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>));
      return session!.accessToken;
    }
    if (r.statusCode == 400 || r.statusCode == 401) await _save(null); // session révoquée
    return null;
  }

  /// Déconnexion : jetons effacés de l'appareil (données locales conservées).
  Future<void> signOut() async {
    final t = session?.accessToken;
    await _save(null);
    if (t != null) {
      try {
        await _http.post(Uri.parse('$supabaseUrl/auth/v1/logout'), headers: {'apikey': supabaseKey, 'Authorization': 'Bearer $t'});
      } catch (_) {}
    }
  }
}
