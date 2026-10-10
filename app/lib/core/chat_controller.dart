// État de la conversation courante et dialogue avec le cœur (flux SSE).

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'backend.dart';

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
  String? uid;
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
    final data = await backend.getJson('/tontolo/conversations/$id') as Map<String, dynamic>;
    for (final m in (data['messages'] as List).cast<Map<String, dynamic>>()) {
      final role = m['role'] as String;
      if (role == 'tool' || role == 'system') continue;
      final meta = (m['_meta'] as Map?)?.cast<String, dynamic>() ?? {};
      final msg = ChatMessage(role: role, model: meta['model'] as String?);
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
    notifyListeners();
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

  void retry() {
    if (_lastText == null) return;
    if (messages.isNotEmpty && messages.last.role == 'notice') messages.removeLast();
    if (messages.isNotEmpty && messages.last.role == 'user') messages.removeLast();
    send(_lastText!);
  }

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

  void stop() {
    _sub?.cancel();
    _sub = null;
    busy = false;
    status = null;
    for (final m in messages) {
      m.streaming = false;
    }
    notifyListeners();
  }

  void _run(Stream<Map<String, dynamic>> events) {
    busy = true;
    status = null;
    notifyListeners();
    ChatMessage? current;
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
          status = null;
        case 'stream_reset':
          ensureCurrent().text = '';
          messages.insert(messages.length - 1, ChatMessage(role: 'notice', text: 'stream_reset|'));
        case 'model_switched':
          final c = ensureCurrent();
          c.model = ev['to'] as String?;
          c.modelName = ev['to_name'] as String?;
          lastModelName = c.modelName;
          messages.insert(messages.length - 1,
              ChatMessage(role: 'notice', text: 'switched|${ev['to_name'] ?? ev['to']}|${ev['reason']}'));
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
            c.text = c.job!['status'] == 'done' ? '' : '${msg['content'] ?? ''}';
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
