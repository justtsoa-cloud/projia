// Sélecteur de modèle (F8) : « Auto » par défaut, ou un modèle précis pour la
// conversation, toujours, ou une catégorie. Recherche, filtres et score affichés.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/backend.dart';

import '../core/chat_controller.dart';
import '../main.dart';
import 'status_screen.dart';

/// État global des modèles gratuits (pastille) : vert, orange ou rouge.
class ModelHealth {
  const ModelHealth(this.state, this.ready, this.best, this.retryAt, this.offline);
  final String state;
  final int ready;
  final String? best;
  final double? retryAt;
  final bool offline;

  static Future<ModelHealth?> fetch(BuildContext context) async {
    try {
      final h = await AppScope.of(context).backend.getJson('/tontolo/health') as Map<String, dynamic>;
      return ModelHealth('${h['state']}', (h['ready'] as num?)?.toInt() ?? 0, h['best'] as String?,
          (h['retry_at'] as num?)?.toDouble(), h['offline'] == true);
    } catch (_) {
      return null;
    }
  }

  Color color(ColorScheme scheme) => switch (state) {
        'green' => const Color(0xFF2E9E6B),
        'orange' => const Color(0xFFE59A1F),
        _ => scheme.error,
      };

  String describe(BuildContext context) {
    if (offline) return context.t('health_offline');
    if (ready == 0) {
      final at = retryAt == null ? null : DateTime.fromMillisecondsSinceEpoch((retryAt! * 1000).round());
      return at == null
          ? context.t('health_none')
          : context.t('health_none_until', {'t': '${at.hour.toString().padLeft(2, '0')}:${at.minute.toString().padLeft(2, '0')}'});
    }
    return context.t('health_ready', {'n': '$ready', 'best': best ?? '—'});
  }
}

class ModelChip extends StatefulWidget {
  const ModelChip({super.key, required this.chat});
  final ChatController chat;

  @override
  State<ModelChip> createState() => _ModelChipState();
}

class _ModelChipState extends State<ModelChip> {
  ModelHealth? health;
  Timer? _timer;
  bool _wasBusy = false;
  Backend? _backend;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _backend ??= AppScope.of(context).backend..addListener(_onBackend);
  }

  void _onBackend() {
    if (_backend?.state == BackendState.ready && health == null) _refresh();
  }

  @override
  void initState() {
    super.initState();
    widget.chat.addListener(_onChat);
    _timer = Timer.periodic(const Duration(seconds: 45), (_) => _refresh());
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  @override
  void dispose() {
    widget.chat.removeListener(_onChat);
    _backend?.removeListener(_onBackend);
    _timer?.cancel();
    super.dispose();
  }

  void _onChat() {
    // Après chaque réponse, l'état des quotas a pu changer.
    if (_wasBusy && !widget.chat.busy) _refresh();
    _wasBusy = widget.chat.busy;
  }

  Future<void> _refresh() async {
    if (!mounted || AppScope.of(context).backend.state != BackendState.ready) return;
    final h = await ModelHealth.fetch(context);
    if (mounted && h != null) setState(() => health = h);
  }

  void _openPicker() => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (_) => ModelPicker(chat: widget.chat, health: health),
      ).then((_) => _refresh());

  @override
  Widget build(BuildContext context) {
    final chat = widget.chat;
    final scheme = Theme.of(context).colorScheme;
    final label = chat.modelOverride == null ? context.t('auto') : chat.modelOverride!.split(':').last.split('/').last;
    final h = health;
    return Tooltip(
      message: h == null ? context.t('model_picker') : h.describe(context),
      child: GestureDetector(
        onLongPress: () {
          HapticFeedback.mediumImpact();
          showModalBottomSheet<void>(
            context: context,
            showDragHandle: true,
            builder: (_) => QuickModels(chat: chat),
          ).then((_) => _refresh());
        },
        child: ActionChip(
          avatar: Stack(clipBehavior: Clip.none, children: [
            Icon(chat.modelOverride == null ? Icons.auto_awesome : Icons.push_pin_outlined, size: 16),
            if (h != null)
              Positioned(
                right: -3,
                bottom: -3,
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: h.color(scheme),
                    shape: BoxShape.circle,
                    border: Border.all(color: scheme.surface, width: 1.5),
                  ),
                ),
              ),
          ]),
          label: Text('$label ▾', style: const TextStyle(fontSize: 12)),
          visualDensity: VisualDensity.compact,
          onPressed: _openPicker,
        ),
      ),
    );
  }
}

/// Appui long sur la pastille : les meilleurs modèles prêts, à fixer d'un geste.
class QuickModels extends StatefulWidget {
  const QuickModels({super.key, required this.chat});
  final ChatController chat;

  @override
  State<QuickModels> createState() => _QuickModelsState();
}

class _QuickModelsState extends State<QuickModels> {
  List<Map<String, dynamic>>? models;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (models == null) _load();
  }

  Future<void> _load() async {
    try {
      final data = await AppScope.of(context).backend.getJson('/tontolo/catalog',
          {'category': 'chat', 'free': true, 'usable': true, 'limit': 60}) as Map<String, dynamic>;
      final all = (data['models'] as List).cast<Map<String, dynamic>>()
          .where((m) => (m['media'] as List? ?? const []).isEmpty && (m['available_at'] as num? ?? 0) == 0)
          .toList()
        ..sort((a, b) => (((b['quality'] as Map?)?['chat'] as num?) ?? 0)
            .compareTo(((a['quality'] as Map?)?['chat'] as num?) ?? 0));
      if (mounted) setState(() => models = all.take(5).toList());
    } catch (_) {
      if (mounted) setState(() => models = []);
    }
  }

  Future<void> _pin(String? key) async {
    final chat = widget.chat;
    chat.modelOverride = key;
    if (chat.conversationId != null) {
      await AppScope.of(context).backend.sendJson('PUT', '/tontolo/preferences',
          {'scope': 'conversation', 'scope_key': chat.conversationId, 'model': key ?? 'auto'});
    }
    chat.refresh();
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final list = models;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 0, 8, 12),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(context.t('quick_models'), style: Theme.of(context).textTheme.titleMedium),
          ),
          ListTile(
            leading: const Icon(Icons.auto_awesome),
            title: Text(context.t('auto')),
            subtitle: Text(context.t('auto_sub')),
            selected: widget.chat.modelOverride == null,
            onTap: () => _pin(null),
          ),
          if (list == null)
            const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()))
          else
            for (final m in list)
              ListTile(
                leading: const Icon(Icons.push_pin_outlined),
                title: Text('${m['name']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: Text('${m['provider']}'),
                selected: widget.chat.modelOverride == m['key'],
                onTap: () => _pin('${m['key']}'),
              ),
        ]),
      ),
    );
  }
}

class ModelPicker extends StatefulWidget {
  const ModelPicker({super.key, required this.chat, this.health});
  final ChatController chat;
  final ModelHealth? health;

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
          if (widget.health != null)
            InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const StatusScreen())),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(children: [
                  Icon(Icons.circle, size: 10, color: widget.health!.color(Theme.of(context).colorScheme)),
                  const SizedBox(width: 8),
                  Expanded(child: Text(widget.health!.describe(context), style: Theme.of(context).textTheme.bodySmall)),
                  const Icon(Icons.chevron_right, size: 18),
                ]),
              ),
            ),
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
                          final waiting = (m['available_at'] as num? ?? 0) > 0;
                          return ListTile(
                            leading: Icon(Icons.circle, size: 10,
                                color: waiting ? const Color(0xFFE59A1F) : const Color(0xFF2E9E6B)),
                            minLeadingWidth: 10,
                            title: Text('${m['name']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                            subtitle: Text([
                              '${m['provider']}',
                              if (m['free'] == true) context.t('tag_free'),
                              if (m['tools'] == true) context.t('tag_tools'),
                              if (m['vision'] == true) context.t('tag_vision'),
                              if ((m['context'] as num? ?? 0) > 0) '${((m['context'] as num) / 1000).round()}k',
                              if (m['provisional'] == true) context.t('tag_provisional'),
                              if (waiting) context.t('model_waiting'),
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
