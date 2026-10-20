// Fiche détaillée d'un modèle (fournisseur, gratuit ou payant, contexte, capacités, scores,
// vitesse, état) et liste simple des générateurs d'images, de vidéos et de sons.

import 'package:flutter/material.dart';

import '../main.dart';

/// Badge « Agent » : le modèle sait utiliser des outils (recherche, fichiers, calcul…).
class AgentBadge extends StatelessWidget {
  const AgentBadge({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(color: scheme.secondaryContainer, borderRadius: BorderRadius.circular(8)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.smart_toy_outlined, size: 12, color: scheme.onSecondaryContainer),
        const SizedBox(width: 3),
        Text(context.t('tag_agent'), style: TextStyle(fontSize: 11, color: scheme.onSecondaryContainer)),
      ]),
    );
  }
}

Color statusColor(Map<String, dynamic> m, ColorScheme scheme) {
  if (m['usable'] == false) return scheme.outline;
  if ((m['available_at'] as num? ?? 0) > 0) return const Color(0xFFE59A1F);
  return const Color(0xFF2E9E6B);
}

String statusText(BuildContext context, Map<String, dynamic> m) {
  if (m['usable'] == false) return context.t('md_needs_key');
  final at = (m['available_at'] as num? ?? 0).toDouble();
  if (at > 0) {
    final t = DateTime.fromMillisecondsSinceEpoch((at * 1000).round());
    return context.t('md_waiting_until', {'t': '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}'});
  }
  return context.t('md_ready');
}

String _price(BuildContext context, Map<String, dynamic> m) {
  if (m['free'] == true) return context.t('tag_free');
  double per(Object? v) => ((v as num?)?.toDouble() ?? 0) * 1e6;
  return context.t('md_price', {'in': per(m['price_in']).toStringAsFixed(2), 'out': per(m['price_out']).toStringAsFixed(2)});
}

Future<void> showModelDetails(BuildContext context, Map<String, dynamic> m, {VoidCallback? onUse}) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        builder: (context, controller) => _ModelDetails(m: m, controller: controller, onUse: onUse),
      ),
    );

class _ModelDetails extends StatelessWidget {
  const _ModelDetails({required this.m, required this.controller, this.onUse});
  final Map<String, dynamic> m;
  final ScrollController controller;
  final VoidCallback? onUse;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final quality = ((m['quality'] as Map?) ?? const {}).cast<String, dynamic>().entries
        .where((e) => (e.value as num? ?? 0) > 0).toList()
      ..sort((a, b) => (b.value as num).compareTo(a.value as num));
    final ctx = (m['context'] as num? ?? 0).toInt();
    final maxOut = (m['max_output'] as num?)?.toInt();
    final speed = (m['speed'] as num?)?.toDouble();
    final inputs = ((m['inputs'] as List?) ?? const ['text']).map((e) => context.t('mod_$e')).join(', ');
    final outputs = ((m['outputs'] as List?) ?? const ['text']).map((e) => context.t('mod_$e')).join(', ');
    Widget row(IconData icon, String label, String value) => ListTile(
          dense: true,
          leading: Icon(icon, size: 20),
          title: Text(label),
          trailing: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 200),
            child: Text(value, textAlign: TextAlign.end, style: text.bodyMedium),
          ),
        );
    return ListView(controller: controller, padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
      Row(children: [
        Expanded(child: Text('${m['name']}', style: text.titleLarge)),
        if (m['agentic'] == true) const AgentBadge(),
      ]),
      const SizedBox(height: 2),
      SelectableText('${m['key']}', style: text.bodySmall),
      const SizedBox(height: 8),
      Row(children: [
        Icon(Icons.circle, size: 10, color: statusColor(m, scheme)),
        const SizedBox(width: 8),
        Expanded(child: Text(statusText(context, m))),
      ]),
      const Divider(),
      row(Icons.business_outlined, context.t('md_provider'), '${m['provider']}${(m['family'] ?? '') != '' ? ' · ${m['family']}' : ''}'),
      row(Icons.payments_outlined, context.t('md_cost'), _price(context, m)),
      if (ctx > 0) row(Icons.notes, context.t('md_context'), context.t('md_tokens', {'n': _k(ctx)})),
      if (maxOut != null && maxOut > 0) row(Icons.short_text, context.t('md_max_output'), context.t('md_tokens', {'n': _k(maxOut)})),
      row(Icons.input, context.t('md_inputs'), inputs),
      row(Icons.output, context.t('md_outputs'), outputs),
      row(Icons.smart_toy_outlined, context.t('md_tools'), context.t(m['tools'] == true ? 'yes' : 'no')),
      if (speed != null) row(Icons.speed, context.t('speed'), '${(speed * 100).round()} / 100'),
      if (m['rate_limit'] != null) row(Icons.timer_outlined, context.t('md_limits'), '${m['rate_limit']}'),
      if (m['provisional'] == true) row(Icons.science_outlined, context.t('md_provisional'), context.t('tag_provisional')),
      if (quality.isNotEmpty) ...[
        const Divider(),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Text(context.t('md_scores'), style: text.titleSmall),
        ),
        for (final e in quality.take(8))
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(children: [
              SizedBox(width: 130, child: Text(context.t('cat_${e.key}'), style: text.bodySmall)),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(value: (e.value as num).toDouble().clamp(0, 1), minHeight: 8),
                ),
              ),
              const SizedBox(width: 8),
              Text(((e.value as num) * 100).round().toString()),
            ]),
          ),
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(context.t('why_rankings'), style: text.bodySmall),
        ),
      ],
      if (onUse != null) ...[
        const SizedBox(height: 12),
        FilledButton.icon(
          icon: const Icon(Icons.push_pin_outlined),
          label: Text(context.t('md_use')),
          onPressed: () {
            Navigator.pop(context);
            onUse!();
          },
        ),
      ],
    ]);
  }
}

String _k(int n) => n >= 1000 ? '${(n / 1000).round()} k' : '$n';

/// Liste simple des générateurs disponibles, par type, avec leur état.
class GeneratorsSheet extends StatefulWidget {
  const GeneratorsSheet({super.key, required this.controller});
  final ScrollController controller;

  static Future<void> show(BuildContext context) => showModalBottomSheet<void>(
        context: context,
        isScrollControlled: true,
        showDragHandle: true,
        builder: (context) => DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.75,
          builder: (context, controller) => GeneratorsSheet(controller: controller),
        ),
      );

  @override
  State<GeneratorsSheet> createState() => _GeneratorsSheetState();
}

const _kinds = [
  ('image_gen', Icons.brush_outlined),
  ('image_edit', Icons.auto_fix_high_outlined),
  ('video_gen', Icons.movie_outlined),
  ('tts', Icons.record_voice_over_outlined),
  ('stt', Icons.mic_none),
  ('music_sfx', Icons.music_note_outlined),
];

class _GeneratorsSheetState extends State<GeneratorsSheet> {
  Map<String, List<Map<String, dynamic>>>? kinds;
  bool error = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (kinds == null && !error) _load();
  }

  Future<void> _load() async {
    try {
      final data = await AppScope.of(context).backend.getJson('/projia/generators') as Map<String, dynamic>;
      final k = (data['kinds'] as Map).map((key, v) => MapEntry('$key', (v as List).cast<Map<String, dynamic>>()));
      if (mounted) setState(() => kinds = k);
    } catch (_) {
      if (mounted) setState(() => error = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final k = kinds;
    return ListView(controller: widget.controller, padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
      Text(context.t('generators'), style: text.titleLarge),
      const SizedBox(height: 4),
      Text(context.t('generators_help'), style: text.bodySmall),
      const SizedBox(height: 8),
      if (error)
        Text(context.t('error_generic'))
      else if (k == null)
        const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()))
      else
        for (final (kind, icon) in _kinds)
          Card(
            margin: const EdgeInsets.symmetric(vertical: 4),
            child: ExpansionTile(
              leading: Icon(icon),
              title: Text(context.t('cat_$kind')),
              subtitle: Text(_summary(context, k[kind] ?? const [])),
              children: [
                if ((k[kind] ?? const []).isEmpty)
                  ListTile(dense: true, title: Text(context.t('generators_none')))
                else
                  for (final m in k[kind]!)
                    ListTile(
                      dense: true,
                      leading: Icon(Icons.circle, size: 10, color: statusColor(m, scheme)),
                      minLeadingWidth: 10,
                      title: Text('${m['name']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text('${m['provider']} · ${m['free'] == true ? context.t('tag_free') : context.t('tag_paid')} · ${statusText(context, m)}'),
                      trailing: const Icon(Icons.info_outline, size: 18),
                      onTap: () => showModelDetails(context, m),
                    ),
              ],
            ),
          ),
    ]);
  }

  String _summary(BuildContext context, List<Map<String, dynamic>> list) {
    final ready = list.where((m) => m['usable'] == true && (m['available_at'] as num? ?? 0) == 0).length;
    final free = list.where((m) => m['usable'] == true && m['free'] == true).length;
    return context.t('generators_count', {'ready': '$ready', 'total': '${list.length}', 'free': '$free'});
  }
}
