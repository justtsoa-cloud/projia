// État des modèles gratuits : prêts, en pause (avec l'heure de retour) ou épuisés pour la
// journée. Rend visible ce que fait la bascule automatique.

import 'package:flutter/material.dart';

import '../main.dart';
import 'model_picker.dart' show ModelHealth;

class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});

  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> {
  List<Map<String, dynamic>>? models;
  ModelHealth? health;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (models == null) _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    final h = await ModelHealth.fetch(context);
    try {
      final data = await b.getJson('/projia/catalog', {'free': true, 'usable': true, 'limit': 400}) as Map<String, dynamic>;
      final all = (data['models'] as List).cast<Map<String, dynamic>>();
      if (!mounted) return;
      setState(() {
        models = all;
        health = h;
      });
    } catch (_) {
      if (mounted) setState(() => models = []);
    }
  }

  String _reason(BuildContext context, String? r) => switch (r) {
        'rate_limit' => context.t('why_rate_limit'),
        'quota' => context.t('why_quota'),
        'auth' => context.t('why_auth'),
        'unavailable' => context.t('why_unavailable'),
        'server' => context.t('why_server'),
        'network' => context.t('why_network'),
        _ => '',
      };

  String _time(num at) {
    final d = DateTime.fromMillisecondsSinceEpoch((at * 1000).round());
    final now = DateTime.now();
    final hm = '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    return d.day == now.day ? hm : '${d.day}/${d.month} $hm';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final list = models;
    final ready = <Map<String, dynamic>>[], paused = <Map<String, dynamic>>[], out = <Map<String, dynamic>>[];
    for (final m in list ?? const <Map<String, dynamic>>[]) {
      if ((m['available_at'] as num? ?? 0) == 0) {
        ready.add(m);
      } else if (m['status'] == 'exhausted_daily') {
        out.add(m);
      } else {
        paused.add(m);
      }
    }
    Widget section(String title, Color color, List<Map<String, dynamic>> items, {bool showTime = false}) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
              child: Row(children: [
                Icon(Icons.circle, size: 10, color: color),
                const SizedBox(width: 8),
                Text('$title · ${items.length}', style: Theme.of(context).textTheme.titleSmall),
              ]),
            ),
            for (final m in items)
              ListTile(
                dense: true,
                leading: Icon(_icon(m), size: 20, color: scheme.onSurfaceVariant),
                title: Text('${m['name']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                subtitle: Text([
                  '${m['provider']}',
                  if (showTime) context.t('back_at', {'t': _time(m['available_at'] as num)}),
                  if (showTime && _reason(context, m['wait_reason'] as String?).isNotEmpty)
                    _reason(context, m['wait_reason'] as String?),
                ].join(' · ')),
              ),
          ],
        );
    return Scaffold(
      appBar: AppBar(title: Text(context.t('model_status'))),
      body: list == null
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(children: [
                if (health != null)
                  Card(
                    margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                    child: ListTile(
                      leading: Icon(Icons.circle, color: health!.color(scheme)),
                      title: Text(health!.describe(context)),
                      subtitle: Text(context.t('status_help')),
                    ),
                  ),
                section(context.t('st_ready'), const Color(0xFF2E9E6B), ready),
                if (paused.isNotEmpty) section(context.t('st_paused'), const Color(0xFFE59A1F), paused, showTime: true),
                if (out.isNotEmpty) section(context.t('st_out'), scheme.error, out, showTime: true),
                const SizedBox(height: 24),
              ]),
            ),
    );
  }

  IconData _icon(Map<String, dynamic> m) {
    final media = (m['media'] as List? ?? const []).cast<String>();
    if (media.contains('video_gen')) return Icons.movie_outlined;
    if (media.contains('image_gen') || media.contains('image_edit')) return Icons.image_outlined;
    if (media.contains('tts') || media.contains('stt') || media.contains('music_sfx')) return Icons.graphic_eq;
    return Icons.chat_bubble_outline;
  }
}
