// Galerie « Créations » (images, sons, vidéos) et fil « Nouveautés ».

import 'dart:async';

import 'package:flutter/material.dart';

import '../core/backend.dart';
import '../main.dart';
import 'message_view.dart';

class CreationsScreen extends StatelessWidget {
  const CreationsScreen({super.key});

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 2,
        child: Scaffold(
          appBar: AppBar(
            leading: ShellNav.maybeOf(context)?.backButton(context),
            title: Text(context.t('creations')),
            bottom: TabBar(tabs: [Tab(text: context.t('creations')), Tab(text: context.t('news'))]),
          ),
          body: const TabBarView(children: [_Gallery(), NewsFeed()]),
        ),
      );
}

class _Gallery extends StatefulWidget {
  const _Gallery();

  @override
  State<_Gallery> createState() => _GalleryState();
}

class _GalleryState extends State<_Gallery> {
  List<Map<String, dynamic>> jobs = [];
  String? kind;
  bool loading = true;
  Timer? _poll;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final data = await b.getJson('/tontolo/media', {'limit': 200, if (kind != null) 'kind': kind}) as List;
    if (!mounted) return;
    setState(() {
      jobs = data.cast<Map<String, dynamic>>();
      loading = false;
    });
    // Jobs en cours : rafraîchissement léger tant qu'il y en a (pas de sondage permanent).
    _poll?.cancel();
    if (jobs.any((j) => j['status'] == 'queued' || j['status'] == 'running')) {
      _poll = Timer(const Duration(seconds: 3), _load);
    }
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    return Column(children: [
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.all(8),
        child: Row(children: [
          for (final (k, label) in [(null, 'Tout'), ('image_gen', 'Images'), ('tts', 'Voix'), ('stt', 'Transcriptions'), ('video_gen', 'Vidéos')])
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: ChoiceChip(label: Text(label), selected: kind == k, onSelected: (_) { kind = k; _load(); }),
            ),
        ]),
      ),
      Expanded(
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : jobs.isEmpty
                ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(context.t('empty_creations'), textAlign: TextAlign.center)))
                : GridView.builder(
                    padding: const EdgeInsets.all(8),
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: (width / 260).floor().clamp(1, 6), childAspectRatio: 0.8,
                      crossAxisSpacing: 8, mainAxisSpacing: 8),
                    itemCount: jobs.length,
                    itemBuilder: (context, i) {
                      final j = jobs[i];
                      return Card(
                        clipBehavior: Clip.antiAlias,
                        child: Padding(
                          padding: const EdgeInsets.all(8),
                          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Expanded(child: SingleChildScrollView(child: MediaResult(job: j))),
                            Text('${j['prompt']}', maxLines: 2, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
                            Row(children: [
                              Expanded(child: Text('${(j['params'] as Map?)?['model_name'] ?? j['model'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.labelSmall)),
                              IconButton(
                                icon: const Icon(Icons.delete_outline, size: 18),
                                tooltip: context.t('delete'),
                                onPressed: () async {
                                  await AppScope.of(context).backend.sendJson('DELETE', '/tontolo/media/${j['id']}');
                                  _load();
                                },
                              ),
                            ]),
                          ]),
                        ),
                      );
                    },
                  ),
      ),
    ]);
  }
}

/// Fil daté des changements du catalogue (nouveau modèle gratuit, nouveau n°1…).
class NewsFeed extends StatefulWidget {
  const NewsFeed({super.key});

  @override
  State<NewsFeed> createState() => _NewsFeedState();
}

class _NewsFeedState extends State<NewsFeed> {
  List<Map<String, dynamic>> items = [];

  static const labels = {
    'new_free': ('Nouveau modèle gratuit', Icons.celebration_outlined),
    'became_free': ('Devenu gratuit', Icons.savings_outlined),
    'new_top': ('Nouveau n°1', Icons.emoji_events_outlined),
    'removed': ('Retiré', Icons.remove_circle_outline),
    'no_longer_free': ('N\'est plus gratuit', Icons.money_off),
    'new': ('Nouveau modèle', Icons.fiber_new_outlined),
    'price_changed': ('Prix modifié', Icons.price_change_outlined),
    'capabilities_changed': ('Capacités modifiées', Icons.tune),
  };

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final data = await b.getJson('/tontolo/changes', {'limit': 200}) as List;
    await b.sendJson('POST', '/tontolo/changes/seen');
    if (mounted) {
      setState(() => items = data.cast<Map<String, dynamic>>().where((c) => c['kind'] != 'new' && c['kind'] != 'price_changed').toList());
    }
  }

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(context.t('empty_news'), textAlign: TextAlign.center)));
    }
    return RefreshIndicator(
      onRefresh: () async {
        await AppScope.of(context).backend.sendJson('POST', '/tontolo/catalog/refresh');
        await _load();
      },
      child: ListView.builder(
        itemCount: items.length,
        itemBuilder: (context, i) {
          final c = items[i];
          final (label, icon) = labels[c['kind']] ?? ('${c['kind']}', Icons.info_outline);
          final detail = (c['detail'] as Map?) ?? {};
          final date = DateTime.fromMillisecondsSinceEpoch(((c['ts'] as num) * 1000).round());
          return ListTile(
            leading: Icon(icon),
            title: Text('$label${detail['category'] != null ? ' (${detail['category']})' : ''}'),
            subtitle: Text('${detail['name'] ?? c['model_id']}'),
            trailing: Text('${date.day.toString().padLeft(2, '0')}/${date.month.toString().padLeft(2, '0')}'),
          );
        },
      ),
    );
  }
}
