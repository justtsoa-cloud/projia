import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:projia/core/account.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('retour après redémarrage : PKCE échangé une seule fois, session sauvegardée', () async {
    final storage = MemoryStorage();
    storage.values['account_pending_pkce'] = jsonEncode({
      'verifier': 'test-verifier', 'started': DateTime.now().millisecondsSinceEpoch,
    });
    var calls = 0;
    final client = MockClient((request) async {
      calls++;
      expect(request.url.queryParameters['grant_type'], 'pkce');
      expect(jsonDecode(request.body)['code_verifier'], 'test-verifier');
      return http.Response(jsonEncode({
        'access_token': 'test-access', 'refresh_token': 'test-refresh',
        'user': {'id': 'test-user', 'app_metadata': {'provider': 'google'}},
      }), 200);
    });
    final account = Account(client: client, storage: storage);
    final link = Uri.parse('$androidCallbackUrl?code=test-code');
    await Future.wait([account.receiveAuthLink(link), account.receiveAuthLink(link)]);
    expect(calls, 1);
    expect(account.session?.provider, 'google');
    expect(storage.values.containsKey('account_session'), isTrue);
    expect(storage.values.containsKey('account_pending_pkce'), isFalse);
    await account.receiveAuthLink(link);
    expect(calls, 1);
  });

  test('sans demande ou avec demande expirée : aucun échange réseau', () async {
    final storage = MemoryStorage();
    var calls = 0;
    final account = Account(storage: storage, client: MockClient((_) async {
      calls++;
      return http.Response('{}', 400);
    }));
    final link = Uri.parse('$androidCallbackUrl?code=test-code');
    await account.receiveAuthLink(link);
    storage.values['account_pending_pkce'] = jsonEncode({'verifier': 'old', 'started': 0});
    await account.receiveAuthLink(link);
    expect(calls, 0);
    expect(account.signedIn, isFalse);
    expect(storage.values.containsKey('account_pending_pkce'), isFalse);
  });
}

class MemoryStorage extends FlutterSecureStorage {
  final values = <String, String>{};
  @override
  Future<String?> read({required String key, AppleOptions? iOptions, AndroidOptions? aOptions,
    LinuxOptions? lOptions, WebOptions? webOptions, AppleOptions? mOptions, WindowsOptions? wOptions}) async => values[key];
  @override
  Future<void> write({required String key, required String? value, AppleOptions? iOptions,
    AndroidOptions? aOptions, LinuxOptions? lOptions, WebOptions? webOptions,
    AppleOptions? mOptions, WindowsOptions? wOptions}) async {
    if (value != null) values[key] = value;
  }
  @override
  Future<void> delete({required String key, AppleOptions? iOptions, AndroidOptions? aOptions,
    LinuxOptions? lOptions, WebOptions? webOptions, AppleOptions? mOptions, WindowsOptions? wOptions}) async {
    values.remove(key);
  }
}
