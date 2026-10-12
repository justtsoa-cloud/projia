// État de la conversation courante et dialogue avec le cœur (flux SSE).

import 'dart:async';
import 'dart:convert';


import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../l10n/strings.dart';
import 'background.dart';
import 'backend.dart';
import 'notifier.dart';
import 'stats.dart';
import 'retouch.dart';

class ChatMessage {
  ChatMessage({required this.role, this.text = '', this.model, this.modelName, this.streaming = false});

  final String role; // user | assistant | notice
  String text;
  String? model;
  String? modelName;
  Map<String, dynamic>? reason;
  Map<String, dynamic>? job; // création média liée
  List<String> images = []; // pièces jointes (data URL)
  List<Map<String, dynamic>> sources = [];
  bool streaming;
  String reasoning = ''; // réflexion du modèle (affichée à part, repliable)
  String? uid;
  int? seq; // position en base (modifier et renvoyer)
}

/// Question à choix posée par Tontolo (outil `ask_user`) pour préciser la demande.
class AskedQuestion {
  AskedQuestion(this.question, this.options, this.multiple);
  final String question;
  final List<String> options;
  final bool multiple;

  static List<AskedQuestion> parse(dynamic raw) => [
        for (final q in (raw as List? ?? const []).whereType<Map>())
          if ('${q['question'] ?? ''}'.isNotEmpty && (q['options'] as List? ?? const []).length >= 2)
            AskedQuestion('${q['question']}', [for (final o in q['options'] as List) '$o'],
                q['multiple'] == true),
      ];
}

class PendingAction {
  PendingAction.paid(this.model, this.cost) : kind = 'paid', tools = const [];
  PendingAction.tools(this.tools) : kind = 'tools', model = null, cost = null;
  final String kind;
  final String? model;
  final double? cost;
  final List<Map<String, dynamic>> tools;
}

class ChatController extends ChangeNotifier {
  ChatController(this.backend);

  final Backend backend;
  String? conversationId;
  final List<ChatMessage> messages = [];
  bool busy = false;
  String? modelOverride; // null = Auto (ou préférence enregistrée côté cœur)
  String? lastModelName;
  String? status; // « Recherche sur le web… », etc.
  PendingAction? pending;
  List<AskedQuestion> asked = []; // questions à choix en attente de réponse
  StreamSubscription<Map<String, dynamic>>? _sub;
  String? _lastText;
  int _epoch = 0; // invalide les lectures de la discussion quittée
  int _streamEpoch = 0;
  Timer? _offlineTimer; // message en attente du retour du réseau

  @override
  void dispose() {
    _epoch++;
    _streamEpoch++;
    _sub?.cancel();
    _offlineTimer?.cancel();
    super.dispose();
  }

  void refresh() => notifyListeners();

  // Mode Apprendre (tuteur) : propre à chaque discussion, mémorisé par le cœur.
  late bool learn = backend.prefs.learnMode;
  String get level => backend.prefs.learnLevel;
  bool _modeChanged = false; // à transmettre avec le prochain message

  void setLearn(bool value) {
    learn = value;
    agent = null;
    backend.prefs.learnMode = value;
    _modeChanged = true;
    notifyListeners();
  }

  // Mode Agent : null = désactivé ; sinon « auto », « researcher », « developer »,
  // « writer » ou « analyst ». Propre à chaque discussion (mémorisé par le cœur).
  String? agent;

  void setAgent(String? value) {
    agent = value;
    if (value != null) {
      learn = false;
      backend.prefs.learnMode = false;
    }
    _modeChanged = true;
    notifyListeners();
  }

  /// Plan d'une tâche complexe (mode « parallel » ou « steps ») et état de ses étapes.
  Map<String, dynamic>? plan;
  final Map<int, Map<String, dynamic>> planSteps = {};

  bool get planActive => plan != null && plan!['status'] == 'active';

  /// Pas à pas : étape suivante du plan.
  Future<void> continuePlan(String label) => send(label);

  Future<void> dropPlan() async {
    final id = conversationId;
    plan = null;
    planSteps.clear();
    notifyListeners();
    if (id != null) await backend.sendJson('DELETE', '/tontolo/conversations/$id/plan');
  }

  /// Fiche compactée du début de la discussion (null si elle n'a pas encore été compactée).
  String? summary;

  /// Compactage manuel : renvoie la fiche (ou null s'il n'y a rien à compacter).
  Future<String?> compact() async {
    final id = conversationId;
    if (id == null) return null;
    final r = await backend.sendJson('POST', '/tontolo/conversations/$id/compact', {}) as Map<String, dynamic>;
    summary = r['summary'] as String?;
    notifyListeners();
    return r['ok'] == true ? summary : null;
  }

  String get mode => learn ? 'learn' : agent != null ? 'agent' : 'general';

  void setLevel(String value) {
    backend.prefs.learnLevel = value;
    _modeChanged = true;
    notifyListeners();
  }

  /// Bandeau d'information dans la discussion courante (ex. « discussion importée »).
  void addNotice(String raw) {
    messages.add(ChatMessage(role: 'notice', text: raw));
    notifyListeners();
  }

  bool get offlineQueued => _offlineTimer != null;

  /// Hors ligne : le message reste en attente et part tout seul au retour du réseau.
  void _queueOffline() {
    _offlineTimer?.cancel();
    messages.add(ChatMessage(role: 'notice', text: 'offline_queued|'));
    _offlineTimer = Timer.periodic(const Duration(seconds: 8), (_) => checkOfflineQueue());
  }

  /// Vérifie la connexion (aussi appelé au retour au premier plan) et renvoie le message.
  Future<void> checkOfflineQueue() async {
    if (_offlineTimer == null || busy) return;
    try {
      final r = await backend.getJson('/tontolo/online') as Map<String, dynamic>;
      if (r['online'] != true || _offlineTimer == null) return;
    } catch (_) {
      return;
    }
    cancelOfflineQueue(notify: false);
    retry();
  }

  void cancelOfflineQueue({bool notify = true}) {
    _offlineTimer?.cancel();
    _offlineTimer = null;
    messages.removeWhere((m) => m.role == 'notice' && m.text.startsWith('offline_queued|'));
    if (notify) notifyListeners();
  }

  /// Échec avec heure de retour connue : notification « de nouveau disponible ». Une réussite
  /// annule la notification du même sujet.
  void _notifyAvailability(Map<String, dynamic> job) {
    final kind = '${job['kind']}';
    final topic = 'media_$kind';
    if (job['status'] == 'done') {
      Notifier.cancel(topic);
      return;
    }
    final at = ((job['params'] as Map?)?['retry_at'] as num?)?.toDouble();
    if (job['status'] == 'failed' && at != null) {
      _schedule(at, topic, kind == 'video_gen' ? 'notif_video' : kind.startsWith('image') ? 'notif_image' : 'notif_media');
    }
  }

  void _schedule(double at, String topic, String key) {
    final locale = backend.prefs.locale;
    Notifier.availableAt(at, topic, tr(locale, 'notif_title'), tr(locale, key),
        channel: tr(locale, 'notif_channel'), channelDescription: tr(locale, 'notif_channel_desc'));
  }

  /// Raison de bascule dans la langue de l'interface (code du moteur, sinon texte d'origine).
  String _reasonText(Map<String, dynamic> ev) {
    final code = ev['reason_code'] as String?;
    if (code == null || code.isEmpty) return '${ev['reason'] ?? ''}';
    final key = 'why_$code';
    final t = tr(backend.prefs.locale, key);
    return t == key ? '${ev['reason'] ?? ''}' : t;
  }

  /// Documents joints à la conversation (noms et pages), affichés au-dessus de la saisie.
  final List<Map<String, dynamic>> documents = [];

  /// Joint un document (PDF, texte…) : le cœur en extrait le texte et s'en sert pour répondre
  /// en citant les pages. Renvoie un message d'erreur (traduit) ou null.
  Future<String?> attachDocument(String name, Uint8List bytes) async {
    final epoch = _epoch;
    final req = http.MultipartRequest('POST', backend.uri('/tontolo/documents'))
      ..headers.addAll(backend.headers)
      ..files.add(http.MultipartFile.fromBytes('file', bytes, filename: name));
    if (conversationId != null) req.fields['conversation_id'] = conversationId!;
    try {
      final resp = await http.Response.fromStream(await req.send()).timeout(const Duration(minutes: 2));
      final body = jsonDecode(utf8.decode(resp.bodyBytes));
      if (resp.statusCode != 200) {
        return (body is Map && body['detail'] is String) ? body['detail'] as String : tr(backend.prefs.locale, 'error_generic');
      }
      final doc = (body as Map).cast<String, dynamic>();
      if (epoch != _epoch) return null;
      conversationId = doc['conversation_id'] as String;
      documents.add(doc);
      messages.add(ChatMessage(role: 'notice', text: 'document|${doc['name']}|${doc['pages']}'));
      notifyListeners();
      return null;
    } catch (_) {
      return tr(backend.prefs.locale, 'error_generic');
    }
  }

  Future<void> _loadDocuments() async {
    documents.clear();
    final cid = conversationId;
    final epoch = _epoch;
    if (cid == null) return;
    try {
      final list = await backend.getJson('/tontolo/conversations/$cid/documents') as List;
      if (epoch != _epoch) return;
      documents.addAll(list.cast<Map<String, dynamic>>());
    } catch (_) {}
  }

  Future<void> removeDocument(Map<String, dynamic> doc) async {
    if (conversationId == null) return;
    final epoch = _epoch;
    await backend.sendJson('DELETE', '/tontolo/conversations/$conversationId/documents/${doc['id']}');
    if (epoch != _epoch) return;
    documents.remove(doc);
    notifyListeners();
  }

  void newChat() {
    BackgroundWork.stop();
    _epoch++;
    _streamEpoch++;
    _lastText = null;
    lastModelName = null;
    documents.clear();
    cancelOfflineQueue(notify: false);
    _sub?.cancel();
    conversationId = null;
    learn = backend.prefs.learnMode;
    agent = null;
    summary = null;
    plan = null;
    planSteps.clear();
    _modeChanged = false;
    messages.clear();
    asked = [];
    earlierLeft = 0;
    loadingEarlier = false;
    busy = false;
    pending = null;
    status = null;
    notifyListeners();
  }

  Future<void> open(String id) async {
    newChat();
    conversationId = id;
    final epoch = _epoch;
    busy = true;
    notifyListeners();
    try {
      final data = await backend.getJson('/tontolo/conversations/$id?tail=$pageSize')
          as Map<String, dynamic>;
      if (epoch != _epoch) return;
      earlierLeft = _earlierCount(data);
      if (data.containsKey('mode')) {
        final mode = '${data['mode']}';
        learn = mode.startsWith('learn');
        summary = data['summary'] as String?;
        plan = (data['plan'] as Map?)?.cast<String, dynamic>();
        agent = mode.startsWith('agent') ? (mode.contains(':') ? mode.split(':')[1] : 'auto') : null;
      }
      await _loadMessages((data['messages'] as List).cast<Map<String, dynamic>>());
      if (epoch != _epoch) return;
      await _loadDocuments();
      if (epoch != _epoch) return;
      busy = false;
      notifyListeners();
      // Réponse encore en cours de génération : on s'y rattache (rejeu puis direct).
      if (data['active'] == true && conversationId == id) _run(backend.follow(id), replay: true);
    } catch (e) {
      if (epoch != _epoch) return;
      busy = false;
      messages.add(ChatMessage(role: 'notice', text: 'error|$e'));
      notifyListeners();
    }
  }

  /// Messages chargés à l'ouverture : les plus récents seulement (fils de milliers de messages).
  static const pageSize = 120;

  /// Nombre de messages plus anciens encore sur le cœur (0 = tout est affiché).
  int earlierLeft = 0;
  bool loadingEarlier = false;

  int _earlierCount(Map<String, dynamic> data) {
    final total = data['total'];
    final got = (data['messages'] as List).length;
    return total is int && total > got ? total - got : 0;
  }

  /// Ajoute en tête la page précédente de la discussion.
  Future<void> loadEarlier() async {
    final id = conversationId;
    final first = messages.where((m) => m.seq != null).map((m) => m.seq!).fold<int?>(
        null, (a, b) => a == null || b < a ? b : a);
    if (id == null || first == null || loadingEarlier || earlierLeft <= 0) return;
    final epoch = _epoch;
    loadingEarlier = true;
    notifyListeners();
    try {
      final data = await backend.getJson('/tontolo/conversations/$id?tail=$pageSize&before=$first')
          as Map<String, dynamic>;
      if (epoch != _epoch) return;
      final keep = List<ChatMessage>.of(messages);
      messages.clear();
      await _loadMessages((data['messages'] as List).cast<Map<String, dynamic>>());
      if (epoch != _epoch) return;
      messages.addAll(keep);
      final got = (data['messages'] as List).length;
      earlierLeft = earlierLeft > got ? earlierLeft - got : 0;
    } catch (_) {
      // la page reste disponible : l'utilisateur peut réessayer
    } finally {
      if (epoch == _epoch) {
        loadingEarlier = false;
        notifyListeners();
      }
    }
  }

  Future<void> _loadMessages(List<Map<String, dynamic>> items) async {
    final epoch = _epoch;
    final loaded = <ChatMessage>[];
    List<AskedQuestion> lastAsk = [];
    for (final m in items) {
      final role = m['role'] as String? ?? '';
      if (role == 'tool' || role == 'system') continue;
      if (role == 'user') lastAsk = [];
      for (final c in (m['tool_calls'] as List? ?? const []).whereType<Map>()) {
        final fn = c['function'] as Map?;
        if (fn?['name'] == 'ask_user') {
          try {
            lastAsk = AskedQuestion.parse((jsonDecode('${fn!['arguments']}') as Map)['questions']);
          } catch (_) {}
        }
      }
      final meta = (m['_meta'] as Map?)?.cast<String, dynamic>() ?? {};
      final msg = ChatMessage(role: role, model: meta['model'] as String?)
        ..uid = meta['uid'] as String?
        ..seq = meta['seq'] as int?;
      final content = m['content'];
      if (content is String) {
        msg.text = content;
      } else if (content is List) {
        for (final p in content.cast<Map>()) {
          if (p['type'] == 'text') msg.text += '${p['text']}';
          if (p['type'] == 'image_url') msg.images.add('${(p['image_url'] as Map)['url']}');
        }
      }
      final media = RegExp(r'^\[média:([0-9a-f]+)\]$').firstMatch(msg.text);
      if (media != null) {
        try {
          msg.job = await backend.getJson('/tontolo/media/${media.group(1)}') as Map<String, dynamic>;
          msg.text = '';
        } catch (_) {}
      }
      if (role == 'assistant' && msg.text.isEmpty && msg.job == null && m['tool_calls'] != null) continue;
      if (epoch != _epoch) return;
      loaded.add(msg);
    }
    if (epoch == _epoch) {
      messages.addAll(loaded);
      asked = lastAsk;
    }
  }

  Future<void> send(String text, {List<String> images = const [], String? category}) async {
    if (busy || (text.trim().isEmpty && images.isEmpty)) return;
    cancelOfflineQueue(notify: false);
    asked = [];
    Stats.countMessage(backend.prefs);
    _lastText = text;
    final user = ChatMessage(role: 'user', text: text)..images = List.of(images);
    messages.add(user);
    final Object content = images.isEmpty
        ? text
        : [
            if (text.isNotEmpty) {'type': 'text', 'text': text},
            for (final img in images) {'type': 'image_url', 'image_url': {'url': img}},
          ];
    // Le mode n'est envoyé que s'il compte : nouvelle discussion, bascule, ou mode Apprendre
    // (un ancien serveur distant ignore simplement ces champs).
    final sendMode = conversationId == null || _modeChanged || learn || agent != null;
    _modeChanged = false;
    _run(backend.sse('/tontolo/chat', {
      'conversation_id': conversationId,
      'content': content,
      'model': modelOverride,
      'category': category,
      if (sendMode) 'mode': mode,
      if (sendMode && learn) 'level': level,
      if (sendMode && agent != null) 'agent': agent,
    }));
  }

  /// Retouche **faite sur l'appareil** (fidèle : la personne et la composition restent
  /// intactes, rien n'est envoyé à un service en ligne). Le résultat est ensuite enregistré
  /// dans la conversation et la galerie.
  Future<void> sendLocalRetouch(String text, Uint8List original, String previewDataUrl,
      EditIntent intent) async {
    if (busy) return;
    final epoch = _epoch;
    final streamEpoch = ++_streamEpoch;
    final cid = conversationId;
    busy = true;
    status = 'retouching';
    final user = ChatMessage(role: 'user', text: text)..images = [previewDataUrl];
    final answer = ChatMessage(role: 'assistant', streaming: true)
      ..modelName = tr(backend.prefs.locale, 'local_retouch_name')
      ..model = 'local:retouche'
      ..job = {'status': 'running', 'kind': 'image_edit', 'params': <String, dynamic>{}};
    messages..add(user)..add(answer);
    notifyListeners();
    try {
      final jpg = await retouchPhoto(original, intent.plan);
      if (epoch != _epoch || streamEpoch != _streamEpoch) return;
      final loc = backend.prefs.locale;
      final note = tr(loc, 'local_retouch_note',
          {'steps': intent.plan.steps.map((k) => tr(loc, k)).join(' · ')});
      final res = await backend.sendJson('POST', '/tontolo/chat/local-media', {
        'conversation_id': cid,
        'content': [
          if (text.isNotEmpty) {'type': 'text', 'text': text},
          {'type': 'image_url', 'image_url': {'url': previewDataUrl}},
        ],
        'result_b64': base64Encode(jpg),
        'mime': 'image/jpeg',
        'note': note,
      }) as Map<String, dynamic>;
      if (epoch != _epoch || streamEpoch != _streamEpoch) return;
      conversationId = res['conversation_id'] as String;
      answer
        ..job = (res['job'] as Map).cast<String, dynamic>()
        ..uid = res['uid'] as String?
        ..streaming = false;
    } catch (e) {
      if (epoch != _epoch || streamEpoch != _streamEpoch) return;
      messages.remove(answer);
      messages.add(ChatMessage(role: 'notice', text: 'error|$e'));
    }
    busy = false;
    status = null;
    notifyListeners();
  }

  /// Réessayer après une erreur : si la conversation existe, on régénère la réponse au
  /// dernier message (sans le dupliquer) ; sinon on renvoie le texte.
  void retry() {
    if (busy) return;
    while (messages.isNotEmpty && messages.last.role != 'user') {
      messages.removeLast();
    }
    if (conversationId != null && messages.isNotEmpty) {
      regenerate(keepLast: true);
    } else if (_lastText != null) {
      if (messages.isNotEmpty) messages.removeLast();
      send(_lastText!);
    }
  }

  /// Régénère la dernière réponse (même modèle ou celui choisi dans le sélecteur).
  void regenerate({bool keepLast = false}) {
    if (busy || conversationId == null) return;
    if (!keepLast) {
      while (messages.isNotEmpty && messages.last.role != 'user') {
        messages.removeLast();
      }
    }
    _run(backend.sse('/tontolo/chat/$conversationId/regenerate', {'approved': true, 'model': modelOverride}));
  }

  /// Modifie un message utilisateur et relance la conversation à partir de lui.
  void editAndResend(ChatMessage m, String text) {
    if (busy || conversationId == null || m.seq == null || text.trim().isEmpty) return;
    final i = messages.indexOf(m);
    if (i < 0) return;
    messages.removeRange(i + 1, messages.length);
    m.text = text;
    _run(backend.sse('/tontolo/chat/$conversationId/edit', {'seq': m.seq, 'content': text, 'model': modelOverride}));
  }

  bool get canRegenerate =>
      !busy && conversationId != null && messages.isNotEmpty && messages.last.role == 'assistant';

  Future<void> resolveTools(bool approved) async {
    pending = null;
    _run(backend.sse('/tontolo/chat/$conversationId/resume', {'approved': approved, 'model': modelOverride}));
  }

  Future<void> resolvePaid(bool approved) async {
    pending = null;
    notifyListeners();
    if (!approved || conversationId == null) return;
    await backend.sendJson('POST', '/tontolo/chat/$conversationId/approve-paid');
    // Relance du dernier message utilisateur, désormais autorisé en payant.
    if (messages.isNotEmpty && messages.last.role == 'user') {
      final last = messages.removeLast();
      send(last.text, images: last.images);
    }
  }

  /// Arrêt demandé par l'utilisateur : interrompt aussi la génération côté cœur.
  void stop() {
    _streamEpoch++;
    final cid = conversationId;
    if (cid != null) {
      backend.sendJson('POST', '/tontolo/chat/$cid/stop').catchError((_) {});
    }
    _sub?.cancel();
    _sub = null;
    busy = false;
    status = null;
    for (final m in messages) {
      m.streaming = false;
    }
    notifyListeners();
  }

  void _run(Stream<Map<String, dynamic>> events, {bool replay = false}) {
    final epoch = _epoch;
    final streamEpoch = ++_streamEpoch;
    bool currentStream() => epoch == _epoch && streamEpoch == _streamEpoch;
    busy = true;
    status = null;
    notifyListeners();
    ChatMessage? current;
    var terminal = false; // fin normale du tour reçue (sinon : connexion coupée → rattachement)
    BackgroundWork.start();
    // Rattachement : le rejeu recommence au début du tour, on repart d'une réponse vide.
    if (replay && messages.isNotEmpty && messages.last.role == 'assistant' && messages.last.uid == null) {
      messages.removeLast();
    }
    ChatMessage ensureCurrent() {
      if (current == null) {
        current = ChatMessage(role: 'assistant', streaming: true);
        messages.add(current!);
      }
      return current!;
    }

    _sub = events.listen((ev) {
      if (!currentStream()) return;
      switch (ev['type']) {
        case 'conversation':
          conversationId = ev['id'] as String;
        case 'user_saved':
          final lastUser = messages.lastWhere((m) => m.role == 'user', orElse: () => ChatMessage(role: 'user'));
          lastUser.uid = ev['uid'] as String?;
          lastUser.seq = ev['seq'] as int?;
        case 'memory_saved':
          messages.add(ChatMessage(role: 'notice', text: 'memory|${ev['text']}'));
        case 'step':
          // Création de fichier : rédaction, construction, relecture, corrections.
          status = '${ev['step']}' == 'doc_done'
              ? null
              : '${ev['step']}' == 'book_chapter'
                  ? 'book_chapter|${ev['n']}|${ev['total']}'
                  : '${ev['step']}';
        case 'review':
          // Équipe de modèles : verdict du second modèle sur la réponse qui vient d'arriver.
          status = null;
          final issues = ((ev['issues'] as List?) ?? const []).join('\u0001');
          messages.add(ChatMessage(role: 'notice', text: 'review|${ev['ok'] == true ? 1 : 0}|${ev['name'] ?? ''}|$issues'));
        case 'waiting':
          status = 'waiting|${ev['seconds']}';
        case 'route':
          final c = ensureCurrent();
          c.model = ev['model'] as String?;
          c.modelName = ev['name'] as String?;
          c.reason = (ev['reason'] as Map?)?.cast<String, dynamic>();
          lastModelName = c.modelName;
        case 'model_returned':
          messages.add(ChatMessage(role: 'notice', text: 'returned|${ev['name'] ?? ev['model']}'));
        case 'web_search':
          status = 'searching_web';
          ensureCurrent().sources = (ev['results'] as List).cast<Map<String, dynamic>>();
        case 'delta':
          final c = ensureCurrent();
          if (ev['content'] != null) c.text += ev['content'] as String;
          final r = ev['reasoning'] ?? ev['reasoning_content'];
          if (r != null) c.reasoning += r as String;
          status = c.text.isEmpty && c.reasoning.isNotEmpty ? 'thinking' : null;
        case 'media_switch':
          // Le modèle de texte a refusé de produire une image : on repart en création d'image.
          final c = ensureCurrent();
          c.text = '';
          c.reasoning = '';
          messages.insert(messages.length - 1, ChatMessage(role: 'notice', text: 'media|'));
          status = 'generating';
        case 'stopped':
          terminal = true;
          status = null;
        case 'stream_reset':
          ensureCurrent().text = '';
          messages.insert(messages.length - 1, ChatMessage(role: 'notice', text: 'stream_reset|'));
        case 'model_switched':
          final c = ensureCurrent();
          c.model = ev['to'] as String?;
          c.modelName = ev['to_name'] as String?;
          lastModelName = c.modelName;
          // Une série de bascules consécutives tient sur une seule ligne (la dernière + le total).
          var count = 1;
          final prev = messages.length >= 2 ? messages[messages.length - 2] : null;
          if (prev != null && prev.role == 'notice' && prev.text.startsWith('switched|')) {
            final p = prev.text.split('|');
            count = (p.length > 3 ? int.tryParse(p[3]) ?? 1 : 1) + 1;
            messages.remove(prev);
          }
          messages.insert(messages.length - 1,
              ChatMessage(role: 'notice', text: 'switched|${ev['to_name'] ?? ev['to']}|${_reasonText(ev)}|$count'));
        case 'offline':
          status = 'offline|${ev['seconds']}';
        case 'tool_call':
          status = 'tool|${ev['name']}';
        case 'tool_result':
          status = null;
        case 'plan':
          plan = (ev['plan'] as Map?)?.cast<String, dynamic>();
          if (plan?['status'] != 'active') planSteps.clear();
          if (status == 'planning') status = null;
        case 'plan_step':
          planSteps[(ev['i'] as num).toInt()] = Map<String, dynamic>.from(ev);
          status = 'plan_running';
        case 'continuing':
          // Réponse coupée par la limite de longueur : suite demandée automatiquement.
          status = 'continuing';
        case 'job':
          status = 'generating';
          final c = ensureCurrent();
          c.job = Map<String, dynamic>.from(ev)..remove('type');
          _notifyAvailability(c.job!);
        case 'done':
          if (ev['job'] == null) Notifier.cancel('chat');
          final c = ensureCurrent();
          final msg = (ev['message'] as Map).cast<String, dynamic>();
          if (ev['job'] != null) {
            c.job = (ev['job'] as Map).cast<String, dynamic>();
            c.text = ''; // l'état (image, erreur) est affiché par la carte média, pas en double
          } else if (msg['tool_calls'] != null && (msg['content'] ?? '').toString().isEmpty) {
            // Étape d'outil : la réponse finale arrivera dans un message suivant.
            messages.remove(c);
            current = null;
            return;
          } else {
            c.text = '${msg['content'] ?? c.text}';
          }
          c.model = ev['model'] as String?;
          c.modelName = ev['name'] as String? ?? c.modelName;
          c.uid = ev['uid'] as String?;
          c.streaming = false;
          current = null;
          terminal = true;
        case 'question':
          terminal = true;
          asked = AskedQuestion.parse(ev['questions']);
        case 'tool_confirmation':
          terminal = true;
          pending = PendingAction.tools((ev['calls'] as List).cast<Map<String, dynamic>>());
        case 'paid_confirmation':
          terminal = true;
          pending = PendingAction.paid('${ev['name']}', (ev['estimated_cost_usd'] as num?)?.toDouble());
          if (current != null && current!.text.isEmpty) messages.remove(current);
        case 'error' when ev['offline'] == true:
          terminal = true;
          if (current != null && current!.text.isEmpty) messages.remove(current);
          _queueOffline();
        case 'error':
          terminal = true;
          if (current != null && current!.text.isEmpty) messages.remove(current);
          final code = ev['code'] as String?;
          final retryAt = (ev['retry_at'] as num?)?.toDouble();
          if (retryAt != null && code != 'offline') _schedule(retryAt, 'chat', 'notif_chat');
          messages.add(ChatMessage(
              role: 'notice',
              text: code == null
                  ? 'error|${ev['message']}'
                  : 'errorc|$code|${ev['retry_at'] ?? ''}|${ev['message']}'));
      }
      notifyListeners();
    }, onError: (Object e) {
      if (!currentStream()) return;
      // Connexion coupée (application en arrière-plan, mise en veille…) : le tour continue
      // dans le cœur ; on s'y rattache au lieu d'afficher une erreur.
      if (conversationId != null) {
        _recover(fallback: 'error|$e');
        return;
      }
      messages.add(ChatMessage(role: 'notice', text: 'error|$e'));
      _finish();
    }, onDone: () {
      if (!currentStream()) return;
      if (!terminal && conversationId != null) {
        _recover();
        return;
      }
      _finish();
    });
  }

  /// Retour au premier plan : un flux resté muet pendant la veille est relancé.
  void resumeIfStale() {
    if (busy && conversationId != null && _sub != null) _recover();
  }

  /// Rattachement au tour en cours (ou rechargement de la réponse déjà enregistrée).
  Future<void> _recover({String? fallback}) async {
    final id = conversationId;
    if (id == null) return;
    _streamEpoch++;
    await _sub?.cancel();
    _sub = null;
    for (var attempt = 0; attempt < 5; attempt++) {
      await Future<void>.delayed(Duration(milliseconds: 600 * (attempt + 1)));
      if (conversationId != id) return; // l'utilisateur a changé de discussion
      try {
        await backend.getJson('/health');
        BackgroundWork.stop(); // relancé par le suivi si la réponse est encore en cours
        await open(id); // recharge le fil et suit la réponse si elle est encore en cours
        return;
      } catch (_) {
        continue; // cœur en cours de redémarrage
      }
    }
    if (conversationId != id) return;
    messages.add(ChatMessage(role: 'notice', text: fallback ?? 'error|connexion'));
    _finish();
  }

  void _finish() {
    BackgroundWork.stop();
    busy = false;
    status = null;
    for (final m in messages) {
      m.streaming = false;
    }
    _sub = null;
    notifyListeners();
  }

  static String dataUrl(List<int> bytes, String mime) => 'data:$mime;base64,${base64Encode(bytes)}';
}
