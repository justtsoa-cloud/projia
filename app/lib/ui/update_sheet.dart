// Annonce de mise à jour (résumé des changements) et présentation des nouveautés
// après installation. Visibles dès l'ouverture, sans passer par les réglages avancés.

import 'dart:io';

import 'package:flutter/material.dart';

import '../core/updater.dart';
import '../core/whats_new.dart';
import '../main.dart';
import 'message_view.dart' show openSafeLink;

/// Annonce « Nouvelle version » : résumé des changements, installer maintenant ou plus tard.
Future<void> showUpdateSheet(BuildContext context) => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _UpdateSheet(),
    );

class _UpdateSheet extends StatelessWidget {
  const _UpdateSheet();

  @override
  Widget build(BuildContext context) {
    final up = AppScope.of(context).updater;
    final linuxAppImage = Platform.isLinux && Platform.environment['APPIMAGE'] != null;
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      maxChildSize: 0.92,
      builder: (context, controller) => ListenableBuilder(
        listenable: up,
        builder: (context, _) {
          final ready = up.file != null && up.status == UpdateStatus.ready;
          final notes = up.notes;
          return Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Icon(Icons.system_update, size: 28),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(context.t('update_title', {'v': up.latest ?? ''}),
                      style: Theme.of(context).textTheme.titleLarge),
                ),
              ]),
              const SizedBox(height: 4),
              Text(context.t('update_from', {'v': appVersion}), style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 12),
              Expanded(
                child: notes.isEmpty
                    ? Center(child: Text(context.t('update_no_notes')))
                    : ListView(controller: controller, children: [
                        for (final (head, items) in notes) ...[
                          Padding(
                            padding: const EdgeInsets.only(top: 8, bottom: 4),
                            child: Text(head, style: Theme.of(context).textTheme.titleSmall?.copyWith(color: Theme.of(context).colorScheme.primary)),
                          ),
                          for (final i in items)
                            Padding(
                              padding: const EdgeInsets.symmetric(vertical: 3),
                              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                const Padding(padding: EdgeInsets.only(top: 6, right: 8), child: Icon(Icons.circle, size: 6)),
                                Expanded(child: Text(i)),
                              ]),
                            ),
                        ],
                      ]),
              ),
              if (up.status == UpdateStatus.downloading)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${context.t('update_downloading')} ${(up.progress * 100).round()} %'),
                    const SizedBox(height: 6),
                    LinearProgressIndicator(value: up.progress == 0 ? null : up.progress),
                  ]),
                ),
              if (up.status == UpdateStatus.failed)
                Text(up.message ?? '', style: TextStyle(color: Theme.of(context).colorScheme.error)),
              const SizedBox(height: 8),
              Row(children: [
                TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('later'))),
                if (up.releaseUrl != null)
                  TextButton(onPressed: () => openSafeLink(up.releaseUrl), child: Text(context.t('details'))),
                const Spacer(),
                FilledButton.icon(
                  icon: Icon(linuxAppImage ? Icons.restart_alt : Icons.download_done),
                  label: Text(linuxAppImage ? context.t('restart') : context.t('install')),
                  onPressed: ready
                      ? () {
                          Navigator.pop(context);
                          linuxAppImage ? up.installLinuxAndRestart() : up.installAndroid();
                        }
                      : null,
                ),
              ]),
            ]),
          );
        },
      ),
    );
  }
}

/// « Quoi de neuf » : présentation des nouveautés de la version installée.
Future<void> showWhatsNew(BuildContext context, {String? version}) {
  final prefs = AppScope.of(context).prefs;
  final v = version ?? appVersion;
  prefs.lastSeenVersion = appVersion;
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _WhatsNew(version: v),
  );
}

class _WhatsNew extends StatelessWidget {
  const _WhatsNew({required this.version});
  final String version;

  @override
  Widget build(BuildContext context) {
    final locale = AppScope.of(context).prefs.locale;
    final items = newsFor(version);
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.8,
      maxChildSize: 0.95,
      builder: (context, controller) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Image.asset('assets/icon.png', width: 40, height: 40),
            const SizedBox(width: 12),
            Expanded(
              child: Text(context.t('whats_new_title', {'v': version}), style: Theme.of(context).textTheme.titleLarge),
            ),
          ]),
          const SizedBox(height: 12),
          Expanded(
            child: ListView(controller: controller, children: [
              for (final n in items)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: CircleAvatar(
                    backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                    child: Icon(n.icon, color: Theme.of(context).colorScheme.onPrimaryContainer),
                  ),
                  title: Text(n.title(locale)),
                  subtitle: Text(n.text(locale)),
                ),
              if (items.isEmpty) Text(context.t('update_no_notes')),
            ]),
          ),
          SizedBox(
            width: double.infinity,
            child: FilledButton(onPressed: () => Navigator.pop(context), child: Text(context.t('got_it'))),
          ),
        ]),
      ),
    );
  }
}
