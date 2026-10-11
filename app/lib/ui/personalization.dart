// Personnalisation : instructions personnalisées, mémoire à long terme, vitesse de lecture.

import 'package:flutter/material.dart';

import '../core/backend.dart';
import '../main.dart';

class PersonalizationSection extends StatefulWidget {
  const PersonalizationSection({super.key});

  @override
  State<PersonalizationSection> createState() => _PersonalizationSectionState();
}

class _PersonalizationSectionState extends State<PersonalizationSection> {
  final instructions = TextEditingController();
  List<Map<String, dynamic>> memories = [];
  bool enabled = true;
  bool speedFirst = false;
  bool teamReview = true;
  bool loaded = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!loaded) _load();
  }

  @override
  void dispose() {
    instructions.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final s = await b.getJson('/tontolo/settings') as Map<String, dynamic>;
    final m = await b.getJson('/tontolo/memory') as Map<String, dynamic>;
    if (!mounted) return;
    setState(() {
      loaded = true;
      instructions.text = '${s['custom_instructions'] ?? ''}';
      enabled = m['enabled'] == true;
      speedFirst = s['speed_first'] == true;
      teamReview = s['team_review'] != false; // absent (ancien cœur) : affiché actif
      memories = (m['items'] as List).cast<Map<String, dynamic>>();
    });
  }

  Future<void> _call(String method, String path, [Object? body]) async {
    await AppScope.of(context).backend.sendJson(method, path, body);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final prefs = AppScope.of(context).prefs;
    final small = Theme.of(context).textTheme.bodySmall;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
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
      ListenableBuilder(
        listenable: prefs,
        builder: (context, _) => ListTile(
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
