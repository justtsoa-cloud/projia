// Saut de mises à jour : de n'importe quelle version (0.2.0…) à la dernière.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:projia/core/prefs.dart';
import 'package:projia/core/update_key.dart';
import 'package:projia/core/updater.dart';
import 'package:projia/core/whats_new.dart';

void main() {
  test('le CHANGELOG cumule toutes les versions sautées', () {
    final changelog = File('../CHANGELOG.md').readAsStringSync();
    final notes = Updater.changelogSince(changelog, '0.2.0');
    for (final v in ['0.2.1', '0.2.2', '0.2.3', '0.2.4', '0.2.5', appVersion]) {
      expect(notes.contains('### $v ·'), isTrue, reason: 'notes de $v manquantes');
    }
    expect(notes.contains('### 0.2.0 ·'), isFalse);
    final parsed = Updater.parseNotes(notes);
    expect(parsed.first.$1.startsWith(appVersion), isTrue);
    expect(parsed.every((s) => s.$2.isNotEmpty), isTrue);
  });

  test('rien de plus récent : notes vides', () {
    final changelog = File('../CHANGELOG.md').readAsStringSync();
    expect(Updater.changelogSince(changelog, appVersion).trim(), isEmpty);
  });

  test('repli sans API : noms de fichiers stables', () {
    final rel = Updater.fallbackRelease('9.9.9');
    final names = [for (final a in rel['assets'] as List) (a as Map)['name']];
    expect(names, containsAll(['projia-9.9.9-arm64-v8a.apk', 'SHA256SUMS', 'Projia-9.9.9-x86_64.AppImage']));
    for (final a in rel['assets'] as List) {
      expect(Uri.parse('${(a as Map)['browser_download_url']}').host, 'github.com');
    }
  });

  test('nouveautés de toutes les versions intermédiaires, la plus récente en premier', () {
    final groups = newsBetween('0.2.3', appVersion);
    final versions = [for (final g in groups) g.$1];
    expect(versions.first, appVersion);
    expect(versions, isNot(contains('0.2.3')));
    expect(versions, containsAll(['0.2.4', '0.2.5']));
    expect(newsBetween(appVersion, appVersion), isEmpty);
  });

  test('chaque version de l\'application a ses nouveautés et son CHANGELOG', () {
    expect(newsFor(appVersion), isNotEmpty);
    expect(File('../CHANGELOG.md').readAsStringSync().contains('## [$appVersion]'), isTrue);
  });

  test('empreintes signées : signature openssl (comme la CI) acceptée, toute altération refusée', () async {
    // Vecteur produit par `openssl pkeyutl -sign -rawin` avec une clé jetable (comme la CI).
    const pub = 'O6l5dFQk2gG7WSLOhlZaXWiLlsnwYcR0qqGZjvoJUkU=';
    final sig = base64Decode('APW7Dt353xmHGJxKAhL9XiGau+oAkay56kjNNiMW04jbRr+R2HMBw7rKAteASlgh+b6azvoGbPQcW8hyAHXvCA==');
    final sums = utf8.encode('abc123  Projia-9.9.9-x86_64.AppImage\n');
    expect(await Updater.verifySums(sums, sig, publicKey: pub), isTrue);
    final forged = utf8.encode('abc124  Projia-9.9.9-x86_64.AppImage\n');
    expect(await Updater.verifySums(forged, sig, publicKey: pub), isFalse);
    expect(await Updater.verifySums(sums, sig), isFalse); // autre clé (celle de Projia)
    expect(await Updater.verifySums(sums, sig.sublist(1)), isFalse);
    // La clé embarquée est celle de .github/update-signing.pub.
    expect(File('../.github/update-signing.pub').readAsStringSync(), contains('MCowBQYDK2VwAyEA'));
    expect(base64Decode(updateSigningKey), hasLength(32));
    expect(Updater.fallbackRelease('9.9.9')['assets'].map((a) => a['name']), contains('SHA256SUMS.sig'));
  });
  test('asset absent, mauvaise architecture ou version détournée refusés', () {
    final assets = (Updater.fallbackRelease('9.9.9')['assets'] as List).cast<Map<String, dynamic>>();
    expect(Updater.pickAsset(assets, 'linux', 'x86_64', '9.9.9'), isNotNull);
    expect(Updater.pickAsset([], 'linux', 'x86_64', '9.9.9'), isNull);
    expect(Updater.pickAsset(assets, 'linux', 'x86_64', '9.9.8'), isNull);
    expect(Updater.pickAsset(assets, 'linux', 'unknown', '9.9.9'), isNull);
    expect(Updater.isNewer('0.1.0', appVersion), isFalse);
  });

  test('installation refusée sans preuve de vérification, dans les trois langues', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    for (final lang in ['fr', 'en', 'mg']) {
      prefs.locale = lang;
      final updater = Updater(prefs)..latest = '0.1.0'..file = File('/tmp/unverified.apk');
      await updater.installAndroid(); // aucun appel à l’installeur natif
      expect(updater.status, UpdateStatus.failed);
      expect(updater.message, isNotEmpty);
      expect(updater.message, isNot('upd_downgrade'));
      updater.dispose();
    }
  });
}
