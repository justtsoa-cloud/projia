// Sélecteur de modèle (F8) : « Auto » par défaut, ou un modèle précis pour la
// conversation, toujours, ou une catégorie. Recherche, filtres et score affichés.

import 'package:flutter/material.dart';

import '../core/chat_controller.dart';
import '../main.dart';

class ModelChip extends StatelessWidget {
  const ModelChip({super.key, required this.chat});
  final ChatController chat;

  @override
  Widget build(BuildContext context) {
    final label = chat.modelOverride == null ? context.t('auto') : chat.modelOverride!.split(':').last.split('/').last;
    return ActionChip(
      avatar: Icon(chat.modelOverride == null ? Icons.auto_awesome : Icons.push_pin_outlined, size: 16),
      label: Text('$label ▾', style: const TextStyle(fontSize: 12)),
      visualDensity: VisualDensity.compact,
      tooltip: context.t('model_picker'),
      onPressed: () => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (_) => ModelPicker(chat: chat),
      ),
    );
  }
}

class ModelPicker extends StatefulWidget {
  const ModelPicker({super.key, required this.chat});
  final ChatController chat;

  @override
  State<ModelPicker> createState() => _ModelPickerState();
}

class _ModelPickerState extends State<ModelPicker> {
  List<Map<String, dynamic>> models = [];
  String query = '';
  String category = 'chat';
  bool freeOnly = true;
  bool tools = false;
  bool loading = true;
  String scope = 'conversation';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    final b = AppScope.of(context).backend;
    try {
      final data = await b.getJson('/tontolo/catalog', {
        'category': category, 'free': freeOnly, 'usable': true, 'limit': 200,
        if (query.isNotEmpty) 'q': query,
      }) as Map<String, dynamic>;
      models = (data['models'] as List).cast<Map<String, dynamic>>();
      if (tools) models = models.where((m) => m['tools'] == true).toList();
    } catch (_) {
      models = [];
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _choose(String? key) async {
    final b = AppScope.of(context).backend;
    final chat = widget.chat;
    if (scope == 'conversation') {
      chat.modelOverride = key;
      if (chat.conversationId != null) {
        await b.sendJson('PUT', '/tontolo/preferences',
            {'scope': 'conversation', 'scope_key': chat.conversationId, 'model': key ?? 'auto'});
      }
    } else {
      chat.modelOverride = null;
      await b.sendJson('PUT', '/tontolo/preferences', {
        'scope': scope, 'scope_key': scope == 'category' ? category : '', 'model': key ?? 'auto',
      });
    }
    chat.refresh();
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.75,
      builder: (context, controller) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(children: [
          Row(children: [
            Expanded(child: Text(context.t('model_picker'), style: Theme.of(context).textTheme.titleLarge)),
            TextButton.icon(
              icon: const Icon(Icons.auto_awesome),
              label: Text(context.t('back_to_auto')),
              onPressed: () => _choose(null),
            ),
          ]),
          const SizedBox(height: 8),
          TextField(
            decoration: InputDecoration(prefixIcon: const Icon(Icons.search), hintText: context.t('search')),
            onChanged: (v) {
              query = v;
              _load();
            },
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              FilterChip(label: Text(context.t('free_only')), selected: freeOnly, onSelected: (v) { freeOnly = v; _load(); }),
              const SizedBox(width: 6),
              for (final (cat, key) in [('code', 'filter_code'), ('vision', 'filter_vision')])
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: FilterChip(label: Text(context.t(key)), selected: category == cat,
                      onSelected: (v) { category = v ? cat : 'chat'; _load(); }),
                ),
              FilterChip(label: Text(context.t('filter_tools')), selected: tools, onSelected: (v) { tools = v; _load(); }),
            ]),
          ),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            segments: [
              ButtonSegment(value: 'conversation', label: Text(context.t('scope_conv'))),
              ButtonSegment(value: 'global', label: Text(context.t('scope_global'))),
              ButtonSegment(value: 'category', label: Text(context.t('scope_cat'))),
            ],
            selected: {scope},
            onSelectionChanged: (s) => setState(() => scope = s.first),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : models.isEmpty
                    ? Center(child: Text(context.t('no_results')))
                    : ListView.builder(
                        controller: controller,
                        itemCount: models.length,
                        itemBuilder: (context, i) {
                          final m = models[i];
                          final q = ((m['quality'] as Map?)?[category] as num?)?.toDouble() ?? 0;
                          return ListTile(
                            title: Text('${m['name']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                            subtitle: Text([
                              '${m['provider']}',
                              if (m['free'] == true) 'gratuit',
                              if (m['tools'] == true) 'outils',
                              if (m['vision'] == true) 'vision',
                              if ((m['context'] as num? ?? 0) > 0) '${((m['context'] as num) / 1000).round()}k',
                              if (m['provisional'] == true) 'provisoire',
                            ].join(' · ')),
                            trailing: Text(q.toStringAsFixed(2)),
                            selected: widget.chat.modelOverride == m['key'],
                            onTap: () => _choose('${m['key']}'),
                          );
                        },
                      ),
          ),
        ]),
      ),
    );
  }
}
