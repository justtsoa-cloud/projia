// Conversation vocale mains libres : écouter → transcrire → envoyer → lire la réponse à voix
// haute → écouter à nouveau. Tout se passe sur l'appareil (micro et voix du système) ; seuls
// la transcription et la réponse passent par les modèles gratuits habituels.

import 'dart:async';

import 'package:flutter/foundation.dart';

enum VadEvent { none, speechStarted, speechEnded, timedOut }

/// Détecte le début et la fin d'une phrase à partir du niveau sonore (dBFS) du micro.
/// Le bruit de fond est mesuré pendant les premières 500 ms ; le seuil s'y adapte.
class SilenceDetector {
  SilenceDetector({
    this.minSpeechMs = 350,
    this.endSilenceMs = 1400,
    this.maxWaitMs = 12000,
    this.maxSpeechMs = 60000,
  });

  final int minSpeechMs, endSilenceMs, maxWaitMs, maxSpeechMs;

  int? _t0;
  final List<double> _floor = [];
  double _threshold = -38;
  int? _loudSince; // début du son continu (au-dessus du seuil)
  int? _quietSince; // début du silence suivant la parole
  bool speaking = false;
  int _speechStart = 0;

  double get threshold => _threshold;

  VadEvent feed(double db, int nowMs) {
    _t0 ??= nowMs;
    final t = nowMs - _t0!;
    if (!db.isFinite) db = -120;
    if (t < 500) {
      _floor.add(db);
      if (_floor.length >= 3) {
        final s = [..._floor]..sort();
        _threshold = (s[s.length ~/ 2] + 14).clamp(-48.0, -26.0);
      }
      return VadEvent.none;
    }
    final loud = db > _threshold;
    if (!speaking) {
      if (loud) {
        _loudSince ??= nowMs;
        if (nowMs - _loudSince! >= minSpeechMs) {
          speaking = true;
          _speechStart = _loudSince!;
          _quietSince = null;
          return VadEvent.speechStarted;
        }
      } else {
        _loudSince = null;
      }
      return t > maxWaitMs ? VadEvent.timedOut : VadEvent.none;
    }
    if (loud) {
      _quietSince = null;
    } else {
      _quietSince ??= nowMs;
      if (nowMs - _quietSince! >= endSilenceMs) return VadEvent.speechEnded;
    }
    return nowMs - _speechStart > maxSpeechMs ? VadEvent.speechEnded : VadEvent.none;
  }
}

enum VoiceState { off, listening, hearing, transcribing, thinking, speaking }

/// Boucle de conversation. Les dépendances sont injectées (micro, transcription, envoi, voix) :
/// la logique se teste sans appareil.
class VoiceLoop extends ChangeNotifier {
  VoiceLoop({
    required this.begin,
    required this.finish,
    required this.transcribe,
    required this.ask,
    required this.answer,
    required this.speak,
    required this.stopSpeaking,
    int Function()? clock,
    this.maxTurnsWithoutSpeech = 1,
  }) : _clock = clock ?? (() => DateTime.now().millisecondsSinceEpoch);

  /// Démarre l'enregistrement ; renvoie le flux des niveaux sonores (dBFS), ou null si le micro
  /// est refusé.
  final Future<Stream<double>?> Function() begin;

  /// Arrête l'enregistrement ; renvoie le fichier.
  final Future<String?> Function() finish;
  final Future<String> Function(String path) transcribe;

  /// Envoie la question ; se termine quand la réponse est complète.
  final Future<void> Function(String text) ask;

  /// Texte de la dernière réponse (null si le tour a échoué).
  final String? Function() answer;
  final Future<void> Function(String text) speak;
  final Future<void> Function() stopSpeaking;
  final int Function() _clock;
  final int maxTurnsWithoutSpeech;

  VoiceState state = VoiceState.off;
  String? lastError;
  String? heard; // dernière phrase comprise (affichée un instant)
  bool _stop = false;
  StreamSubscription<double>? _sub;
  Completer<VadEvent>? _waiting;

  bool get active => state != VoiceState.off;

  void _set(VoiceState s) {
    state = s;
    notifyListeners();
  }

  Future<void> start() async {
    if (active) return;
    _stop = false;
    lastError = null;
    var silent = 0;
    try {
      while (!_stop) {
        _set(VoiceState.listening);
        final levels = await begin();
        if (levels == null) {
          lastError = 'mic_denied';
          break;
        }
        final event = await _listen(levels);
        if (_stop) break;
        if (event == VadEvent.timedOut) {
          await finish();
          silent++;
          if (silent >= maxTurnsWithoutSpeech) break; // personne ne parle : on s'arrête
          continue;
        }
        silent = 0;
        _set(VoiceState.transcribing);
        final path = await finish();
        if (path == null || _stop) continue;
        final text = (await transcribe(path)).trim();
        if (text.isEmpty) continue; // bruit : on réécoute
        heard = text;
        _set(VoiceState.thinking);
        await ask(text);
        if (_stop) break;
        final reply = answer();
        if (reply == null || reply.trim().isEmpty) continue;
        _set(VoiceState.speaking);
        await speak(reply);
      }
    } catch (e) {
      lastError = '$e';
    } finally {
      await _sub?.cancel();
      _sub = null;
      try {
        await finish();
      } catch (_) {}
      _set(VoiceState.off);
    }
  }

  /// Écoute le flux jusqu'à la fin de la phrase (ou au délai sans parole).
  Future<VadEvent> _listen(Stream<double> levels) {
    final detector = SilenceDetector();
    final done = _waiting = Completer<VadEvent>();
    _sub = levels.listen((db) {
      if (done.isCompleted) return;
      final ev = detector.feed(db, _clock());
      if (ev == VadEvent.speechStarted) _set(VoiceState.hearing);
      if (ev == VadEvent.speechEnded || ev == VadEvent.timedOut) done.complete(ev);
    }, onDone: () {
      if (!done.isCompleted) done.complete(VadEvent.timedOut);
    });
    return done.future.whenComplete(() async {
      await _sub?.cancel();
      _sub = null;
    });
  }

  /// Arrête la conversation (bouton, retour, changement d'écran).
  Future<void> stop() async {
    _stop = true;
    await stopSpeaking();
    if (_waiting != null && !_waiting!.isCompleted) _waiting!.complete(VadEvent.timedOut);
  }
}
