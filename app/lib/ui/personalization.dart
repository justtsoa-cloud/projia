// Personnalisation : instructions personnalisées, mémoire à long terme, vitesse de lecture.

import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../core/backend.dart';
import '../main.dart';

/// Réglages simples, en groupes titrés : Vous, Réponses, Mémoire, Espace de travail, Voix.
class PersonalizationSection extends StatefulWidget {
  const PersonalizationSection({super.key, required this.header});

  /// Titre de groupe, au style de l'écran des réglages.
  final Widget Function(String title) header;

  @override
  State<PersonalizationSection> createState() => _PersonalizationSectionState();
}

class _PersonalizationSectionState extends State<PersonalizationSection> {
  final instructions = TextEditingController();
  final userName = TextEditingController();
  List<Map<String, dynamic>> memories = [];
  bool enabled = true;
  bool speedFirst = false;
  bool economy = false;
  bool teamReview = true;
  bool autoCompact = true;
  bool taskPlanning = true;
  bool orchestrate = false;
  bool answerCache = true;
  int answers = 0; // réponses déjà données gardées sur l'appareil
  Map<String, dynamic>? workspace; // bureau Linux : dossier de travail de l'agent
  bool loaded = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!loaded) _load();
  }

  @override
  void dispose() {
    instructions.dispose();
    userName.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    final local = AppScope.of(context).prefs.remoteUrl.isEmpty;
    if (b.state != BackendState.ready) return;
    final s = await b.getJson('/tontolo/settings') as Map<String, dynamic>;
    final m = await b.getJson('/tontolo/memory') as Map<String, dynamic>;
    Map<String, dynamic>? ans;
    try {
      ans = await b.getJson('/tontolo/answers') as Map<String, dynamic>;
    } catch (_) {} // ancien cœur : pas de cache de réponses
    Map<String, dynamic>? ws;
    if (Platform.isLinux && local) {
      try {
        ws = await b.getJson('/tontolo/workspace') as Map<String, dynamic>;
      } catch (_) {} // ancien cœur : pas d'espace de travail
    }
    if (!mounted) return;
    setState(() {
      loaded = true;
      instructions.text = '${s['custom_instructions'] ?? ''}';
      userName.text = '${s['user_name'] ?? ''}';
      enabled = m['enabled'] == true;
      speedFirst = s['speed_first'] == true;
      economy = s['economy'] == true;
      teamReview = s['team_review'] != false; // absent (ancien cœur) : affiché actif
      autoCompact = s['auto_compact'] != false;
      taskPlanning = s['task_planning'] != false;
      orchestrate = s['orchestrate'] == true;
      answerCache = ans != null && ans['enabled'] == true;
      answers = (ans?['count'] as int?) ?? -1;
      memories = (m['items'] as List).cast<Map<String, dynamic>>();
      workspace = ws;
    });
  }

  Future<void> _pickWorkspace() async {
    final messenger = ScaffoldMessenger.of(context);
    final dir = await FilePicker.getDirectoryPath();
    if (dir == null || !mounted) return;
    try {
      await AppScope.of(context).backend.sendJson('PUT', '/tontolo/workspace', {'path': dir});
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('$e')));
    }
    await _load();
  }

  Future<void> _call(String method, String path, [Object? body]) async {
    await AppScope.of(context).backend.sendJson(method, path, body);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final prefs = AppScope.of(context).prefs;
    final small = Theme.of(context).textTheme.bodySmall;
    // Tâches en plusieurs parties : un seul choix lisible au lieu de deux interrupteurs.
    final tasks = orchestrate ? 'multi' : taskPlanning ? 'plan' : 'off';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      widget.header(context.t('group_you')),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
        child: TextField(
          controller: userName,
          maxLength: 40,
          textCapitalization: TextCapitalization.words,
          decoration: InputDecoration(labelText: context.t('user_name'), helperText: context.t('user_name_help'), helperMaxLines: 2),
          onEditingComplete: () => _call('PUT', '/tontolo/settings', {'user_name': userName.text.trim()}),
          onTapOutside: (_) {
            FocusScope.of(context).unfocus();
            _call('PUT', '/tontolo/settings', {'user_name': userName.text.trim()});
          },
        ),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: TextField(
          controller: instructions,
          minLines: 2,
          maxLines: 5,
          maxLength: 2000,
          decoration: InputDecoration(labelText: context.t('instructions'), hintText: context.t('instructions_hint')),
          onEditingComplete: () => _call('PUT', '/tontolo/settings', {'custom_instructions': instructions.text}),
          onTapOutside: (_) {
            FocusScope.of(context).unfocus();
            _call('PUT', '/tontolo/settings', {'custom_instructions': instructions.text});
          },
        ),
      ),
      widget.header(context.t('group_answers')),
      SwitchListTile(
        secondary: const Icon(Icons.bolt_outlined),
        title: Text(context.t('speed_first')),
        subtitle: Text(context.t('speed_first_help'), style: small),
        value: speedFirst,
        onChanged: (v) {
          setState(() => speedFirst = v);
          _call('PUT', '/tontolo/settings', {'speed_first': v});
        },
      ),
      SwitchListTile(
        secondary: const Icon(Icons.battery_saver_outlined),
        title: Text(context.t('economy')),
        subtitle: Text(context.t('economy_help'), style: small),
        value: economy,
        onChanged: (v) {
          setState(() => economy = v);
          _call('PUT', '/tontolo/settings', {'economy': v});
        },
      ),
      SwitchListTile(
        secondary: const Icon(Icons.groups_outlined),
        title: Text(context.t('team_review')),
        subtitle: Text(context.t('team_review_help'), style: small),
        value: teamReview,
        onChanged: (v) {
          setState(() => teamReview = v);
          _call('PUT', '/tontolo/settings', {'team_review': v});
        },
      ),
      SwitchListTile(
        secondary: const Icon(Icons.compress),
        title: Text(context.t('auto_compact')),
        subtitle: Text(context.t('auto_compact_help'), style: small),
        value: autoCompact,
        onChanged: (v) {
          setState(() => autoCompact = v);
          _call('PUT', '/tontolo/settings', {'auto_compact': v});
        },
      ),
      ListTile(
        leading: const Icon(Icons.account_tree_outlined),
        title: Text(context.t('tasks_mode')),
        subtitle: Text(context.t('tasks_${tasks}_help'), style: small),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
        child: SegmentedButton<String>(
          showSelectedIcon: false,
          segments: [
            ButtonSegment(value: 'off', label: Text(context.t('tasks_off'))),
            ButtonSegment(value: 'plan', label: Text(context.t('tasks_plan'))),
            ButtonSegment(value: 'multi', label: Text(context.t('tasks_multi'))),
          ],
          selected: {tasks},
          onSelectionChanged: (v) {
            final m = v.first;
            setState(() {
              taskPlanning = m != 'off';
              orchestrate = m == 'multi';
            });
            _call('PUT', '/tontolo/settings', {'task_planning': m != 'off', 'orchestrate': m == 'multi'});
          },
        ),
      ),
      if (workspace != null) ...[
        widget.header(context.t('workspace')),
        ListTile(
          leading: const Icon(Icons.folder_special_outlined),
          title: Text(context.t('workspace')),
          subtitle: Text(workspace!['path'] == null
              ? context.t('workspace_none')
              : '${workspace!['path']}\n${context.t('workspace_help')}', style: small),
          isThreeLine: workspace!['path'] != null,
          trailing: workspace!['path'] == null
              ? FilledButton.tonal(onPressed: _pickWorkspace, child: Text(context.t('workspace_choose')))
              : IconButton(
                  icon: const Icon(Icons.close),
                  tooltip: context.t('workspace_clear'),
                  onPressed: () => _call('PUT', '/tontolo/workspace', {'path': null}),
                ),
          onTap: _pickWorkspace,
        ),
        if ((workspace!['history'] as List? ?? const []).isNotEmpty)
          ListTile(
            dense: true,
            leading: const SizedBox(width: 24),
            title: Text(context.t('workspace_last', {
              'f': '${(workspace!['history'] as List).first['rel']}',
              'a': '${(workspace!['history'] as List).first['action']}',
            })),
            trailing: TextButton.icon(
              icon: const Icon(Icons.undo, size: 18),
              label: Text(context.t('workspace_undo')),
              onPressed: () => _call('POST', '/tontolo/workspace/undo'),
            ),
          ),
      ],
      widget.header(context.t('memory')),
      SwitchListTile(
        secondary: const Icon(Icons.psychology_outlined),
        title: Text(context.t('memory')),
        subtitle: Text(context.t('memory_help'), style: small),
        value: enabled,
        onChanged: (v) => _call('PUT', '/tontolo/settings', {'memory_enabled': v}),
      ),
      if (enabled) ...[
        if (memories.isEmpty)
          Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(context.t('memory_empty'), style: small)),
        for (final m in memories)
          ListTile(
            dense: true,
            leading: Icon(m['kind'] == 'instruction' ? Icons.rule : Icons.bookmark_outline, size: 18),
            title: Text('${m['text']}'),
            trailing: IconButton(
              icon: const Icon(Icons.close, size: 18),
              tooltip: context.t('delete'),
              onPressed: () => _call('DELETE', '/tontolo/memory/${m['id']}'),
            ),
          ),
        if (memories.isNotEmpty)
          OverflowBar(alignment: MainAxisAlignment.end, children: [
            TextButton(onPressed: () => _call('POST', '/tontolo/memory/compact'), child: Text(context.t('memory_compact'))),
            TextButton(
              onPressed: () => _call('DELETE', '/tontolo/memory'),
              child: Text(context.t('memory_clear'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          ]),
      ],
      if (answers >= 0)
        SwitchListTile(
          secondary: const Icon(Icons.history),
          title: Text(context.t('answer_cache')),
          subtitle: Text(context.t('answer_cache_help', {'n': '$answers'}), style: small),
          value: answerCache,
          onChanged: (v) => _call('PUT', '/tontolo/settings', {'answer_cache': v}),
        ),
      if (answers > 0)
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            onPressed: () => _call('DELETE', '/tontolo/answers'),
            child: Text(context.t('answer_cache_clear'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        ),
      widget.header(context.t('group_voice')),
      ListenableBuilder(
        listenable: prefs,
        builder: (context, _) => ListTile(
          leading: const Icon(Icons.record_voice_over_outlined),
          title: Text(context.t('speech_rate')),
          subtitle: Slider(
            value: prefs.speechRate, min: 0.3, max: 0.8, divisions: 10,
            label: '×${(prefs.speechRate * 2).toStringAsFixed(1)}',
            onChanged: (v) => prefs.speechRate = v,
          ),
        ),
      ),
    ]);
  }
}
