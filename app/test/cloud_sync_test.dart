// Synchronisation chiffrée : aller-retour, mauvaise phrase, blob déplacé, plan des mémoires.

import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:projia/core/account.dart';
import 'package:projia/core/cloud_sync.dart';

void main() {
  test('Android revient dans Projia ; Linux conserve le retour local', () {
    expect(authCallbackUrl(android: true), 'io.github.raantss18.projia://login-callback/');
    expect(authCallbackUrl(android: false), 'http://localhost:43823/');
  });

  test('retour OAuth : refuser les autres hôtes, ports, chemins et jetons implicites', () {
    expect(isAndroidAuthCallback(Uri.parse('$androidCallbackUrl?code=sample')), isTrue);
    for (final bad in [
      'https://login-callback/?code=sample',
      'io.github.raantss18.projia://other/?code=sample',
      'io.github.raantss18.projia://login-callback/other?code=sample',
      'io.github.raantss18.projia://login-callback:123/?code=sample',
      'io.github.raantss18.projia://user@login-callback/?code=sample',
      '$androidCallbackUrl#access_token=sample',
    ]) {
      expect(isAndroidAuthCallback(Uri.parse(bad)), isFalse, reason: bad);
    }
  });

  test('chiffrement : aller-retour, mauvaise clé et données associées refusées', () async {
    final salt = SyncCrypto.newSalt();
    final good = SyncCrypto(SecretKey(await SyncCrypto.deriveBytes('ma phrase secrète', salt, iterations: 1000)));
    final bad = SyncCrypto(SecretKey(await SyncCrypto.deriveBytes('autre phrase !!', salt, iterations: 1000)));
    final blob = await good.seal('conv', 'abc', '{"title":"Bonjour"}');
    expect(blob, isNot(contains('Bonjour')));
    expect(await good.open('conv', 'abc', blob), '{"title":"Bonjour"}');
    expect(() => bad.open('conv', 'abc', blob), throwsA(isA<SecretBoxAuthenticationError>()));
    // Blob recopié sous un autre identifiant : refusé (données associées).
    expect(() => good.open('conv', 'xyz', blob), throwsA(isA<SecretBoxAuthenticationError>()));
  });

  test('même phrase et même sel = même clé (appareils différents)', () async {
    final salt = SyncCrypto.newSalt();
    final a = await SyncCrypto.deriveBytes('phrase commune', salt, iterations: 1000);
    final b = await SyncCrypto.deriveBytes('phrase commune', salt, iterations: 1000);
    expect(a, b);
    expect(a.length, 32);
  });

  test('plan des mémoires : ajouts, suppressions locales et distantes', () {
    final plan = MemoryPlan.of(
      local: {'a', 'b', 'new'},
      previous: {'a', 'b', 'gone'},
      remote: {'a', 'b', 'gone', 'other'},
      remoteDeleted: {'b'},
    );
    expect(plan.push, {'new'});
    expect(plan.tombstones, {'gone'});
    expect(plan.addLocal, {'other'});
    expect(plan.deleteLocal, {'b'});
    // Premier appareil : tout est envoyé, rien n'est supprimé.
    final first = MemoryPlan.of(local: {'a'}, previous: {}, remote: {}, remoteDeleted: {});
    expect(first.push, {'a'});
    expect(first.tombstones, isEmpty);
  });

  test('identifiant de mémoire stable, images lourdes retirées avant envoi', () {
    expect(memoryId(' Je suis en terminale '), memoryId('Je suis en terminale'));
    final big = 'data:image/png;base64,${'A' * (maxImageChars + 10)}';
    final body = jsonEncode({'role': 'user', 'content': [
      {'type': 'text', 'text': 'regarde'},
      {'type': 'image_url', 'image_url': {'url': big}},
    ]});
    final slim = slimConversation({'id': 'c', 'messages': [{'uid': 'u', 'body': body}]});
    final out = (slim['messages'] as List).first['body'] as String;
    expect(out.length, lessThan(1000));
    expect(out, contains('image non synchronisée'));
    expect(out, contains('regarde'));
  });

  test('PKCE : défi = SHA-256 base64url sans remplissage', () {
    // Vecteur de la RFC 7636, annexe B.
    expect(Account.challengeOf('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'), 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM');
  });
}
