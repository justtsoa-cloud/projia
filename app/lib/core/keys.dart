// Clés API personnelles (BYOK) : Android Keystore / libsecret sous Linux.
// Elles ne quittent l'appareil que vers le fournisseur concerné, et sont
// transmises au cœur en mémoire uniquement (persist=false).

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'backend.dart';

class Keys {
  static const _storage = FlutterSecureStorage();
  static const _prefix = 'key:';

  static Future<Map<String, String>> all() async {
    final raw = await _storage.readAll();
    return {
      for (final e in raw.entries)
        if (e.key.startsWith(_prefix)) e.key.substring(_prefix.length): e.value,
    };
  }

  /// Valide la clé auprès du fournisseur (via le cœur) puis l'enregistre.
  static Future<(bool, String)> save(Backend backend, String provider, String key) async {
    final res = await backend.sendJson('PUT', '/tontolo/keys/$provider',
        {'key': key, 'persist': false, 'validate_key': true}) as Map<String, dynamic>;
    final ok = res['valid'] == true;
    if (ok) await _storage.write(key: '$_prefix$provider', value: key);
    return (ok, '${res['detail']}');
  }

  /// Clé reçue d'un autre appareil du même compte (déjà validée là-bas).
  static Future<void> store(Backend backend, String provider, String key) async {
    await _storage.write(key: '$_prefix$provider', value: key);
    if (backend.isRemote) return;
    try {
      await backend.sendJson('PUT', '/tontolo/keys/$provider', {'key': key, 'persist': false, 'validate_key': false});
    } catch (_) {}
  }

  static Future<void> remove(Backend backend, String provider) async {
    await _storage.delete(key: '$_prefix$provider');
    await backend.sendJson('DELETE', '/tontolo/keys/$provider');
  }

  /// Au démarrage : recharge les clés dans le cœur (mode local uniquement).
  static Future<void> pushAll(Backend backend) async {
    if (backend.isRemote) return; // le serveur distant gère ses propres clés
    for (final e in (await all()).entries) {
      try {
        await backend.sendJson('PUT', '/tontolo/keys/${e.key}',
            {'key': e.value, 'persist': false, 'validate_key': false});
      } catch (_) {}
    }
  }

  static Future<String?> remoteToken() => _storage.read(key: 'remote_token');
  static Future<void> setRemoteToken(String v) => _storage.write(key: 'remote_token', value: v);
}
