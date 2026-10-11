// Mises à jour automatiques depuis les releases GitHub.
//
// - Vérification au démarrage puis toutes les 24 h (désactivable).
// - Téléchargement en arrière-plan du fichier adapté (APK de l'ABI, ou AppImage
//   de l'architecture) et vérification SHA-256 contre `SHA256SUMS`.
// - Linux (AppImage) : remplacement atomique du fichier puis redémarrage.
// - Android : ouverture de l'installeur système (un appui : Android interdit
//   l'installation silencieuse aux applications ordinaires).

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import '../l10n/strings.dart';
import 'prefs.dart';

const appVersion = '0.4.1';
const repo = 'raantss18/tontolo';

enum UpdateStatus { idle, checking, downloading, ready, failed, upToDate }

class Updater extends ChangeNotifier {
  Updater(this.prefs);

  final Prefs prefs;
  UpdateStatus status = UpdateStatus.idle;
  String? latest;
  String? releaseUrl;
  String? message;
  String notesRaw = '';
  File? file;

  /// Notes de la release groupées par rubrique (Ajouté, Corrigé, Sécurité…).
  List<(String, List<String>)> get notes => parseNotes(notesRaw);

  static List<(String, List<String>)> parseNotes(String body) {
    final out = <(String, List<String>)>[];
    String? head;
    var items = <String>[];
    void flush() {
      final h = head;
      if (h != null && items.isNotEmpty) out.add((h, items));
      items = [];
    }

    for (final raw in const LineSplitter().convert(body)) {
      final line = raw.trimRight();
      if (line.startsWith('### ')) {
        flush();
        final title = line.substring(4).trim();
        if (title.toLowerCase().startsWith('taille')) break; // tableau des tailles : inutile ici
        head = title;
      } else if (line.startsWith('- ') && head != null) {
        items.add(_clean(line.substring(2)));
      } else if (line.startsWith('  ') && items.isNotEmpty && line.trim().isNotEmpty) {
        items[items.length - 1] = '${items.last} ${_clean(line.trim())}'; // ligne de suite
      }
    }
    flush();
    return out;
  }

  static String _clean(String s) => s.replaceAll('`', '').replaceAll('**', '').trim();
  double progress = 0;
  Timer? _timer;

  void startAuto() {
    if (!prefs.autoUpdate) return;
    unawaited(run());
    _timer ??= Timer.periodic(const Duration(hours: 24), (_) {
      if (prefs.autoUpdate) unawaited(run());
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  static (String, String)? target() {
    final v = Platform.version; // … on "android_arm64"
    final m = RegExp(r'on "(\w+)_(\w+)"').firstMatch(v);
    if (m == null) return null;
    final os = m.group(1)!, arch = m.group(2)!;
    if (os == 'android') {
      return ('android', const {'arm64': 'arm64-v8a', 'arm': 'armeabi-v7a', 'x64': 'x86_64'}[arch] ?? 'arm64-v8a');
    }
    if (os == 'linux') return ('linux', arch == 'arm64' ? 'aarch64' : 'x86_64');
    return null;
  }

  static bool isNewer(String a, String b) {
    List<int> p(String s) => RegExp(r'\d+').allMatches(s.split('-').first).map((m) => int.parse(m[0]!)).toList();
    final x = p(a), y = p(b);
    for (var i = 0; i < 3; i++) {
      final xi = i < x.length ? x[i] : 0, yi = i < y.length ? y[i] : 0;
      if (xi != yi) return xi > yi;
    }
    return false;
  }

  Future<void> run({bool manual = false}) async {
    if (status == UpdateStatus.downloading || status == UpdateStatus.checking) return;
    final t = target();
    if (t == null) return;
    _set(UpdateStatus.checking);
    try {
      final rel = await _latestRelease();
      prefs.lastUpdateCheck = DateTime.now().millisecondsSinceEpoch;
      if (rel == null) throw _UpdateError('upd_unreachable');
      latest = '${rel['tag_name']}'.replaceFirst('v', '');
      releaseUrl = rel['html_url'] as String?;
      if (!isNewer(latest!, appVersion)) return _set(UpdateStatus.upToDate);
      // Notes cumulées de toutes les versions sautées (CHANGELOG), sinon celles de la release.
      notesRaw = await _notesSince(latest!) ?? '${rel['body'] ?? ''}';
      if (t.$1 == 'linux' && Platform.environment['APPIMAGE'] == null) {
        // Installation hors AppImage (paquet, sources) : on signale seulement.
        message = tr(prefs.locale, 'upd_available', {'v': latest!});
        return _set(UpdateStatus.ready);
      }
      final assets = (rel['assets'] as List).cast<Map<String, dynamic>>();
      final asset = _pick(assets, t.$1, t.$2);
      final sums = assets.where((a) => a['name'] == 'SHA256SUMS').firstOrNull;
      if (asset == null || sums == null) throw _UpdateError('upd_missing');
      for (final a in [asset, sums]) {
        final host = Uri.parse('${a['browser_download_url']}').host;
        if (host != 'github.com' && !host.endsWith('.githubusercontent.com')) {
          throw _UpdateError('upd_origin');
        }
      }
      final sumsResp = await http.get(Uri.parse(sums['browser_download_url'])).timeout(const Duration(seconds: 30));
      if (sumsResp.statusCode != 200) throw _UpdateError('upd_missing');
      final sumsText = sumsResp.body;
      final expected = _parseSums(sumsText)[asset['name']];
      if (expected == null) throw _UpdateError('upd_no_hash');
      file = await _download(asset, expected);
      message = tr(prefs.locale, 'upd_ready_install', {'v': latest!});
      _set(UpdateStatus.ready); // l'installation est proposée par l'interface, jamais lancée d'office
    } on _UpdateError catch (e) {
      message = tr(prefs.locale, e.key);
      _set(UpdateStatus.failed);
    } catch (e) {
      message = tr(prefs.locale, 'upd_unreachable');
      _set(UpdateStatus.failed);
    }
  }

  /// Dernière release publiée. L'API GitHub est limitée à 60 requêtes/heure par adresse IP
  /// (souvent partagée sur les réseaux mobiles) : en cas de refus, repli sur la redirection
  /// de la page `releases/latest`, sans limite, et sur les noms de fichiers stables.
  static Future<Map<String, dynamic>?> _latestRelease() async {
    try {
      final r = await http.get(Uri.parse('https://api.github.com/repos/$repo/releases/latest'),
          headers: {'Accept': 'application/vnd.github+json'}).timeout(const Duration(seconds: 15));
      if (r.statusCode == 200) return jsonDecode(r.body) as Map<String, dynamic>;
    } catch (_) {}
    final client = http.Client();
    try {
      final req = http.Request('GET', Uri.parse('https://github.com/$repo/releases/latest'))
        ..followRedirects = false;
      final resp = await client.send(req).timeout(const Duration(seconds: 15));
      final m = RegExp(r'/releases/tag/v?([0-9][\w.\-]*)$').firstMatch(resp.headers['location'] ?? '');
      if (m == null) return null;
      return fallbackRelease(m.group(1)!);
    } catch (_) {
      return null;
    } finally {
      client.close();
    }
  }

  /// Description minimale d'une release à partir de son numéro (noms de fichiers stables,
  /// voir docs/RELEASING.md : ils ne doivent jamais changer).
  static Map<String, dynamic> fallbackRelease(String v) {
    String dl(String n) => 'https://github.com/$repo/releases/download/v$v/$n';
    final names = [
      for (final abi in ['arm64-v8a', 'armeabi-v7a', 'x86_64']) 'tontolo-$v-$abi.apk',
      'Tontolo-$v-x86_64.AppImage', 'Tontolo-$v-aarch64.AppImage', 'SHA256SUMS',
    ];
    return {
      'tag_name': 'v$v',
      'html_url': 'https://github.com/$repo/releases/tag/v$v',
      'body': '',
      'assets': [for (final n in names) {'name': n, 'browser_download_url': dl(n)}],
    };
  }

  /// Sections du CHANGELOG plus récentes que la version installée (jusqu'à `latest`).
  static Future<String?> _notesSince(String latest) async {
    try {
      final r = await http
          .get(Uri.parse('https://raw.githubusercontent.com/$repo/v$latest/CHANGELOG.md'))
          .timeout(const Duration(seconds: 15));
      if (r.statusCode != 200) return null;
      final out = changelogSince(r.body, appVersion);
      return out.trim().isEmpty ? null : out;
    } catch (_) {
      return null;
    }
  }

  /// Extrait du CHANGELOG les rubriques des versions > `installed`, préfixées par la version.
  static String changelogSince(String changelog, String installed) {
    final buf = StringBuffer();
    String? version;
    for (final line in const LineSplitter().convert(changelog)) {
      final h = RegExp(r'^## \[(\d+\.\d+\.\d+)\]').firstMatch(line);
      if (h != null) {
        version = h.group(1);
        if (!isNewer(version!, installed)) break; // le CHANGELOG va du plus récent au plus ancien
        continue;
      }
      if (line.startsWith('## ')) {
        version = null; // « Non publié » ou autre
        continue;
      }
      if (version == null) continue;
      if (line.startsWith('### ')) {
        buf.writeln('### $version · ${line.substring(4).trim()}');
      } else {
        buf.writeln(line);
      }
    }
    return buf.toString();
  }

  Map<String, dynamic>? _pick(List<Map<String, dynamic>> assets, String os, String arch) {
    bool ok(Map<String, dynamic> a) {
      final n = a['name'] as String;
      return os == 'android' ? n.endsWith('.apk') && n.contains(arch) : n.endsWith('.AppImage') && n.contains(arch);
    }

    return assets.where(ok).firstOrNull;
  }

  static Map<String, String> _parseSums(String text) {
    final out = <String, String>{};
    for (final line in const LineSplitter().convert(text)) {
      final m = RegExp(r'^([0-9a-fA-F]{64})\s+\*?(.+)$').firstMatch(line.trim());
      if (m != null) out[m.group(2)!.trim()] = m.group(1)!.toLowerCase();
    }
    return out;
  }

  Future<File> _download(Map<String, dynamic> asset, String expected) async {
    final dir = Directory('${(await getApplicationSupportDirectory()).path}/updates');
    await dir.create(recursive: true);
    final dest = File('${dir.path}/${asset['name']}');
    if (await dest.exists() && (await sha256.bind(dest.openRead()).first).toString() == expected) {
      return dest;
    }
    _set(UpdateStatus.downloading);
    final part = File('${dest.path}.part');
    final client = http.Client();
    try {
      final resp = await client.send(http.Request('GET', Uri.parse(asset['browser_download_url'])));
      if (resp.statusCode != 200) throw _UpdateError('upd_missing');
      final total = resp.contentLength ?? (asset['size'] as int? ?? 0);
      final sink = part.openWrite();
      final hashOut = AccumulatorSink<Digest>();
      final hasher = sha256.startChunkedConversion(hashOut);
      var received = 0;
      await for (final chunk in resp.stream) {
        sink.add(chunk);
        hasher.add(chunk);
        received += chunk.length;
        if (total > 0) {
          progress = received / total;
          notifyListeners();
        }
      }
      await sink.close();
      hasher.close();
      if (hashOut.events.single.toString() != expected) {
        await part.delete();
        throw _UpdateError('upd_bad_hash');
      }
      return await part.rename(dest.path);
    } finally {
      client.close();
    }
  }

  Future<void> installAndroid() async {
    if (file != null) await OpenFilex.open(file!.path, type: 'application/vnd.android.package-archive');
  }

  /// Linux : remplace l'AppImage en cours d'utilisation puis relance.
  Future<void> installLinuxAndRestart() async {
    final appImage = Platform.environment['APPIMAGE'];
    if (appImage == null || file == null) return;
    final tmp = File('$appImage.new');
    await file!.copy(tmp.path);
    await Process.run('chmod', ['+x', tmp.path]);
    await tmp.rename(appImage);
    await Process.start(appImage, [], mode: ProcessStartMode.detached);
    exit(0);
  }

  void _set(UpdateStatus s) {
    status = s;
    notifyListeners();
  }
}

/// Échec de mise à jour, traduit dans la langue de l'interface.
class _UpdateError implements Exception {
  const _UpdateError(this.key);
  final String key;
}

class AccumulatorSink<T> implements Sink<T> {
  final events = <T>[];
  @override
  void add(T event) => events.add(event);
  @override
  void close() {}
}
