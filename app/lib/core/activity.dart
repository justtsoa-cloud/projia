// Activité des discussions : lesquelles tournent sur CET appareil, lesquelles sur un AUTRE
// appareil (suivi en direct), et lesquelles attendent une réponse de l'utilisateur (question
// du modèle, confirmation d'outil, accord pour un modèle payant). Sert aux pastilles de
// l'historique, au badge du menu et à l'avertissement quand l'utilisateur est ailleurs.

import 'dart:async';

import 'package:flutter/foundation.dart';

import 'backend.dart';
import 'chat_controller.dart';
import 'cloud_sync.dart';

enum Dot { waiting, local, remote }

class ActivityWatcher extends ChangeNotifier {
  ActivityWatcher(this.backend, this.cloud, this.chat);

  final Backend backend;
  final CloudSync cloud;
  final ChatController chat;

  Timer? _timer;
  Set<String> running = {};
  Map<String, Map<String, dynamic>> waiting = {};
  final Set<String> _announced = {};
  bool foreground = true;

  /// Appelé une fois par attente quand l'utilisateur est ailleurs (autre discussion, autre
  /// écran, application en arrière-plan).
  void Function(String conversationId, String title, String reason)? onAttention;

  void start() {
    _timer ??= Timer.periodic(const Duration(seconds: 4), (_) => poll());
    poll();
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> poll() async {
    if (backend.state != BackendState.ready) return;
    try {
      final r = await backend.getJson('/tontolo/activity') as Map<String, dynamic>;
      final nextRunning = {
        for (final t in (r['tasks'] as List? ?? const []).cast<Map<String, dynamic>>()) '${t['conversation_id']}',
      };
      final nextWaiting = {
        for (final w in (r['waiting'] as List? ?? const []).cast<Map<String, dynamic>>()) '${w['conversation_id']}': w,
      };
      final changed = !setEquals(nextRunning, running) || !mapEquals(nextWaiting.map((k, v) => MapEntry(k, '${v['reason']}')), waiting.map((k, v) => MapEntry(k, '${v['reason']}')));
      running = nextRunning;
      waiting = nextWaiting;
      _announced.removeWhere((id) => !waiting.containsKey(id));
      for (final e in waiting.entries) {
        final here = foreground && e.key == chat.conversationId && !chat.busy;
        if (!here && _announced.add(e.key) && !(foreground && e.key == chat.conversationId)) {
          onAttention?.call(e.key, '${e.value['title']}', '${e.value['reason']}');
        }
      }
      if (changed) notifyListeners();
    } catch (_) {
      // cœur injoignable : prochain essai dans 4 s
    }
  }

  /// Pastille d'une discussion de l'historique (null : rien en cours).
  Dot? dotFor(String id) {
    if (waiting.containsKey(id)) return Dot.waiting;
    if (running.contains(id)) return Dot.local;
    if (cloud.liveTasks.any((t) => t.conversationId == id)) return Dot.remote;
    return null;
  }

  /// Quelque chose se passe ailleurs que dans la discussion affichée (badge du menu).
  Dot? get elsewhere {
    final here = chat.conversationId;
    if (waiting.keys.any((id) => id != here)) return Dot.waiting;
    if (running.any((id) => id != here)) return Dot.local;
    if (cloud.liveTasks.any((t) => t.conversationId != here)) return Dot.remote;
    return null;
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}
