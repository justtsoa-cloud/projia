// Recherche globale (Ctrl+K) : conversations et créations.

import 'package:flutter/material.dart';

import '../main.dart';

Future<void> showSearchDialog(BuildContext context) => showDialog<void>(
      context: context,
      builder: (_) => const _SearchDialog(),
    );

class _SearchDialog extends StatefulWidget {
  const _SearchDialog();

  @override
  State<_SearchDialog> createState() => _SearchDialogState();
}

class _SearchDialogState extends State<_SearchDialog> {
  List<Map<String, dynamic>> convs = [];
  List<Map<String, dynamic>> jobs = [];
  String filter = 'all';

  Future<void> _search(String q) async {
    final b = AppScope.of(context).backend;
    if (q.trim().isEmpty) {
      setState(() { convs = []; jobs = []; });
      return;
    }
    final c = await b.getJson('/projia/conversations', {'q': q, 'limit': 30}) as List;
    final j = await b.getJson('/projia/media', {'limit': 200}) as List;
    final ql = q.toLowerCase();
    if (!mounted) return;
    setState(() {
      convs = c.cast<Map<String, dynamic>>();
      jobs = j.cast<Map<String, dynamic>>().where((x) => '${x['prompt']}'.toLowerCase().contains(ql)).toList();
    });
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 600, maxHeight: 560),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(children: [
            TextField(
              autofocus: true,
              decoration: InputDecoration(prefixIcon: const Icon(Icons.search), hintText: context.t('search')),
              onChanged: _search,
            ),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: [
                ButtonSegment(value: 'all', label: Text(context.t('f_all'))),
                ButtonSegment(value: 'chat', label: Text(context.t('chat'))),
                ButtonSegment(value: 'media', label: Text(context.t('creations'))),
              ],
              selected: {filter},
              onSelectionChanged: (s) => setState(() => filter = s.first),
            ),
            Expanded(
              child: ListView(children: [
                if (filter != 'media')
                  for (final c in convs)
                    ListTile(
                      leading: const Icon(Icons.chat_bubble_outline),
                      title: Text('${c['title']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: (c['snippet'] ?? '').toString().isEmpty
                          ? null
                          : Text('${c['snippet']}', maxLines: 2, overflow: TextOverflow.ellipsis),
                      onTap: () {
                        scope.chat.open('${c['id']}');
                        Navigator.pop(context);
                      },
                    ),
                if (filter != 'chat')
                  for (final j in jobs)
                    ListTile(
                      leading: const Icon(Icons.photo_outlined),
                      title: Text('${j['prompt']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text('${j['kind']} · ${j['status']}'),
                    ),
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}
