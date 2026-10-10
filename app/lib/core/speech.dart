// Lecture à voix haute (voix du système) : une seule lecture à la fois,
// arrêt à tout moment, vitesse réglable. Gratuit et sans quota.

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

class Speech extends ChangeNotifier {
  Speech._() {
    _tts.setStartHandler(() {
      _starting = false;
      _set(true);
    });
    // Un « annulé » ou « terminé » qui arrive pendant le démarrage d'une nouvelle
    // lecture concerne la précédente : il est ignoré.
    _tts.setCompletionHandler(() => _starting ? null : _set(false));
    _tts.setCancelHandler(() => _starting ? null : _set(false));
    _tts.setErrorHandler((msg) {
      _starting = false;
      lastError = '$msg';
      _set(false);
    });
    _tts.awaitSpeakCompletion(false);
  }

  bool _starting = false;

  /// Dernière erreur du moteur (voix absente, moteur indisponible…).
  String? lastError;

  static final Speech instance = Speech._();
  final FlutterTts _tts = FlutterTts();

  /// Identifiant du texte en cours de lecture (null = silence).
  String? speakingId;
  bool _active = false;

  bool isSpeaking(String id) => _active && speakingId == id;

  void _set(bool active) {
    _active = active;
    if (!active) speakingId = null;
    notifyListeners();
  }

  /// Lance la lecture, ou l'arrête si ce même texte est déjà lu.
  Future<void> toggle(String id, String text, {String locale = 'fr', double rate = 0.5}) async {
    if (isSpeaking(id)) {
      await stop();
      return;
    }
    _starting = true;
    if (_active) await _tts.stop();
    speakingId = id;
    _active = true;
    notifyListeners();
    lastError = null;
    final lang = const {'fr': 'fr-FR', 'en': 'en-US', 'mg': 'fr-FR'}[locale] ?? 'fr-FR';
    try {
      // Voix de la langue si elle est installée, sinon voix par défaut du système.
      if (await _tts.isLanguageAvailable(lang) == true) await _tts.setLanguage(lang);
    } catch (_) {}
    await _tts.setSpeechRate(rate);
    final ok = await _tts.speak(plainText(text));
    if (ok != 1) {
      _starting = false;
      lastError ??= 'speak';
      _set(false);
    }
  }

  Future<void> stop() async {
    _starting = false;
    await _tts.stop();
    _set(false);
  }

  /// Retire la syntaxe Markdown/LaTeX pour une lecture naturelle.
  static String plainText(String text) => text
      .replaceAll(RegExp(r'```[\s\S]*?```'), ' (bloc de code) ')
      .replaceAll(RegExp(r'\$\$[\s\S]*?\$\$'), ' (formule) ')
      .replaceAll(RegExp(r'!\[[^\]]*\]\([^)]*\)'), '')
      .replaceAllMapped(RegExp(r'\[([^\]]+)\]\([^)]*\)'), (m) => m[1]!)
      .replaceAll(RegExp(r'[#*_`>|\\$]'), '')
      .replaceAll(RegExp(r'\n{2,}'), '. ')
      .trim();
}
