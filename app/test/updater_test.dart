// Saut de mises à jour : de n'importe quelle version (0.2.0…) à la dernière.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/core/updater.dart';
import 'package:tontolo/core/whats_new.dart';

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
    expect(names, containsAll(['tontolo-9.9.9-arm64-v8a.apk', 'SHA256SUMS', 'Tontolo-9.9.9-x86_64.AppImage']));
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
}
