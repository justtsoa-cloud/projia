// Synchronisation chiffrée de bout en bout entre les appareils d'un même compte
// (protocole : docs/ACCOUNTS.md). La base ne reçoit que des blobs AES-256-GCM ; la clé est
// dérivée de la phrase secrète de l'utilisateur (PBKDF2-HMAC-SHA256) et ne quitte jamais
// l'appareil. Éléments : une conversation entière (`conv`), une mémoire (`memory`), les clés
// d'API (`keys`) et le bloc de vérification de la phrase (`meta/check`).

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:math';

import 'package:crypto/crypto.dart' as hash;
import 'package:cryptography/cryptography.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

import 'account.dart';
import 'backend.dart';
import 'keys.dart';

const kdfIterations = 310000;
const _checkPlain = 'tontolo-sync-check-v1';
const maxImageChars = 500 * 1024; // images plus lourdes : non synchronisées
const livePeriod = Duration(seconds: 20); // synchro tant que l'application est ouverte
const liveExpiry = 120; // s : une tâche distante sans nouvelles depuis plus longtemps est oubliée

// Éléments ajoutés en 0.5.1, rangés dans `conv` avec un préfixe (aucune modification de la
// table ; les versions précédentes les ignorent car l'identifiant ne correspond pas) :
// « m-<id> » = une création (≤ 1 Mo), « s-<appareil> » = les tâches en cours d'un appareil.
const creationPrefix = 'm-';
const statusPrefix = 's-';

/// Tâche en cours sur un autre appareil.
class RemoteTask {
  RemoteTask(this.device, this.data, this.at);
  final String device;
  final Map<String, dynamic> data;
  final double at;
  String get conversationId => '${data['conversation_id']}';
  String get title => '${data['title'] ?? ''}';
  String get partial => '${data['partial'] ?? ''}';
  String get step => '${data['step'] ?? ''}';
}

class SyncError implements Exception {
  SyncError(this.code);
  final String code; // sync_bad_phrase | sync_signed_out | sync_server | sync_not_setup
  @override
  String toString() => code;
}

/// Chiffrement des éléments (exposé pour les tests).
class SyncCrypto {
  SyncCrypto(this.key);
  final SecretKey key;
  static final _aes = AesGcm.with256bits();

  /// Clé dérivée hors du fil de l'interface (PBKDF2 : quelques secondes sur téléphone).
  static Future<List<int>> deriveBytes(String phrase, List<int> salt, {int iterations = kdfIterations}) =>
      Isolate.run(() async {
        final kdf = Pbkdf2(macAlgorithm: Hmac.sha256(), iterations: iterations, bits: 256);
        final k = await kdf.deriveKeyFromPassword(password: phrase, nonce: salt);
        return k.extractBytes();
      });

  static List<int> newSalt() => List.generate(16, (_) => Random.secure().nextInt(256));

  Future<String> seal(String kind, String id, String plain) async {
    final box = await _aes.encrypt(utf8.encode(plain), secretKey: key, aad: utf8.encode('$kind|$id'));
    return base64.encode(box.concatenation());
  }

  Future<String> open(String kind, String id, String blob) async {
    final box = SecretBox.fromConcatenation(base64.decode(blob), nonceLength: 12, macLength: 16);
    return utf8.decode(await _aes.decrypt(box, secretKey: key, aad: utf8.encode('$kind|$id')));
  }
}

/// Plan de synchronisation des mémoires (ensembles d'identifiants = sha256 du texte).
/// L : local actuel ; P : synchronisé la dernière fois ; R : distant vivant ; T : tombes distantes.
class MemoryPlan {
  MemoryPlan({required this.push, required this.tombstones, required this.addLocal, required this.deleteLocal});
  final Set<String> push; // à envoyer (ajoutées localement)
  final Set<String> tombstones; // supprimées localement → tombe distante
  final Set<String> addLocal; // nouvelles venues d'ailleurs
  final Set<String> deleteLocal; // supprimées ailleurs

  static MemoryPlan of({required Set<String> local, required Set<String> previous, required Set<String> remote, required Set<String> remoteDeleted}) {
    final deletedHere = previous.difference(local);
    return MemoryPlan(
      push: local.difference(previous).difference(remote),
      tombstones: deletedHere.intersection(remote),
      addLocal: remote.difference(local).difference(deletedHere),
      deleteLocal: remoteDeleted.intersection(local).intersection(previous),
    );
  }
}

String memoryId(String text) => hash.sha256.convert(utf8.encode(text.trim())).toString().substring(0, 32);

/// Allège une conversation avant envoi : images volumineuses remplacées par un texte.
Map<String, dynamic> slimConversation(Map<String, dynamic> conv) {
  final msgs = <Map<String, dynamic>>[];
  for (final m in (conv['messages'] as List? ?? const []).cast<Map<String, dynamic>>()) {
    var body = '${m['body']}';
    if (body.length > maxImageChars && body.contains('image_url')) {
      try {
        final msg = jsonDecode(body) as Map<String, dynamic>;
        final content = msg['content'];
        if (content is List) {
          msg['content'] = [
            for (final p in content.cast<Map<String, dynamic>>())
              if (p['type'] == 'image_url' && '${(p['image_url'] as Map?)?['url']}'.length > maxImageChars)
                {'type': 'text', 'text': '[image non synchronisée]'}
              else
                p,
          ];
          body = jsonEncode(msg);
        }
      } catch (_) {}
    }
    msgs.add({...m, 'body': body});
  }
  return {...conv, 'messages': msgs};
}

class CloudSync extends ChangeNotifier {
  CloudSync(this.backend, this.account, {http.Client? client, FlutterSecureStorage? storage})
      : _http = client ?? http.Client(),
        _storage = storage ?? const FlutterSecureStorage();

  final Backend backend;
  final Account account;
  final http.Client _http;
  final FlutterSecureStorage _storage;
  static const _keyName = 'sync_key';

  SyncCrypto? _crypto;
  bool running = false;
  Timer? _live;
  bool _statusSent = false; // l'état « rien en cours » n'est envoyé qu'une fois
  /// Tâches en cours sur les autres appareils, par appareil.
  final Map<String, RemoteTask> remoteTasks = {};
  /// Conversations reçues au dernier cycle (pour rafraîchir celle qui est affichée).
  Set<String> lastImported = {};

  List<RemoteTask> get liveTasks {
    final now = _now();
    return [for (final t in remoteTasks.values) if (now - t.at < liveExpiry) t];
  }

  /// Synchro périodique tant que l'application est au premier plan.
  void startLive(bool Function() enabled) {
    _live?.cancel();
    _live = Timer.periodic(livePeriod, (_) {
      if (enabled() && ready && !running) run().catchError((_) => 0);
    });
  }

  void stopLive() {
    _live?.cancel();
    _live = null;
  }

  static String get deviceName {
    final os = Platform.isAndroid ? 'Android' : Platform.isLinux ? 'Linux' : Platform.operatingSystem;
    try {
      return '$os · ${Platform.localHostname}';
    } catch (_) {
      return os;
    }
  }
  String? lastError;
  DateTime? lastRun;

  bool get ready => _crypto != null;

  Future<void> load() async {
    final raw = await _storage.read(key: _keyName);
    if (raw != null) _crypto = SyncCrypto(SecretKey(base64.decode(raw)));
    notifyListeners();
  }

  Future<Map<String, String>> _headers() async {
    final t = await account.token();
    if (t == null) throw SyncError('sync_signed_out');
    return {'apikey': supabaseKey, 'Authorization': 'Bearer $t', 'Content-Type': 'application/json'};
  }

  Uri _table([Map<String, String>? q]) => Uri.parse('$supabaseUrl/rest/v1/sync_items').replace(queryParameters: q);

  Future<List<Map<String, dynamic>>> _select(Map<String, String> q) async {
    final r = await _http.get(_table(q), headers: await _headers());
    if (r.statusCode != 200) throw SyncError('sync_server');
    return (jsonDecode(utf8.decode(r.bodyBytes)) as List).cast<Map<String, dynamic>>();
  }

  Future<void> _upsert(List<Map<String, dynamic>> rows) async {
    final uid = account.session!.userId;
    for (var i = 0; i < rows.length; i += 50) {
      final batch = [for (final r in rows.skip(i).take(50)) {...r, 'user_id': uid}];
      final r = await _http.post(_table({'on_conflict': 'user_id,kind,item_id'}),
          headers: {...await _headers(), 'Prefer': 'resolution=merge-duplicates,return=minimal'}, body: jsonEncode(batch));
      if (r.statusCode >= 300) throw SyncError('sync_server');
    }
  }

  /// Première configuration sur cet appareil : crée le bloc de vérification (premier
  /// appareil) ou vérifie la phrase (appareils suivants). Rien n'est écrit si elle est fausse.
  Future<void> setup(String phrase, {int iterations = kdfIterations}) async {
    final rows = await _select({'select': 'blob', 'kind': 'eq.meta', 'item_id': 'eq.check'});
    if (rows.isEmpty) {
      final salt = SyncCrypto.newSalt();
      final crypto = SyncCrypto(SecretKey(await SyncCrypto.deriveBytes(phrase, salt, iterations: iterations)));
      final check = jsonEncode({'v': 1, 'salt': base64.encode(salt), 'iter': iterations, 'check': await crypto.seal('meta', 'check', _checkPlain)});
      await _upsert([{'kind': 'meta', 'item_id': 'check', 'updated_at': _now(), 'deleted': false, 'blob': check}]);
      await _keep(crypto);
      return;
    }
    final meta = jsonDecode('${rows.first['blob']}') as Map<String, dynamic>;
    final crypto = SyncCrypto(SecretKey(await SyncCrypto.deriveBytes(phrase, base64.decode('${meta['salt']}'), iterations: (meta['iter'] as num).toInt())));
    try {
      if (await crypto.open('meta', 'check', '${meta['check']}') != _checkPlain) throw SyncError('sync_bad_phrase');
    } on SecretBoxAuthenticationError {
      throw SyncError('sync_bad_phrase');
    }
    await _keep(crypto);
  }

  Future<void> _keep(SyncCrypto crypto) async {
    _crypto = crypto;
    await _storage.write(key: _keyName, value: base64.encode(await crypto.key.extractBytes()));
    final p = backend.prefs;
    p.cloudLastPush = 0;
    p.cloudLastPull = '';
    notifyListeners();
  }

  /// Oublie la clé de cet appareil (déconnexion) ; les données locales restent.
  Future<void> forget() async {
    _crypto = null;
    await _storage.delete(key: _keyName);
    notifyListeners();
  }

  /// « Repartir de zéro » / « Supprimer mes données en ligne » : efface toutes les lignes du compte.
  Future<void> wipeRemote() async {
    final r = await _http.delete(_table({'user_id': 'eq.${account.session!.userId}'}), headers: await _headers());
    if (r.statusCode >= 300) throw SyncError('sync_server');
    await forget();
  }

  static double _now() => DateTime.now().millisecondsSinceEpoch / 1000;

  /// Un cycle complet : envoi puis réception. Renvoie le nombre d'éléments échangés.
  Future<int> run() async {
    final crypto = _crypto;
    if (crypto == null) throw SyncError('sync_not_setup');
    if (running || backend.isRemote) return 0;
    running = true;
    lastError = null;
    notifyListeners();
    try {
      final n = await _push(crypto) + await _pushCreations(crypto) + await _pushStatus(crypto) + await _pull(crypto);
      lastRun = DateTime.now();
      return n;
    } on SyncError catch (e) {
      lastError = e.code;
      rethrow;
    } catch (e) {
      lastError = 'sync_server';
      throw SyncError('sync_server');
    } finally {
      running = false;
      notifyListeners();
    }
  }

  Future<int> _push(SyncCrypto crypto) async {
    final p = backend.prefs;
    final exp = await backend.getJson('/tontolo/cloud/export', {'since': p.cloudLastPush}) as Map<String, dynamic>;
    final rows = <Map<String, dynamic>>[];
    for (final c in (exp['conversations'] as List).cast<Map<String, dynamic>>()) {
      final slim = slimConversation(c);
      final blob = await crypto.seal('conv', '${c['id']}', jsonEncode(slim));
      if (blob.length > 1900000) continue; // trop volumineuse : reste sur l'appareil
      rows.add({'kind': 'conv', 'item_id': '${c['id']}', 'updated_at': (c['updated_at'] as num).toDouble(), 'deleted': c['deleted'] == 1, 'blob': blob});
    }
    // Mémoires (ensembles L/P/R/T).
    final mem = (await backend.getJson('/tontolo/memory') as Map<String, dynamic>)['items'] as List;
    final local = {for (final m in mem.cast<Map<String, dynamic>>()) memoryId('${m['text']}'): m};
    final remoteRows = await _select({'select': 'item_id,deleted', 'kind': 'eq.memory'});
    final remote = {for (final r in remoteRows) if (r['deleted'] != true) '${r['item_id']}'};
    final plan = MemoryPlan.of(local: local.keys.toSet(), previous: p.cloudMemories, remote: remote, remoteDeleted: {});
    for (final id in plan.push) {
      final m = local[id]!;
      rows.add({'kind': 'memory', 'item_id': id, 'updated_at': _now(), 'deleted': false,
          'blob': await crypto.seal('memory', id, jsonEncode({'text': m['text'], 'kind': m['kind'] ?? 'fact'}))});
    }
    for (final id in plan.tombstones) {
      rows.add({'kind': 'memory', 'item_id': id, 'updated_at': _now(), 'deleted': true, 'blob': ''});
    }
    // Clés d'API : envoyées quand elles changent.
    final keys = await Keys.all();
    final keysJson = jsonEncode(Map.fromEntries(keys.entries.toList()..sort((a, b) => a.key.compareTo(b.key))));
    final keysHash = hash.sha256.convert(utf8.encode(keysJson)).toString();
    if (keys.isNotEmpty && keysHash != p.cloudKeysHash) {
      rows.add({'kind': 'keys', 'item_id': 'all', 'updated_at': _now(), 'deleted': false, 'blob': await crypto.seal('keys', 'all', keysJson)});
    }
    await _upsert(rows);
    p.cloudLastPush = (exp['until'] as num).toDouble();
    p.cloudKeysHash = keysHash;
    // P = mémoires présentes ici ; celles venues d'ailleurs y sont ajoutées à leur arrivée.
    p.cloudMemories = local.keys.toSet();
    return rows.length;
  }

  /// Créations terminées (≤ 1 Mo), chiffrées comme le reste.
  Future<int> _pushCreations(SyncCrypto crypto) async {
    final p = backend.prefs;
    var sent = 0;
    for (var round = 0; round < 10; round++) {
      final Map<String, dynamic> exp;
      try {
        exp = await backend.getJson('/tontolo/cloud/creations', {'since': p.cloudCreationsPush}) as Map<String, dynamic>;
      } catch (_) {
        return sent; // cœur plus ancien : pas de créations
      }
      final rows = <Map<String, dynamic>>[];
      for (final c in (exp['creations'] as List).cast<Map<String, dynamic>>()) {
        final id = '$creationPrefix${c['id']}';
        final blob = await crypto.seal('conv', id, jsonEncode(c));
        if (blob.length > 1900000) continue;
        rows.add({'kind': 'conv', 'item_id': id, 'updated_at': (c['updated_at'] as num).toDouble(), 'deleted': false, 'blob': blob});
      }
      await _upsert(rows);
      sent += rows.length;
      final until = (exp['until'] as num).toDouble();
      if (until <= p.cloudCreationsPush) break;
      p.cloudCreationsPush = until;
    }
    return sent;
  }

  /// État des tâches en cours sur cet appareil (« en cours sur le téléphone… »).
  Future<int> _pushStatus(SyncCrypto crypto) async {
    List tasks;
    try {
      tasks = (await backend.getJson('/tontolo/activity') as Map<String, dynamic>)['tasks'] as List;
    } catch (_) {
      return 0;
    }
    if (tasks.isEmpty && _statusSent) return 0;
    final id = '$statusPrefix${backend.prefs.deviceId}';
    final blob = await crypto.seal('conv', id, jsonEncode({'device': deviceName, 'tasks': tasks, 'at': _now()}));
    await _upsert([{'kind': 'conv', 'item_id': id, 'updated_at': _now(), 'deleted': false, 'blob': blob}]);
    _statusSent = tasks.isEmpty;
    return 0; // l'état n'est pas compté comme un élément échangé
  }

  void _applyStatus(String id, Map<String, dynamic> s) {
    final device = id.substring(statusPrefix.length);
    if (device == backend.prefs.deviceId) return;
    final tasks = (s['tasks'] as List? ?? const []).cast<Map<String, dynamic>>();
    final at = (s['at'] as num? ?? 0).toDouble();
    if (tasks.isEmpty) {
      remoteTasks.removeWhere((k, _) => k.startsWith('$device|'));
      return;
    }
    remoteTasks.removeWhere((k, _) => k.startsWith('$device|'));
    for (final t in tasks) {
      remoteTasks['$device|${t['conversation_id']}'] = RemoteTask('${s['device'] ?? '?'}', t, at);
    }
  }

  Future<int> _pull(SyncCrypto crypto) async {
    final p = backend.prefs;
    var applied = 0;
    var since = p.cloudLastPull;
    final convs = <Map<String, dynamic>>[];
    final creations = <Map<String, dynamic>>[];
    while (true) {
      final rows = await _select({
        'select': 'kind,item_id,updated_at,deleted,blob,server_ts',
        if (since.isNotEmpty) 'server_ts': 'gt.$since',
        'kind': 'neq.meta',
        'order': 'server_ts.asc',
        'limit': '200',
      });
      if (rows.isEmpty) break;
      for (final r in rows) {
        final kind = '${r['kind']}';
        final id = '${r['item_id']}';
        try {
          if (kind == 'conv' && id.startsWith(statusPrefix)) {
            _applyStatus(id, jsonDecode(await crypto.open('conv', id, '${r['blob']}')) as Map<String, dynamic>);
          } else if (kind == 'conv' && id.startsWith(creationPrefix)) {
            creations.add(jsonDecode(await crypto.open('conv', id, '${r['blob']}')) as Map<String, dynamic>);
          } else if (kind == 'conv') {
            final c = jsonDecode(await crypto.open('conv', id, '${r['blob']}')) as Map<String, dynamic>;
            if (c['id'] == id) convs.add(c);
          } else if (kind == 'memory') {
            applied += await _applyMemory(crypto, id, r);
          } else if (kind == 'keys') {
            applied += await _applyKeys(crypto, '${r['blob']}');
          }
        } on SecretBoxAuthenticationError {
          continue; // élément altéré ou d'une autre phrase : ignoré
        } on FormatException {
          continue;
        }
      }
      since = '${rows.last['server_ts']}';
      if (rows.length < 200) break;
    }
    // Créations d'abord : la conversation qui les affiche arrive juste après.
    for (var i = 0; i < creations.length; i += 5) {
      try {
        final res = await backend.sendJson('POST', '/tontolo/cloud/creations', {'creations': creations.sublist(i, min(i + 5, creations.length))}) as Map<String, dynamic>;
        applied += (res['applied'] as num).toInt();
      } catch (_) {
        break; // cœur plus ancien
      }
    }
    for (var i = 0; i < convs.length; i += 50) {
      final res = await backend.sendJson('POST', '/tontolo/cloud/import', {'conversations': convs.sublist(i, min(i + 50, convs.length))}) as Map<String, dynamic>;
      applied += (res['applied'] as num).toInt();
    }
    lastImported = {for (final c in convs) '${c['id']}'};
    p.cloudLastPull = since;
    return applied;
  }

  Future<int> _applyMemory(SyncCrypto crypto, String id, Map<String, dynamic> r) async {
    final p = backend.prefs;
    final mem = ((await backend.getJson('/tontolo/memory') as Map<String, dynamic>)['items'] as List).cast<Map<String, dynamic>>();
    final local = {for (final m in mem) memoryId('${m['text']}'): m};
    if (r['deleted'] == true) {
      final m = local[id];
      if (m == null || !p.cloudMemories.contains(id)) return 0;
      await backend.sendJson('DELETE', '/tontolo/memory/${m['id']}');
      p.cloudMemories = p.cloudMemories..remove(id);
      return 1;
    }
    if (local.containsKey(id)) return 0;
    final m = jsonDecode(await crypto.open('memory', id, '${r['blob']}')) as Map<String, dynamic>;
    try {
      await backend.sendJson('POST', '/tontolo/memory', {'text': m['text'], 'kind': m['kind']});
      p.cloudMemories = p.cloudMemories..add(id);
      return 1;
    } catch (_) {
      return 0; // mémoire refusée par le cœur (vide, secret…)
    }
  }

  /// Clés venues d'un autre appareil : ajoutées si absentes ; une clé locale différente
  /// n'est jamais écrasée.
  Future<int> _applyKeys(SyncCrypto crypto, String blob) async {
    final remote = (jsonDecode(await crypto.open('keys', 'all', blob)) as Map).cast<String, String>();
    final local = await Keys.all();
    var n = 0;
    for (final e in remote.entries) {
      if (local.containsKey(e.key) || e.value.isEmpty) continue;
      await Keys.store(backend, e.key, e.value);
      n++;
    }
    return n;
  }
}
