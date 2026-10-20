// Synchronisation optionnelle de l'historique entre l'appareil (cœur local) et
// un serveur Projia : envoi des changements locaux, réception des changements
// distants (le plus récent l'emporte). La même conversation devient visible
// sur les deux appareils.

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'backend.dart';
import 'keys.dart';

class HistorySync {
  static Future<int> run(Backend local) async {
    final prefs = local.prefs;
    if (!prefs.syncEnabled || prefs.syncUrl.isEmpty || local.isRemote) return 0;
    final base = prefs.syncUrl.replaceAll(RegExp(r'/+$'), '');
    final token = await Keys.remoteToken() ?? '';
    final headers = {'Content-Type': 'application/json', if (token.isNotEmpty) 'Authorization': 'Bearer $token'};
    final since = prefs.lastSync;
    // 1. Local → serveur
    final mine = await local.getJson('/projia/sync', {'since': since}) as Map<String, dynamic>;
    final up = await http.post(Uri.parse('$base/projia/sync'), headers: headers, body: jsonEncode(mine));
    if (up.statusCode != 200) throw Exception('Synchronisation refusée (${up.statusCode})');
    // 2. Serveur → local
    final down = await http.get(Uri.parse('$base/projia/sync?since=$since'), headers: headers);
    if (down.statusCode != 200) throw Exception('Synchronisation refusée (${down.statusCode})');
    final theirs = jsonDecode(utf8.decode(down.bodyBytes)) as Map<String, dynamic>;
    final res = await local.sendJson('POST', '/projia/sync', theirs) as Map<String, dynamic>;
    prefs.lastSync = [(mine['until'] as num).toDouble(), (theirs['until'] as num).toDouble()]
        .reduce((a, b) => a < b ? a : b);
    return (res['applied'] as num).toInt() + ((jsonDecode(up.body) as Map)['applied'] as num).toInt();
  }
}
