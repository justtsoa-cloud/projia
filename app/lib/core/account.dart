// Compte Tontolo (facultatif) : connexion Google ou GitHub via Supabase Auth, flux PKCE.
// Le compte donne seulement l'ACCÈS à ses données synchronisées ; leur LECTURE exige la
// phrase secrète de synchronisation (voir cloud_sync.dart) : la base ne voit que des blobs
// chiffrés. Jetons conservés dans le stockage sécurisé du système.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart' as hash;
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

const supabaseUrl = String.fromEnvironment('TONTOLO_STATS_URL');
const supabaseKey = String.fromEnvironment('TONTOLO_STATS_KEY');

/// Android revient directement dans Tontolo ; Linux utilise la boucle locale.
/// Le code reçu exige le vérificateur PKCE conservé en stockage sécurisé.
const callbackPort = 43823;
const callbackUrl = 'http://localhost:$callbackPort/';
const androidCallbackUrl = 'io.github.raantss18.tontolo://login-callback/';

bool isAndroidAuthCallback(Uri uri) =>
    uri.scheme == 'io.github.raantss18.tontolo' &&
    uri.host == 'login-callback' && uri.path == '/' &&
    !uri.hasPort && uri.userInfo.isEmpty && uri.fragment.isEmpty;

String authCallbackUrl({required bool android}) => android ? androidCallbackUrl : callbackUrl;

class Session {
  Session(this.accessToken, this.refreshToken, this.expiresAt, this.userId, this.email, this.provider, [this.name = '']);

  final String accessToken;
  final String refreshToken;
  final int expiresAt; // secondes depuis l'époque
  final String userId;
  final String email;
  final String provider;
  final String name; // nom affiché par Google ou GitHub (pour « Bonjour » + prénom)

  /// Prénom : premier mot du nom du compte.
  String get firstName => name.trim().split(RegExp(r'\s+')).first;

  bool get expired => DateTime.now().millisecondsSinceEpoch ~/ 1000 > expiresAt - 60;

  Map<String, dynamic> toJson() => {
        'access_token': accessToken, 'refresh_token': refreshToken, 'expires_at': expiresAt,
        'user_id': userId, 'email': email, 'provider': provider, 'name': name,
      };

  static Session fromJson(Map<String, dynamic> j) => Session('${j['access_token']}', '${j['refresh_token']}',
      (j['expires_at'] as num).toInt(), '${j['user_id']}', '${j['email'] ?? ''}', '${j['provider'] ?? ''}',
      '${j['name'] ?? ''}');

  /// Réponse de `/auth/v1/token`.
  static Session fromToken(Map<String, dynamic> t) {
    final user = (t['user'] as Map?)?.cast<String, dynamic>() ?? {};
    final meta = (user['app_metadata'] as Map?)?.cast<String, dynamic>() ?? {};
    final profile = (user['user_metadata'] as Map?)?.cast<String, dynamic>() ?? {};
    final name = '${profile['full_name'] ?? profile['name'] ?? profile['given_name'] ?? ''}';
    final expiresAt = (t['expires_at'] as num?)?.toInt() ??
        DateTime.now().millisecondsSinceEpoch ~/ 1000 + ((t['expires_in'] as num?)?.toInt() ?? 3600);
    return Session('${t['access_token']}', '${t['refresh_token']}', expiresAt, '${user['id']}',
        '${user['email'] ?? ''}', '${meta['provider'] ?? ''}', name);
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
  static const _pendingKey = 'account_pending_pkce';
  static const _links = MethodChannel('tontolo/auth');
  Completer<void>? _signInDone;
  bool _handlingLink = false;
  bool _signingIn = false;
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
    if (Platform.isAndroid) {
      _links.setMethodCallHandler((call) async {
        if (call.method == 'authLink' && call.arguments is String) {
          await receiveAuthLink(Uri.parse(call.arguments as String));
        }
      });
      final link = await _links.invokeMethod<String>('initialAuthLink');
      if (link != null) await receiveAuthLink(Uri.parse(link));
    }
    notifyListeners();
  }

  /// Retour Android : accepte seulement un code PKCE pour une connexion en attente.
  Future<void> receiveAuthLink(Uri uri) async {
    if (!isAndroidAuthCallback(uri) || _handlingLink) return;
    _handlingLink = true;
    try {
      final raw = await _storage.read(key: _pendingKey);
      if (raw == null) return;
      final pending = jsonDecode(raw) as Map<String, dynamic>;
      final started = (pending['started'] as num).toInt();
      if (DateTime.now().millisecondsSinceEpoch - started > 300000) {
        throw AccountError('acc_cancelled');
      }
      await _exchange(uri, pending['verifier'] as String);
      if (_signInDone != null && !_signInDone!.isCompleted) _signInDone!.complete();
    } catch (_) {
      if (_signInDone != null && !_signInDone!.isCompleted) {
        _signInDone!.completeError(AccountError('acc_failed'));
      }
    } finally {
      await _storage.delete(key: _pendingKey);
      _handlingLink = false;
    }
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
    if (_signingIn || !const {'google', 'github'}.contains(provider)) {
      throw AccountError('acc_failed');
    }
    _signingIn = true;
    final verifier = _verifier();
    final url = Uri.parse('$supabaseUrl/auth/v1/authorize').replace(queryParameters: {
      'provider': provider,
      'redirect_to': authCallbackUrl(android: Platform.isAndroid),
      'code_challenge': challengeOf(verifier),
      'code_challenge_method': 's256',
    });
    try {
      if (Platform.isAndroid) {
        final done = Completer<void>();
        _signInDone = done;
        // Installer l'attente avant d'ouvrir le navigateur ; elle couvre aussi les erreurs.
        final waiting = done.future.timeout(const Duration(minutes: 5));
        try {
          await _storage.write(key: _pendingKey, value: jsonEncode({
            'verifier': verifier, 'started': DateTime.now().millisecondsSinceEpoch,
          }));
          if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
            done.completeError(AccountError('acc_failed'));
          }
        } catch (_) {
          if (!done.isCompleted) done.completeError(AccountError('acc_failed'));
        }
        await waiting;
      } else {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, callbackPort);
        try {
          if (!await launchUrl(url, mode: LaunchMode.externalApplication)) {
            throw AccountError('acc_failed');
          }
          // Ignorer favicon et requêtes sans code : elles ne terminent pas la connexion.
          final request = await server.firstWhere((req) {
            final valid = req.uri.path == '/' &&
                (req.uri.queryParameters.containsKey('code') || req.uri.queryParameters.containsKey('error'));
            if (!valid) {
              req.response.statusCode = 404;
              unawaited(req.response.close());
            }
            return valid;
          }).timeout(const Duration(minutes: 5));
          request.response.headers.contentType = ContentType.html;
          request.response.write('<!doctype html><meta charset="utf-8"><h1>Tontolo</h1>'
              '<p>Retour reçu. Revenez dans Tontolo pour vérifier la connexion.</p>');
          await request.response.close();
          await _exchange(request.uri, verifier);
        } finally {
          await server.close(force: true);
        }
      }
    } on AccountError {
      rethrow;
    } catch (_) {
      throw AccountError('acc_cancelled');
    } finally {
      if (Platform.isAndroid) await _storage.delete(key: _pendingKey);
      _signInDone = null;
      _signingIn = false;
    }
  }

  Future<void> _exchange(Uri back, String verifier) async {
    final params = back.queryParameters;
    if (params['error'] != null) {
      final desc = '${params['error_description']}'.toLowerCase();
      throw AccountError(desc.contains('provider is not enabled') || desc.contains('unsupported provider') ? 'acc_provider_off' : 'acc_failed');
    }
    final code = params['code'];
    if (code == null || code.isEmpty) throw AccountError('acc_failed');
    final r = await _http.post(Uri.parse('$supabaseUrl/auth/v1/token?grant_type=pkce'),
        headers: {'apikey': supabaseKey, 'Content-Type': 'application/json'},
        body: jsonEncode({'auth_code': code, 'code_verifier': verifier}))
        .timeout(const Duration(seconds: 20));
    if (r.statusCode != 200) throw AccountError('acc_failed');
    final data = jsonDecode(utf8.decode(r.bodyBytes)) as Map<String, dynamic>;
    if (data['access_token'] is! String || data['refresh_token'] is! String || data['user'] is! Map) {
      throw AccountError('acc_failed');
    }
    await _save(Session.fromToken(data));
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
