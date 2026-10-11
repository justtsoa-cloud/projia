// Résultats intermédiaires d'une tâche complexe (parties rédigées en parallèle, étapes,
// sorties d'outils longues, brouillons de fichiers) : gardés 7 jours sur l'appareil et
// synchronisés avec les autres appareils.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../main.dart';
import 'message_view.dart' show RichMarkdown;

IconData _icon(String kind) => switch (kind) {
      'part' => Icons.call_split,
      'step' => Icons.format_list_numbered,
      'tool' => Icons.build_outlined,
      _ => Icons.description_outlined,
    };

Future<void> showTaskResults(BuildContext context, String conversationId) => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        builder: (context, controller) => _TaskResults(conversationId: conversationId, controller: controller),
      ),
    );

class _TaskResults extends StatefulWidget {
  const _TaskResults({required this.conversationId, required this.controller});
  final String conversationId;
  final ScrollController controller;

  @override
  State<_TaskResults> createState() => _TaskResultsState();
}

class _TaskResultsState extends State<_TaskResults> {
  List<Map<String, dynamic>>? items;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (items == null) _load();
  }

  Future<void> _load() async {
    try {
      final r = await AppScope.of(context).backend.getJson('/tontolo/conversations/${widget.conversationId}/tasks') as List;
      if (mounted) setState(() => items = r.cast<Map<String, dynamic>>().reversed.toList());
    } catch (_) {
      if (mounted) setState(() => items = []);
    }
  }

  Future<void> _open(Map<String, dynamic> item) async {
    final backend = AppScope.of(context).backend;
    final data = await backend.getJson('/tontolo/conversations/${widget.conversationId}/tasks/${item['id']}') as Map<String, dynamic>;
    if (!mounted) return;
    final text = '${data['content'] ?? ''}';
    final prose = item['kind'] == 'part' || item['kind'] == 'step';
    await Navigator.push(context, MaterialPageRoute<void>(
      builder: (context) => Scaffold(
        appBar: AppBar(title: Text('${item['title']}'), actions: [
          IconButton(
            icon: const Icon(Icons.copy),
            tooltip: context.t('copy'),
            onPressed: () => Clipboard.setData(ClipboardData(text: text)),
          ),
        ]),
        body: SafeArea(
          child: ListView(padding: const EdgeInsets.all(16), children: [
            if (prose)
              RichMarkdown(text)
            else
              SelectableText(text, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
          ]),
        ),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final list = items;
    final small = Theme.of(context).textTheme.bodySmall;
    return ListView(controller: widget.controller, padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
      Text(context.t('task_results'), style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 4),
      Text(context.t('task_results_help'), style: small),
      const SizedBox(height: 8),
      if (list == null)
        const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
      else if (list.isEmpty)
        Padding(padding: const EdgeInsets.all(16), child: Text(context.t('task_results_none')))
      else
        for (final it in list)
          ListTile(
            leading: Icon(_icon('${it['kind']}')),
            title: Text('${it['title']}', maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: Text('${context.t('task_kind_${it['kind']}')} · ${((it['size'] as num? ?? 0) / 1024).toStringAsFixed(1)} Ko', style: small),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _open(it),
          ),
    ]);
  }
}
