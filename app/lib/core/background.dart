// Travail en arrière-plan sur Android : pendant qu'une réponse est générée, un service de
// premier plan (notification discrète « Projia termine votre réponse… ») empêche Android
// d'endormir ou d'arrêter l'application quand on la quitte. Sans effet ailleurs.

import 'dart:io';

import 'package:flutter/services.dart';

class BackgroundWork {
  static const _channel = MethodChannel('projia/background');
  static bool _running = false;

  static void start() {
    if (!Platform.isAndroid || _running) return;
    _running = true;
    _channel.invokeMethod<void>('start').catchError((_) => _running = false);
  }

  static void stop() {
    if (!Platform.isAndroid || !_running) return;
    _running = false;
    _channel.invokeMethod<void>('stop').catchError((_) {});
  }
}
