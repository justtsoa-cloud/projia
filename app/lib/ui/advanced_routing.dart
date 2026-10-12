// Mode avancé : plus de souplesse sur le routage, sans affaiblir la sécurité.
// - Fournisseurs personnalisés compatibles OpenAI : testés avant l'ajout, clé envoyée seulement
//   en HTTPS à l'hôte épinglé (serveur local en HTTP : sans clé). Sur l'appareil seulement.
// - Fournisseurs exclus, enchaînements de modèles par catégorie, délais du routeur bornés.
// - Export / import des réglages (jamais les clés).
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/backend.dart';
import '../core/provider_text.dart';
import '../main.dart';

class AdvancedRouting extends StatefulWidget {
  const AdvancedRouting({super.key, required this.header});

  /// Titre de section, au style de l'écran des réglages.
  final Widget Function(String title) header;

  @override
  State<AdvancedRouting> createState() => _AdvancedRoutingState();
}

/// Message d'erreur lisible d'une réponse du cœur (« HTTP 400 : {"error": …} »).
String coreError(Object e) {
  final text = '$e';
  final i = text.indexOf('{');
  if (i >= 0) {
    try {
      final data = jsonDecode(text.substring(i));
      final msg = data is Map ? ((data['error'] as Map?)?['message'] ?? data['detail']) : null;
      if (msg != null) return '$msg';
    } catch (_) {}
  }
  return text.replaceFirst('HttpException: ', '');
}

class _AdvancedRoutingState extends State<AdvancedRouting> {
  static const categories = ['chat', 'code', 'math', 'reasoning', 'writing', 'search', 'vision'];

  Map<String, dynamic>? routing;
  List<Map<String, dynamic>> custom = [];
  List<Map<String, dynamic>> providers = [];
  bool available = false; // cœur récent (sinon section masquée)

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Backend get _b => AppScope.of(context).backend;
  bool get _local => AppScope.of(context).prefs.remoteUrl.isEmpty;

  Future<void> _load() async {
    if (_b.state != BackendState.ready) return;
    try {
      final s = await _b.getJson('/tontolo/settings') as Map<String, dynamic>;
      final c = (await _b.getJson('/tontolo/custom-providers') as List).cast<Map<String, dynamic>>();
      final p = (await _b.getJson('/tontolo/providers') as List).cast<Map<String, dynamic>>();
      if (!mounted) return;
      setState(() {
        routing = (s['routing'] as Map?)?.cast<String, dynamic>();
        custom = c;
        providers = p.where((x) => x['id'] != 'local' && (x['keyless'] == true || x['has_key'] == true)).toList()
          ..sort((a, b) => '${a['name']}'.compareTo('${b['name']}'));
        available = routing != null;
      });
    } catch (_) {
      if (mounted) setState(() => available = false); // ancien cœur
    }
  }

  Future<void> _patchRouting(Map<String, dynamic> patch) async {
    try {
      final s = await _b.sendJson('PUT', '/tontolo/settings', {'routing': patch});
      if (mounted) setState(() => routing = ((s as Map)['routing'] as Map).cast<String, dynamic>());
    } catch (e) {
      _snack(coreError(e));
    }
  }

  void _snack(String text) {
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  // --- Fournisseurs personnalisés ---------------------------------------------------------

  Future<void> _addCustom() async {
    final name = TextEditingController();
    final url = TextEditingController(text: 'https://');
    final key = TextEditingController();
    final priceIn = TextEditingController();
    final priceOut = TextEditingController();
    var noKey = false, free = true, busy = false;
    String? error;
    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocal) => AlertDialog(
          title: Text(context.t('adv_custom_add')),
          scrollable: true,
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(context.t('adv_custom_help'), style: Theme.of(context).textTheme.bodySmall),
            TextField(controller: name, maxLength: 60, decoration: InputDecoration(labelText: context.t('adv_name'))),
            TextField(
              controller: url,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(labelText: context.t('adv_url'), hintText: 'https://api.exemple.com/v1'),
            ),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: noKey,
              title: Text(context.t('adv_no_key')),
              onChanged: (v) => setLocal(() => noKey = v ?? false),
            ),
            if (!noKey) TextField(controller: key, obscureText: true, decoration: InputDecoration(labelText: context.t('paste_key'))),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: free,
              title: Text(context.t('adv_free')),
              onChanged: (v) => setLocal(() => free = v),
            ),
            if (!free)
              Row(children: [
                Expanded(child: TextField(controller: priceIn, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: context.t('adv_price_in')))),
                const SizedBox(width: 8),
                Expanded(child: TextField(controller: priceOut, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: InputDecoration(labelText: context.t('adv_price_out')))),
              ]),
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
            FilledButton(
              onPressed: busy
                  ? null
                  : () async {
                      setLocal(() {
                        busy = true;
                        error = null;
                      });
                      try {
                        final r = await _b.sendJson('POST', '/tontolo/custom-providers', {
                          'name': name.text.trim(),
                          'base_url': url.text.trim(),
                          'needs_key': !noKey,
                          if (!noKey) 'key': key.text.trim(),
                          'free': free,
                          if (!free) 'price_in_per_m': double.tryParse(priceIn.text.replaceAll(',', '.')) ?? 0,
                          if (!free) 'price_out_per_m': double.tryParse(priceOut.text.replaceAll(',', '.')) ?? 0,
                        }) as Map;
                        if (context.mounted) Navigator.pop(context);
                        if (mounted) _snack(this.context.t('adv_added', {'n': '${r['models']}'}));
                      } catch (e) {
                        setLocal(() {
                          busy = false;
                          error = coreError(e);
                        });
                      }
                    },
              child: busy
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(context.t('adv_test_add')),
            ),
          ],
        ),
      ),
    );
    _load();
  }

  Future<void> _removeCustom(String id) async {
    try {
      await _b.sendJson('DELETE', '/tontolo/custom-providers/$id');
    } catch (e) {
      _snack(coreError(e));
    }
    _load();
  }

  // --- Enchaînements ----------------------------------------------------------------------

  Map<String, List<String>> get _chains => {
        for (final e in ((routing?['chains'] as Map?) ?? const {}).entries)
          '${e.key}': [for (final k in e.value as List) '$k'],
      };

  Future<void> _addToChain(String category) async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (context) => _ChainModelPicker(category: category),
    );
    if (picked == null) return;
    final chains = _chains;
    final list = chains[category] ?? [];
    if (list.contains(picked) || list.length >= 10) return;
    chains[category] = [...list, picked];
    await _patchRouting({'chains': chains});
  }

  Future<void> _removeFromChain(String category, String key) async {
    final chains = _chains;
    chains[category] = (chains[category] ?? []).where((k) => k != key).toList();
    if (chains[category]!.isEmpty) chains.remove(category);
    await _patchRouting({'chains': chains});
  }

  // --- Export / import --------------------------------------------------------------------

  Future<void> _export() async {
    final data = await _b.getJson('/tontolo/settings/export');
    await Clipboard.setData(ClipboardData(text: const JsonEncoder.withIndent(' ').convert(data)));
    if (mounted) _snack(context.t('adv_exported'));
  }

  Future<void> _import() async {
    final ctrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(context.t('adv_import')),
        content: TextField(controller: ctrl, maxLines: 8, decoration: InputDecoration(hintText: context.t('adv_import_hint'))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(context.t('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(context.t('adv_import'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _b.sendJson('POST', '/tontolo/settings/import', jsonDecode(ctrl.text));
      if (mounted) _snack(context.t('adv_imported'));
    } on FormatException {
      if (mounted) _snack(context.t('adv_import_hint'));
    } catch (e) {
      _snack(coreError(e));
    }
    _load();
  }

  @override
  Widget build(BuildContext context) {
    if (!available) return const SizedBox.shrink();
    final small = Theme.of(context).textTheme.bodySmall;
    final excluded = {for (final p in (routing?['excluded_providers'] as List? ?? const [])) '$p'};
    final chains = _chains;
    Widget limit(String field, String label, double min, double max, double def) {
      final v = (routing?[field] as num?)?.toDouble();
      return ListTile(
        dense: true,
        title: Text('$label : ${v == null ? context.t('adv_default', {'s': def.toStringAsFixed(0)}) : '${v.toStringAsFixed(0)} s'}'),
        subtitle: Slider(
          value: (v ?? def).clamp(min, max),
          min: min,
          max: max,
          divisions: ((max - min) / 5).round(),
          onChanged: (x) => setState(() => routing = {...?routing, field: x}),
          onChangeEnd: (x) => _patchRouting({field: x.roundToDouble()}),
        ),
        trailing: v == null
            ? null
            : IconButton(
                icon: const Icon(Icons.restart_alt, size: 18),
                tooltip: context.t('adv_reset'),
                onPressed: () => _patchRouting({field: null}),
              ),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      widget.header(context.t('adv_custom')),
      for (final c in custom)
        ListTile(
          leading: Icon(c['needs_key'] == true ? Icons.lock_outline : Icons.lan_outlined),
          title: Text('${c['name']}'),
          subtitle: Text('${c['base_url']}\n${context.t('adv_n_models', {'n': '${c['models']}'})}'
              '${c['free'] == true ? '' : ' · ${context.t('paid_auto')}'}', style: small),
          isThreeLine: true,
          trailing: _local
              ? IconButton(icon: const Icon(Icons.delete_outline), tooltip: context.t('delete'), onPressed: () => _removeCustom('${c['id']}'))
              : null,
        ),
      if (_local)
        Align(
          alignment: Alignment.centerLeft,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: TextButton.icon(onPressed: _addCustom, icon: const Icon(Icons.add), label: Text(context.t('adv_custom_add'))),
          ),
        )
      else
        Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(context.t('adv_local_only'), style: small)),
      widget.header(context.t('adv_excluded')),
      Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(context.t('adv_excluded_help'), style: small)),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
        child: Wrap(spacing: 6, runSpacing: 4, children: [
          for (final p in providers)
            FilterChip(
              label: Text(providerText(p, AppScope.of(context).prefs.locale, 'name')),
              selected: excluded.contains(p['id']),
              onSelected: (v) => _patchRouting({
                'excluded_providers': v ? [...excluded, p['id']] : excluded.where((x) => x != p['id']).toList(),
              }),
            ),
        ]),
      ),
      widget.header(context.t('adv_chains')),
      Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(context.t('adv_chains_help'), style: small)),
      for (final cat in categories)
        ListTile(
          dense: true,
          title: Text(context.t('cat_$cat')),
          subtitle: Wrap(spacing: 4, runSpacing: 2, children: [
            for (final (i, k) in (chains[cat] ?? const <String>[]).indexed)
              InputChip(
                label: Text('${i + 1}. ${k.split(':').last}', style: const TextStyle(fontSize: 12)),
                onDeleted: () => _removeFromChain(cat, k),
                visualDensity: VisualDensity.compact,
              ),
          ]),
          trailing: IconButton(icon: const Icon(Icons.add), tooltip: context.t('adv_add_model'), onPressed: () => _addToChain(cat)),
        ),
      widget.header(context.t('adv_limits')),
      Padding(padding: const EdgeInsets.symmetric(horizontal: 16), child: Text(context.t('adv_limits_help'), style: small)),
      limit('first_token_s', context.t('adv_first_token'), 20, 300, 90),
      limit('stall_s', context.t('adv_stall'), 15, 180, 60),
      limit('think_s', context.t('adv_think'), 60, 600, 150),
      OverflowBar(alignment: MainAxisAlignment.start, children: [
        TextButton.icon(onPressed: _export, icon: const Icon(Icons.upload_outlined), label: Text(context.t('adv_export'))),
        if (_local) TextButton.icon(onPressed: _import, icon: const Icon(Icons.download_outlined), label: Text(context.t('adv_import'))),
      ]),
    ]);
  }
}

/// Choix d'un modèle utilisable pour une catégorie (enchaînement).
class _ChainModelPicker extends StatefulWidget {
  const _ChainModelPicker({required this.category});
  final String category;

  @override
  State<_ChainModelPicker> createState() => _ChainModelPickerState();
}

class _ChainModelPickerState extends State<_ChainModelPicker> {
  List<Map<String, dynamic>> models = [];
  String query = '';
  bool loading = true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    try {
      final data = await AppScope.of(context).backend.getJson('/tontolo/catalog', {
        'category': widget.category, 'usable': true, 'limit': 100, if (query.isNotEmpty) 'q': query,
      }) as Map<String, dynamic>;
      models = (data['models'] as List).cast<Map<String, dynamic>>();
    } catch (_) {
      models = [];
    }
    if (mounted) setState(() => loading = false);
  }

  @override
  Widget build(BuildContext context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        builder: (context, controller) => Column(children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              decoration: InputDecoration(prefixIcon: const Icon(Icons.search), hintText: context.t('cat_${widget.category}')),
              onChanged: (v) {
                query = v.trim();
                _load();
              },
            ),
          ),
          if (loading) const LinearProgressIndicator(),
          Expanded(
            child: ListView(controller: controller, children: [
              for (final m in models)
                ListTile(
                  title: Text('${m['name'] ?? m['key']}'),
                  subtitle: Text('${m['provider']}${m['free'] == true ? '' : ' · \$'}'),
                  onTap: () => Navigator.pop(context, '${m['key']}'),
                ),
            ]),
          ),
        ]),
      );
}
