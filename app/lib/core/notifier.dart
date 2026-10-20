// Notifications locales : « le modèle (ou la création d'image/vidéo) est de nouveau
// disponible ». Android : notification programmée par le système (même application fermée).
// Linux : minuterie tant que l'application est ouverte. Aucun serveur, aucune donnée envoyée.

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

class Notifier {
  Notifier._();

  static final _plugin = FlutterLocalNotificationsPlugin();
  static Future<bool>? _init;
  static final Map<int, Timer> _timers = {};

  static NotificationDetails _details(String channel, String description) => NotificationDetails(
        android: AndroidNotificationDetails(
          'availability',
          channel,
          channelDescription: description,
          icon: 'ic_stat_projia',
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
        ),
        linux: const LinuxNotificationDetails(),
      );

  static Future<bool> _ensure() => _init ??= () async {
        if (!(Platform.isAndroid || Platform.isLinux)) return false;
        try {
          tzdata.initializeTimeZones();
          final ok = await _plugin.initialize(
            settings: const InitializationSettings(
              android: AndroidInitializationSettings('ic_stat_projia'),
              linux: LinuxInitializationSettings(defaultActionName: 'Ouvrir Projia'),
            ),
          );
          return ok ?? false;
        } catch (e) {
          debugPrint('Notifications indisponibles : $e');
          return false;
        }
      }();

  /// Programme « de nouveau disponible » à l'instant `epochSeconds` (heure de retour estimée
  /// par le cœur). Une seule notification par sujet (`topic`) : la dernière remplace l'autre.
  static Future<void> availableAt(double epochSeconds, String topic, String title, String body,
      {String channel = 'Disponibilité des modèles', String channelDescription = ''}) async {
    final details = _details(channel, channelDescription);
    if (!await _ensure()) return;
    final id = topic.hashCode & 0x7fffffff;
    final when = DateTime.fromMillisecondsSinceEpoch((epochSeconds * 1000).round()).add(const Duration(seconds: 20));
    final delay = when.difference(DateTime.now());
    if (delay.inSeconds < 15 || delay.inHours > 30) return; // trop proche (l'app réessaie) ou incertain
    await cancel(topic);
    try {
      if (Platform.isAndroid) {
        final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
        final allowed = await android?.requestNotificationsPermission() ?? true; // Android 13+
        if (!allowed) return;
        await _plugin.zonedSchedule(
          id: id,
          title: title,
          body: body,
          scheduledDate: tz.TZDateTime.from(when.toUtc(), tz.UTC),
          notificationDetails: details,
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        );
      } else {
        _timers[id] = Timer(delay, () {
          _timers.remove(id);
          _plugin.show(id: id, title: title, body: body, notificationDetails: details);
        });
      }
    } catch (e) {
      debugPrint('Notification non programmée : $e');
    }
  }

  /// Rappel discret programmé à `when` (heure locale), jusqu'à plusieurs jours à l'avance : canal
  /// à faible importance (ni son ni vibration). Une seule par `topic`.
  static Future<bool> scheduleAt(DateTime when, String topic, String title, String body,
      {String channel = 'Idées de Projia'}) async {
    if (!Platform.isAndroid || !await _ensure()) return false;
    try {
      final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
      if (!(await android?.requestNotificationsPermission() ?? true)) return false;
      await cancel(topic);
      await _plugin.zonedSchedule(
        id: topic.hashCode & 0x7fffffff,
        title: title,
        body: body,
        scheduledDate: tz.TZDateTime.from(when.toUtc(), tz.UTC),
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails('comeback', channel,
              icon: 'ic_stat_projia', importance: Importance.low, priority: Priority.low),
        ),
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      );
      return true;
    } catch (e) {
      debugPrint('Rappel non programmé : $e');
      return false;
    }
  }

  /// Notification immédiate : une discussion attend votre réponse (application en arrière-plan).
  static Future<void> attention(String topic, String title, String body,
      {String channel = 'Réponses attendues'}) async {
    if (!await _ensure()) return;
    try {
      if (Platform.isAndroid) {
        final android = _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
        if (!(await android?.requestNotificationsPermission() ?? true)) return;
      }
      await _plugin.show(id: topic.hashCode & 0x7fffffff, title: title, body: body, notificationDetails: _details(channel, ''));
    } catch (e) {
      debugPrint('Notification non affichée : $e');
    }
  }

  static Future<void> cancel(String topic) async {
    final id = topic.hashCode & 0x7fffffff;
    _timers.remove(id)?.cancel();
    if (_init == null) return;
    try {
      await _plugin.cancel(id: id);
    } catch (_) {}
  }
}
