// Démarrage et connexion au cœur Tontolo.
//
// Mode local : le cœur Python est embarqué (serious_python) et écoute sur
// 127.0.0.1 avec un port libre et un jeton aléatoire, pour qu'aucune autre
// application de l'appareil ne puisse l'utiliser.
// Mode distant : l'application parle à un serveur Tontolo sur Linux (URL + jeton).
// Le reste de l'application utilise le même code dans les deux cas.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:serious_python/serious_python.dart';

import 'keys.dart';
import 'prefs.dart';

enum BackendState { starting, ready, failed }

class Backend extends ChangeNotifier {
  Backend(this.prefs);

  final Prefs prefs;
  BackendState state = BackendState.starting;
  String baseUrl = '';
  String token = '';
  String? error;
  Duration? startupTime;
  bool _pythonStarted = false;

  bool get isRemote => prefs.remoteUrl.isNotEmpty;

  Map<String, String> get headers => {
        if (token.isNotEmpty) 'Authorization': 'Bearer $token',
      };

  Future<void> start() async {
    final watch = Stopwatch()..start();
    state = BackendState.starting;
    error = null;
    notifyListeners();
    try {
      if (isRemote) {
        baseUrl = prefs.remoteUrl.replaceAll(RegExp(r'/+$'), '');
        token = await Keys.remoteToken() ?? '';
      } else {
        await _startEmbedded();
      }
      await _waitHealthy(timeout: isRemote ? const Duration(seconds: 10) : const Duration(seconds: 90));
      await Keys.pushAll(this);
      startupTime = watch.elapsed;
      state = BackendState.ready;
    } catch (e) {
      error = e.toString();
      state = BackendState.failed;
    }
    notifyListeners();
  }

  Future<void> _startEmbedded() async {
    if (_pythonStarted) return;
    final support = await getApplicationSupportDirectory();
    final home = Directory('${support.path}/tontolo');
    await home.create(recursive: true);
    // Quitter l'application (bouton Retour) ne tue pas le processus Android : le moteur Python
    // y reste en vie, mais l'interface est recréée. On le retrouve (port + jeton mémorisés)
    // au lieu d'en démarrer un second, ce qui est impossible dans un même processus.
    final info = File('${home.path}/core.json');
    if (await _reuseRunningCore(info)) {
      _pythonStarted = true;
      return;
    }
    final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = socket.port;
    await socket.close();
    final rnd = Random.secure();
    token = List.generate(32, (_) => rnd.nextInt(256).toRadixString(16).padLeft(2, '0')).join();
    baseUrl = 'http://127.0.0.1:$port';
    await info.writeAsString(jsonEncode({'port': port, 'token': token}), flush: true);
    _pythonStarted = true;
    // Le cœur tourne dans un fil d'exécution d'arrière-plan : l'interface reste fluide.
    unawaited(SeriousPython.run(
      environmentVariables: {
        'TONTOLO_PORT': '$port',
        'TONTOLO_TOKEN': token,
        'TONTOLO_HOME': home.path,
        'TONTOLO_PLATFORM': Platform.isAndroid ? 'android' : 'linux',
      },
    ));
  }

  /// Vrai si un moteur déjà démarré (même processus) répond avec le jeton mémorisé.
  Future<bool> _reuseRunningCore(File info) async {
    try {
      if (!await info.exists()) return false;
      final j = jsonDecode(await info.readAsString()) as Map<String, dynamic>;
      final url = 'http://127.0.0.1:${j['port']}';
      final t = '${j['token']}';
      final r = await http
          .get(Uri.parse('$url/tontolo/status'), headers: {'Authorization': 'Bearer $t'})
          .timeout(const Duration(seconds: 2));
      if (r.statusCode != 200) return false;
      baseUrl = url;
      token = t;
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _waitHealthy({required Duration timeout}) async {
    final deadline = DateTime.now().add(timeout);
    var delay = 100;
    while (DateTime.now().isBefore(deadline)) {
      try {
        final r = await http
            .get(Uri.parse('$baseUrl/health'), headers: headers)
            .timeout(const Duration(seconds: 3));
        if (r.statusCode == 200) return;
      } catch (_) {}
      await Future.delayed(Duration(milliseconds: delay));
      delay = min(delay * 2, 800);
    }
    throw Exception('Le cœur Tontolo ne répond pas ($baseUrl)');
  }

  Uri uri(String path, [Map<String, dynamic>? query]) => Uri.parse('$baseUrl$path').replace(
      queryParameters: query?.map((k, v) => MapEntry(k, '$v')));

  Future<dynamic> getJson(String path, [Map<String, dynamic>? query]) async {
    final r = await http.get(uri(path, query), headers: headers);
    _check(r);
    return jsonDecode(utf8.decode(r.bodyBytes));
  }

  Future<dynamic> sendJson(String method, String path, [Object? body]) async {
    final req = http.Request(method, uri(path))
      ..headers.addAll({...headers, 'Content-Type': 'application/json'})
      ..body = jsonEncode(body ?? {});
    final r = await http.Response.fromStream(await req.send());
    _check(r);
    return r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
  }

  void _check(http.Response r) {
    if (r.statusCode >= 400) {
      throw HttpException('HTTP ${r.statusCode} : ${utf8.decode(r.bodyBytes)}');
    }
  }

  /// Flux d'événements SSE (`data: {...}`). La génération tourne côté cœur : fermer ce flux
  /// (quitter la discussion) ne l'interrompt pas ; on peut s'y rattacher avec `follow`.
  Stream<Map<String, dynamic>> follow(String conversationId) =>
      sse('/tontolo/chat/$conversationId/stream', null, method: 'GET');

  Stream<Map<String, dynamic>> sse(String path, Object? body, {String method = 'POST'}) async* {
    final client = http.Client();
    try {
      final req = http.Request(method, uri(path))
        ..headers.addAll({...headers, 'Content-Type': 'application/json', 'Accept': 'text/event-stream'});
      if (body != null) req.body = jsonEncode(body);
      final resp = await client.send(req);
      if (resp.statusCode >= 400) {
        final text = await resp.stream.bytesToString();
        yield {'type': 'error', 'message': 'HTTP ${resp.statusCode} : $text'};
        return;
      }
      await for (final line in resp.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (!line.startsWith('data:')) continue;
        final data = line.substring(5).trim();
        if (data.isEmpty) continue;
        try {
          yield jsonDecode(data) as Map<String, dynamic>;
        } catch (_) {}
      }
    } finally {
      client.close();
    }
  }
}
