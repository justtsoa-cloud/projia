// État de la conversation courante et dialogue avec le cœur (flux SSE).

import 'dart:async';
import 'dart:convert';


import 'package:flutter/foundation.dart';

import 'backend.dart';
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
  StreamSubscription<Map<String, dynamic>>? _sub;
  String? _lastText;

  void refresh() => notifyListeners();

  void newChat() {
    _sub?.cancel();
    conversationId = null;
    messages.clear();
    busy = false;
    pending = null;
    status = null;
    notifyListeners();
  }

  Future<void> open(String id) async {
    newChat();
    conversationId = id;
    try {
      final data = await backend.getJson('/tontolo/conversations/$id') as Map<String, dynamic>;
      await _loadMessages((data['messages'] as List).cast<Map<String, dynamic>>());
      notifyListeners();
      // Réponse encore en cours de génération : on s'y rattache (rejeu puis direct).
      if (data['active'] == true && conversationId == id) _run(backend.follow(id), replay: true);
    } catch (e) {
      messages.add(ChatMessage(role: 'notice', text: 'error|$e'));
      notifyListeners();
    }
  }

  Future<void> _loadMessages(List<Map<String, dynamic>> items) async {
    for (final m in items) {
      final role = m['role'] as String? ?? '';
      if (role == 'tool' || role == 'system') continue;
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
      messages.add(msg);
    }
  }

  Future<void> send(String text, {List<String> images = const [], String? category}) async {
    if (busy || (text.trim().isEmpty && images.isEmpty)) return;
    _lastText = text;
    final user = ChatMessage(role: 'user', text: text)..images = List.of(images);
    messages.add(user);
    final Object content = images.isEmpty
        ? text
        : [
            if (text.isNotEmpty) {'type': 'text', 'text': text},
            for (final img in images) {'type': 'image_url', 'image_url': {'url': img}},
          ];
    _run(backend.sse('/tontolo/chat', {
      'conversation_id': conversationId,
      'content': content,
      'model': modelOverride,
      'category': category,
    }));
  }

  /// Retouche **faite sur l'appareil** (fidèle : la personne et la composition restent
  /// intactes, rien n'est envoyé à un service en ligne). Le résultat est ensuite enregistré
  /// dans la conversation et la galerie.
  Future<void> sendLocalRetouch(String text, Uint8List original, String previewDataUrl,
      EditIntent intent) async {
    if (busy) return;
    busy = true;
    status = 'retouching';
    final user = ChatMessage(role: 'user', text: text)..images = [previewDataUrl];
    final answer = ChatMessage(role: 'assistant', streaming: true)
      ..modelName = 'Retouche locale (sur l\'appareil)'
      ..model = 'local:retouche'
      ..job = {'status': 'running', 'kind': 'image_edit', 'params': <String, dynamic>{}};
    messages..add(user)..add(answer);
    notifyListeners();
    try {
      final jpg = await retouchPhoto(original, intent.plan);
      final note = 'Retouche faite sur votre appareil, rien n\'a été envoyé. '
          '${intent.plan.steps.join(' · ')}. La personne et la composition sont inchangées.';
      final res = await backend.sendJson('POST', '/tontolo/chat/local-media', {
        'conversation_id': conversationId,
        'content': [
          if (text.isNotEmpty) {'type': 'text', 'text': text},
          {'type': 'image_url', 'image_url': {'url': previewDataUrl}},
        ],
        'result_b64': base64Encode(jpg),
        'mime': 'image/jpeg',
        'note': note,
      }) as Map<String, dynamic>;
      conversationId = res['conversation_id'] as String;
      answer
        ..job = (res['job'] as Map).cast<String, dynamic>()
        ..uid = res['uid'] as String?
        ..streaming = false;
    } catch (e) {
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
    busy = true;
    status = null;
    notifyListeners();
    ChatMessage? current;
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
      switch (ev['type']) {
        case 'conversation':
          conversationId = ev['id'] as String;
        case 'user_saved':
          final lastUser = messages.lastWhere((m) => m.role == 'user', orElse: () => ChatMessage(role: 'user'));
          lastUser.uid = ev['uid'] as String?;
          lastUser.seq = ev['seq'] as int?;
        case 'memory_saved':
          messages.add(ChatMessage(role: 'notice', text: 'memory|${ev['text']}'));
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
              ChatMessage(role: 'notice', text: 'switched|${ev['to_name'] ?? ev['to']}|${ev['reason']}|$count'));
        case 'offline':
          status = 'offline|${ev['seconds']}';
        case 'tool_call':
          status = 'tool|${ev['name']}';
        case 'tool_result':
          status = null;
        case 'job':
          status = 'generating';
          final c = ensureCurrent();
          c.job = Map<String, dynamic>.from(ev)..remove('type');
        case 'done':
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
        case 'tool_confirmation':
          pending = PendingAction.tools((ev['calls'] as List).cast<Map<String, dynamic>>());
        case 'paid_confirmation':
          pending = PendingAction.paid('${ev['name']}', (ev['estimated_cost_usd'] as num?)?.toDouble());
          if (current != null && current!.text.isEmpty) messages.remove(current);
        case 'error':
          if (current != null && current!.text.isEmpty) messages.remove(current);
          messages.add(ChatMessage(role: 'notice', text: 'error|${ev['message']}'));
      }
      notifyListeners();
    }, onError: (Object e) {
      messages.add(ChatMessage(role: 'notice', text: 'error|$e'));
      _finish();
    }, onDone: _finish);
  }

  void _finish() {
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
