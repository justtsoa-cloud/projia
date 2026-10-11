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
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

const supabaseUrl = String.fromEnvironment('TONTOLO_STATS_URL');
const supabaseKey = String.fromEnvironment('TONTOLO_STATS_KEY');

/// Retour de connexion : petit serveur local de l'application (Android et bureau), qui ne
/// reçoit qu'une requête puis s'arrête. Le code reçu est inutilisable sans le vérificateur
/// PKCE gardé en mémoire.
const callbackPort = 43823;
const callbackUrl = 'http://localhost:$callbackPort/';

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
    final url = Uri.parse('$supabaseUrl/auth/v1/authorize').replace(queryParameters: {
      'provider': provider,
      'redirect_to': callbackUrl,
      'code_challenge': challengeOf(verifier),
      'code_challenge_method': 's256',
    });
    final Uri back;
    HttpServer? server;
    try {
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, callbackPort);
      if (!await launchUrl(url, mode: LaunchMode.externalApplication)) throw AccountError('acc_failed');
      final req = await server.first.timeout(const Duration(minutes: 5));
      back = req.uri;
      // Page de retour : propose de revenir dans l'application (Android : lien intent://).
      req.response
        ..statusCode = 200
        ..headers.contentType = ContentType.html
        ..write(_donePage(Platform.isAndroid));
      await req.response.close();
    } on AccountError {
      rethrow;
    } catch (e) {
      throw AccountError('acc_cancelled');
    } finally {
      await server?.close(force: true);
    }
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

  static String _donePage(bool android) => '<!doctype html><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1">'
      '<body style="font-family:sans-serif;text-align:center;padding:40px">'
      '<h2>Tontolo</h2><p>Connexion terminée. Vous pouvez revenir dans l\'application.</p>'
      '${android ? '<p><a href="intent://#Intent;package=io.github.raantss18.tontolo;end" '
          'style="font-size:20px">Revenir à Tontolo</a></p>'
          '<script>location.href="intent://#Intent;package=io.github.raantss18.tontolo;end"</script>' : ''}'
      '</body>';

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
