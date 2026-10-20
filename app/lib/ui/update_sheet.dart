// Annonce de mise à jour (résumé des changements) et présentation des nouveautés
// après installation. Visibles dès l'ouverture, sans passer par les réglages avancés.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../core/author.dart';
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
                        const _AuthorLine(),
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
/// `since` : dernière version vue ; toutes les nouveautés intermédiaires sont présentées.
Future<void> showWhatsNew(BuildContext context, {String? version, String? since}) {
  final prefs = AppScope.of(context).prefs;
  final v = version ?? appVersion;
  prefs.lastSeenVersion = appVersion;
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _WhatsNew(version: v, since: since),
  );
}

class _WhatsNew extends StatelessWidget {
  const _WhatsNew({required this.version, this.since});
  final String version;
  final String? since;

  @override
  Widget build(BuildContext context) {
    final locale = AppScope.of(context).prefs.locale;
    final groups = since == null ? [(version, newsFor(version))] : newsBetween(since!, version);
    final items = [for (final g in groups) ...g.$2];
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
              _PosterCard(version: version, locale: locale),
              for (final (v, group) in groups) ...[
                if (groups.length > 1)
                  Padding(
                    padding: const EdgeInsets.only(top: 12, bottom: 2),
                    child: Text('${context.t('version')} $v', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: Theme.of(context).colorScheme.primary)),
                  ),
                for (final n in group)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: CircleAvatar(
                    backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                    child: Icon(n.icon, color: Theme.of(context).colorScheme.onPrimaryContainer),
                  ),
                  title: Text(n.title(locale)),
                  subtitle: Text(n.text(locale)),
                ),
              ],
              if (items.isEmpty) Text(context.t('update_no_notes')),
              const _AuthorLine(),
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


/// Poster de la version (image illustrée : changement majeur en exemple d'usage). Une seule
/// affiche est embarquée : celle de la version installée ; absente, rien n'est affiché.
class _PosterCard extends StatefulWidget {
  const _PosterCard({required this.version, required this.locale});
  final String version;
  final String locale;

  @override
  State<_PosterCard> createState() => _PosterCardState();
}

class _PosterCardState extends State<_PosterCard> {
  bool? available;

  @override
  void initState() {
    super.initState();
    rootBundle.loadString('assets/posters/version.txt').then((v) {
      if (mounted) setState(() => available = v.trim() == widget.version);
    }).catchError((_) {
      if (mounted) setState(() => available = false);
    });
  }

  String get _asset => 'assets/posters/latest-${const ['fr', 'en', 'mg'].contains(widget.locale) ? widget.locale : 'fr'}.webp';

  @override
  Widget build(BuildContext context) {
    if (available != true) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Semantics(
        button: true,
        label: context.t('poster_open'),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: InkWell(
            onTap: () => Navigator.push(context, MaterialPageRoute<void>(
              builder: (_) => _PosterView(asset: _asset, version: widget.version),
            )),
            child: Image.asset(_asset, fit: BoxFit.fitWidth, gaplessPlayback: true),
          ),
        ),
      ),
    );
  }
}

class _PosterView extends StatelessWidget {
  const _PosterView({required this.asset, required this.version});
  final String asset;
  final String version;

  @override
  Widget build(BuildContext context) => Scaffold(
        backgroundColor: Colors.black,
        appBar: AppBar(
          backgroundColor: Colors.black,
          foregroundColor: Colors.white,
          title: Text('Projia $version'),
          actions: [
            IconButton(
              icon: const Icon(Icons.ios_share),
              tooltip: context.t('export'),
              onPressed: () async {
                final data = await rootBundle.load(asset);
                await SharePlus.instance.share(ShareParams(files: [
                  XFile.fromData(data.buffer.asUint8List(), mimeType: 'image/webp', name: 'Projia-$version-poster.webp'),
                ]));
              },
            ),
          ],
        ),
        body: InteractiveViewer(maxScale: 4, child: Center(child: Image.asset(asset))),
      );
}

/// Signature de l'auteur, présente dans chaque annonce de mise à jour et « Quoi de neuf ».
class _AuthorLine extends StatelessWidget {
  const _AuthorLine();

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 16, bottom: 4),
        child: Text(
          '${context.t('made_by')} $authorName · $authorGithub · $authorEmail · $authorPhone',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      );
}
