// Réglages en deux onglets : Simple (l'essentiel) et Avancé (tout le reste).

import 'dart:convert';

import 'package:flutter/material.dart';

import '../core/account.dart';
import '../core/backend.dart';
import '../core/key_guides.dart';
import '../core/keys.dart';
import '../core/provider_text.dart';
import '../core/stats.dart';
import '../core/sync.dart';
import '../core/updater.dart';
import '../main.dart';
import 'about_screen.dart';
import 'account_section.dart';
import 'advanced_routing.dart';
import 'personalization.dart';
import 'message_view.dart' show openSafeLink;
import 'status_screen.dart';
import 'update_sheet.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 2,
        child: Scaffold(
          appBar: AppBar(
            leading: ShellNav.maybeOf(context)?.backButton(context),
            title: Text(context.t('settings')),
            bottom: TabBar(tabs: [Tab(text: context.t('simple')), Tab(text: context.t('advanced'))]),
          ),
          body: const TabBarView(children: [_Simple(), _Advanced()]),
        ),
      );
}

class _Simple extends StatelessWidget {
  const _Simple();

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final prefs = scope.prefs;
    return ListenableBuilder(
      listenable: Listenable.merge([prefs, scope.updater]),
      builder: (context, _) => ListView(children: [
        if (Account.configured) ...[_Section(context.t('account')), const AccountSection()],
        // Ordre : soi et les réponses d'abord, puis les modèles (clés, payant), puis l'affichage.
        PersonalizationSection(header: (t) => _Section(t)),
        _Section(context.t('keys')),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Text(context.t('keys_help'), style: Theme.of(context).textTheme.bodySmall),
        ),
        const ProviderKeys(),
        _Section(context.t('paid_simple')),
        const PaidSimple(),
        _Section(context.t('group_display')),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: SegmentedButton<ThemeMode>(
            segments: [
              ButtonSegment(value: ThemeMode.system, label: Text(context.t('theme_system'))),
              ButtonSegment(value: ThemeMode.light, label: Text(context.t('theme_light'))),
              ButtonSegment(value: ThemeMode.dark, label: Text(context.t('theme_dark'))),
            ],
            selected: {prefs.themeMode},
            onSelectionChanged: (s) => prefs.themeMode = s.first,
          ),
        ),
        ListTile(
          title: Text(context.t('text_size')),
          subtitle: Slider(
            value: prefs.textScale, min: 0.85, max: 1.6, divisions: 15,
            label: '${(prefs.textScale * 100).round()} %',
            onChanged: (v) => prefs.textScale = v,
          ),
        ),
        SwitchListTile(title: Text(context.t('reduce_motion')), value: prefs.reduceMotion, onChanged: (v) => prefs.reduceMotion = v),
        ListTile(
          title: Text(context.t('language')),
          trailing: DropdownButton<String>(
            value: prefs.locale,
            items: const [
              DropdownMenuItem(value: 'fr', child: Text('Français')),
              DropdownMenuItem(value: 'en', child: Text('English')),
              DropdownMenuItem(value: 'mg', child: Text('Malagasy')),
            ],
            onChanged: (v) {
              prefs.locale = v ?? 'fr';
              // Le moteur répond par défaut dans la langue de l'interface.
              scope.backend.sendJson('PUT', '/tontolo/settings', {'language': prefs.locale}).catchError((_) => null);
            },
          ),
        ),
        ListTile(
          leading: const Icon(Icons.new_releases_outlined),
          title: Text(context.t('whats_new')),
          subtitle: Text('${context.t('version')} $appVersion'),
          onTap: () => showWhatsNew(context),
        ),
        if (scope.updater.status == UpdateStatus.ready && scope.updater.latest != null)
          ListTile(
            leading: Icon(Icons.system_update, color: Theme.of(context).colorScheme.primary),
            title: Text(context.t('update_ready', {'v': scope.updater.latest!})),
            subtitle: Text(context.t('see_changes')),
            onTap: () => showUpdateSheet(context),
          ),
        ListTile(
          leading: const Icon(Icons.monitor_heart_outlined),
          title: Text(context.t('model_status')),
          subtitle: Text(context.t('model_status_sub')),
          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const StatusScreen())),
        ),
        ListTile(
          leading: const Icon(Icons.refresh),
          title: Text(context.t('check_updates')),
          onTap: () async {
            final messenger = ScaffoldMessenger.of(context);
            messenger.showSnackBar(SnackBar(content: Text(context.t('checking_updates')), duration: const Duration(seconds: 2)));
            await scope.updater.run(manual: true);
            if (!context.mounted) return;
            messenger.hideCurrentSnackBar();
            final up = scope.updater;
            switch (up.status) {
              case UpdateStatus.ready:
                await showUpdateSheet(context); // toujours proposée sur demande, même déjà annoncée
              case UpdateStatus.failed:
                messenger.showSnackBar(SnackBar(content: Text(up.message ?? context.t('error_generic'))));
              case UpdateStatus.upToDate:
                messenger.showSnackBar(SnackBar(content: Text(context.t('up_to_date_v', {'v': appVersion}))));
              default:
                break;
            }
          },
        ),
        SwitchListTile(
          title: Text(context.t('auto_update')),
          subtitle: Text(_updateText(context, scope.updater)),
          value: prefs.autoUpdate,
          onChanged: (v) {
            prefs.autoUpdate = v;
            if (v) scope.updater.startAuto();
          },
        ),
        SwitchListTile(title: Text(context.t('notif_new_free')), value: prefs.notifyNewFree, onChanged: (v) => prefs.notifyNewFree = v),
        SwitchListTile(
          secondary: const Icon(Icons.insights_outlined),
          title: Text(context.t('share_stats')),
          subtitle: Text(context.t('share_stats_help')),
          value: prefs.shareStats,
          onChanged: (v) => prefs.shareStats = v,
        ),
        SwitchListTile(
          secondary: const Icon(Icons.thumbs_up_down_outlined),
          title: Text(context.t('share_ratings')),
          subtitle: Text(context.t('share_ratings_help')),
          value: prefs.shareRatings,
          onChanged: (v) => prefs.shareRatings = v,
        ),
        ListTile(
          dense: true,
          leading: const SizedBox(width: 24),
          title: Text(context.t('stats_see')),
          onTap: () => showDialog<void>(
            context: context,
            builder: (context) => AlertDialog(
              title: Text(context.t('stats_see')),
              content: SelectableText(const JsonEncoder.withIndent('  ').convert({...Stats.payload(prefs), if (prefs.shareRatings) 'ratings': Stats.pendingRatings(prefs)}),
                  style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
              actions: [TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('got_it')))],
            ),
          ),
        ),
        ListTile(
          leading: const Icon(Icons.info_outline),
          title: Text(context.t('about')),
          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const AboutScreen())),
        ),
      ]),
    );
  }

  String _updateText(BuildContext context, Updater up) => switch (up.status) {
        UpdateStatus.downloading => '${context.t('update_downloading')} ${(up.progress * 100).round()} %',
        UpdateStatus.ready => up.message ?? '',
        UpdateStatus.failed => up.message ?? '',
        UpdateStatus.upToDate => context.t('up_to_date_v', {'v': appVersion}),
        _ => '${context.t('version')} $appVersion',
      };
}

/// Fournisseurs gratuits : lien direct vers la page de clé, collage, validation immédiate.
class ProviderKeys extends StatefulWidget {
  const ProviderKeys({super.key});

  @override
  State<ProviderKeys> createState() => _ProviderKeysState();
}

class _ProviderKeysState extends State<ProviderKeys> {
  List<Map<String, dynamic>> providers = [];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final data = await b.getJson('/tontolo/providers') as List;
    final list = data.cast<Map<String, dynamic>>()
      ..add({'id': 'artificial-analysis', 'name': mounted ? context.t('aa_name') : 'Artificial Analysis',
             'description': mounted ? context.t('aa_help') : null,
             'key_url': 'https://artificialanalysis.ai/insights', 'has_key': false, 'free_models': 0});
    list.sort((a, b) => (b['free_models'] as int).compareTo(a['free_models'] as int));
    if (mounted) setState(() => providers = list.where((p) => p['id'] != 'local').toList());
  }

  Future<void> _edit(Map<String, dynamic> p) async {
    await editProviderKey(context, p);
    _load();
  }

  @override
  Widget build(BuildContext context) => Column(children: [
        for (final p in providers.where((p) => p['paid'] != true))
          ListTile(
            leading: Icon(p['keyless'] == true ? Icons.lock_open : p['has_key'] == true ? Icons.check_circle : Icons.key_outlined,
                color: p['has_key'] == true || p['keyless'] == true ? Theme.of(context).colorScheme.secondary : null),
            title: Text(providerText(p, AppScope.of(context).prefs.locale, 'name')),
            subtitle: Text(
                p['keyless'] == true
                    ? context.t('no_key_needed')
                    : (p['free_models'] as int? ?? 0) == 0 && p['has_key'] != true && providerText(p, AppScope.of(context).prefs.locale, 'description').isNotEmpty
                        ? providerText(p, AppScope.of(context).prefs.locale, 'description') // modèles découverts une fois la clé ajoutée
                        : context.t('n_free_models', {'n': '${p['free_models']}'}),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
            onTap: p['keyless'] == true ? null : () => _edit(p),
          ),
      ]);
}

/// Étapes pour obtenir la clé d'un fournisseur (repliables), avec le lien direct.
class KeyGuideView extends StatelessWidget {
  const KeyGuideView({super.key, required this.providerId, this.fallbackUrl, this.initiallyExpanded = true});

  final String providerId;
  final String? fallbackUrl;
  final bool initiallyExpanded;

  @override
  Widget build(BuildContext context) {
    final g = keyGuides[providerId];
    final url = g?.url ?? fallbackUrl;
    final small = Theme.of(context).textTheme.bodySmall;
    if (g == null) {
      return url == null
          ? const SizedBox.shrink()
          : Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(icon: const Icon(Icons.open_in_new), label: Text(context.t('get_key')), onPressed: () => openSafeLink(url)),
            );
    }
    final login = g.login.split(', ').map((w) => switch (w) {
          'e-mail' => context.t('kg_email'),
          'téléphone' => context.t('kg_phone'),
          _ => w,
        }).join(', ');
    final steps = [
      context.t('kg_step1', {'login': login}),
      context.t('kg_step2', {'path': g.path}),
      context.t(g.prefix.isEmpty ? 'kg_step3' : 'kg_step3p', {'button': g.button, 'prefix': g.prefix}),
      context.t('kg_step4'),
    ];
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: EdgeInsets.zero,
      color: scheme.surfaceContainerHighest,
      child: ExpansionTile(
        initiallyExpanded: initiallyExpanded,
        leading: const Icon(Icons.help_outline),
        title: Text(context.t('kg_title')),
        subtitle: Text(context.t('kg_cost_${g.cost}'), style: small),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final (i, step) in steps.indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                CircleAvatar(radius: 10, backgroundColor: scheme.primary, child: Text('${i + 1}', style: TextStyle(fontSize: 11, color: scheme.onPrimary))),
                const SizedBox(width: 8),
                Expanded(child: Text(step, style: small)),
              ]),
            ),
          if (g.note != null)
            Padding(
              padding: const EdgeInsets.only(top: 2, bottom: 6),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(Icons.lightbulb_outline, size: 16, color: scheme.tertiary),
                const SizedBox(width: 8),
                Expanded(child: Text(context.t(g.note!), style: small)),
              ]),
            ),
          FilledButton.tonalIcon(
            icon: const Icon(Icons.open_in_new),
            label: Text(context.t('kg_open')),
            onPressed: () => openSafeLink(g.url),
          ),
        ],
      ),
    );
  }
}

/// Modèles payants en version simple : quand les utiliser, un plafond mensuel en un geste,
/// la dépense du mois, et les serveurs (une clé chacun, avec l'aide pour l'obtenir).
class PaidSimple extends StatefulWidget {
  const PaidSimple({super.key});

  @override
  State<PaidSimple> createState() => _PaidSimpleState();
}

class _PaidSimpleState extends State<PaidSimple> {
  Map<String, dynamic>? paid;
  double month = 0;
  List<Map<String, dynamic>> servers = [];

  static const _caps = [1.0, 5.0, 10.0, 20.0];
  static const _order = ['openrouter', 'openai', 'anthropic', 'deepseek', 'xai'];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    try {
      final s = await b.getJson('/tontolo/settings') as Map<String, dynamic>;
      final sp = await b.getJson('/tontolo/spend') as Map<String, dynamic>;
      final prov = (await b.getJson('/tontolo/providers') as List).cast<Map<String, dynamic>>();
      if (!mounted) return;
      setState(() {
        paid = (s['paid'] as Map?)?.cast<String, dynamic>() ?? {};
        month = (sp['month'] as num? ?? 0).toDouble();
        // Ordre connu d'abord, puis tout autre serveur payant ajouté au cœur (aucune liste figée).
        servers = [
          for (final id in _order) ...prov.where((p) => p['id'] == id),
          ...prov.where((p) => p['paid'] == true && !_order.contains(p['id']))
              .toList()..sort((a, b) => '${a['name']}'.compareTo('${b['name']}')),
        ];
      });
    } catch (_) {} // ancien cœur distant : section masquée
  }

  Future<void> _patch(Map<String, dynamic> patch) async {
    final s = await AppScope.of(context).backend.sendJson('PUT', '/tontolo/settings', {'paid': patch});
    if (mounted) setState(() => paid = ((s as Map)['paid'] as Map).cast<String, dynamic>());
  }

  Future<void> _key(Map<String, dynamic> p) async {
    await editProviderKey(context, p);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final p = paid;
    if (p == null) return const SizedBox.shrink();
    final mode = '${p['fallback'] ?? 'off'}';
    final cap = (p['monthly_cap_usd'] as num? ?? 0).toDouble();
    final small = Theme.of(context).textTheme.bodySmall;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text(context.t('paid_simple_help'), style: small),
      ),
      const SizedBox(height: 10),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: SegmentedButton<String>(
          segments: [
            ButtonSegment(value: 'off', label: Text(context.t('paid_off'))),
            ButtonSegment(value: 'ask', label: Text(context.t('paid_ask'))),
            ButtonSegment(value: 'auto', label: Text(context.t('paid_auto'))),
          ],
          selected: {mode},
          onSelectionChanged: (v) {
            final patch = <String, dynamic>{'fallback': v.first};
            // Premier passage en payant : plafond prudent par défaut (5 $ / mois, 1 $ / jour).
            if (v.first != 'off' && cap <= 0) patch.addAll({'monthly_cap_usd': 5.0, 'daily_cap_usd': 1.0});
            _patch(patch);
          },
        ),
      ),
      if (mode != 'off') ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text(context.t('paid_cap_month'), style: Theme.of(context).textTheme.labelLarge),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Wrap(spacing: 8, children: [
            for (final c in _caps)
              ChoiceChip(
                label: Text('${c.toStringAsFixed(0)} \$'),
                selected: cap == c,
                onSelected: (_) => _patch({'monthly_cap_usd': c, 'daily_cap_usd': (c / 5).clamp(0.5, 5.0)}),
              ),
          ]),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text(context.t('paid_spent', {'spent': month.toStringAsFixed(2), 'cap': cap.toStringAsFixed(0)}), style: small),
        ),
        if (cap > 0)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 6, 16, 0),
            child: LinearProgressIndicator(value: (month / cap).clamp(0.0, 1.0)),
          ),
      ],
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Text(context.t('paid_servers'), style: Theme.of(context).textTheme.labelLarge),
      ),
      for (final s in servers)
        ListTile(
          leading: Icon(s['has_key'] == true ? Icons.check_circle : Icons.key_outlined,
              color: s['has_key'] == true ? Theme.of(context).colorScheme.secondary : null),
          title: Text(providerText(s, AppScope.of(context).prefs.locale, 'name')),
          subtitle: Text(s['id'] == 'openrouter' ? context.t('paid_openrouter') : providerText(s, AppScope.of(context).prefs.locale, 'description'), maxLines: 2, overflow: TextOverflow.ellipsis),
          trailing: s['has_key'] == true && (s['paid_models'] as int? ?? 0) > 0
              ? Text(context.t('n_paid_models', {'n': '${s['paid_models']}'}), style: small)
              : null,
          onTap: () => _key(s),
        ),
    ]);
  }
}

/// Boîte de dialogue de clé : aide pas à pas, collage, vérification immédiate.
Future<void> editProviderKey(BuildContext context, Map<String, dynamic> p) async {
  final b = AppScope.of(context).backend;
  final ctrl = TextEditingController();
  String? result;
  await showDialog<void>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, setLocal) => AlertDialog(
        title: Text(providerText(p, AppScope.of(context).prefs.locale, 'name')),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (p['description'] != null) Text(providerText(p, AppScope.of(context).prefs.locale, 'description'), style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 8),
          KeyGuideView(providerId: '${p['id']}', fallbackUrl: p['key_url'] as String?),
          const SizedBox(height: 8),
          TextField(controller: ctrl, obscureText: true, decoration: InputDecoration(hintText: context.t('paste_key'))),
          if (result != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(result!)),
        ]),
        scrollable: true,
        actions: [
          if (p['has_key'] == true)
            TextButton(
              onPressed: () async {
                await Keys.remove(b, '${p['id']}');
                if (context.mounted) Navigator.pop(context);
              },
              child: Text(context.t('delete')),
            ),
          TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
          FilledButton(
            onPressed: () async {
              final (ok, detail) = await Keys.save(b, '${p['id']}', ctrl.text.trim());
              setLocal(() => result = ok ? '✓ ${context.t('key_valid')}' : '✗ $detail');
              if (ok && context.mounted) Navigator.pop(context);
            },
            child: Text(context.t('save')),
          ),
        ],
      ),
    ),
  );
}

class _Advanced extends StatefulWidget {
  const _Advanced();

  @override
  State<_Advanced> createState() => _AdvancedState();
}

class _AdvancedState extends State<_Advanced> {
  Map<String, dynamic>? settings;
  Map<String, dynamic>? status;
  final urlCtrl = TextEditingController();
  final tokenCtrl = TextEditingController();
  final mcpName = TextEditingController();
  final mcpUrl = TextEditingController();
  List<Map<String, dynamic>> mcpServers = [];
  String? syncResult;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final prefs = AppScope.of(context).prefs;
    urlCtrl.text = prefs.remoteUrl.isNotEmpty ? prefs.remoteUrl : prefs.syncUrl;
    _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final s = await b.getJson('/tontolo/settings') as Map<String, dynamic>;
    final st = await b.getJson('/tontolo/status') as Map<String, dynamic>;
    final mcp = await b.getJson('/tontolo/mcp') as Map<String, dynamic>;
    if (mounted) {
      setState(() {
        settings = s;
        status = st;
        mcpServers = (mcp['servers'] as List).cast<Map<String, dynamic>>();
      });
    }
  }

  Future<void> _patch(Map<String, dynamic> patch) async {
    final s = await AppScope.of(context).backend.sendJson('PUT', '/tontolo/settings', patch);
    setState(() => settings = (s as Map).cast<String, dynamic>());
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final prefs = scope.prefs;
    final s = settings;
    final paid = (s?['paid'] as Map?)?.cast<String, dynamic>() ?? {};
    final weights = (s?['weights'] as Map?)?.cast<String, dynamic>() ?? {};
    final remote = prefs.remoteUrl.isNotEmpty;
    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      _Section(context.t('mode')),
      RadioGroup<bool>(
        groupValue: remote,
        onChanged: (v) async {
          if (v == true) {
            prefs.remoteUrl = urlCtrl.text.trim();
          } else {
            prefs.remoteUrl = '';
          }
          await Keys.setRemoteToken(tokenCtrl.text.trim());
          await scope.backend.start();
          _load();
        },
        child: Column(children: [
          RadioListTile<bool>(value: false, title: Text(context.t('mode_local'))),
          RadioListTile<bool>(value: true, title: Text(context.t('mode_remote'))),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Column(children: [
          TextField(controller: urlCtrl, decoration: InputDecoration(labelText: context.t('server_url'), hintText: 'http://192.168.1.10:8765')),
          const SizedBox(height: 8),
          TextField(controller: tokenCtrl, obscureText: true, decoration: InputDecoration(labelText: context.t('server_token'))),
        ]),
      ),
      if (!remote) ...[
        SwitchListTile(
          title: Text(context.t('sync')),
          value: prefs.syncEnabled,
          onChanged: (v) async {
            prefs.syncUrl = urlCtrl.text.trim();
            if (tokenCtrl.text.isNotEmpty) await Keys.setRemoteToken(tokenCtrl.text.trim());
            prefs.syncEnabled = v;
            setState(() {});
          },
        ),
        if (prefs.syncEnabled)
          ListTile(
            title: Text(context.t('sync_now')),
            subtitle: syncResult == null ? null : Text(syncResult!),
            trailing: const Icon(Icons.sync),
            onTap: () async {
              try {
                final n = await HistorySync.run(scope.backend);
                setState(() => syncResult = '✓ $n élément(s)');
              } catch (e) {
                setState(() => syncResult = '✗ $e');
              }
            },
          ),
      ],
      _Section(context.t('storage')),
      const _StorageSection(),
      _Section(context.t('paid')),
      if (s != null) ...[
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: SegmentedButton<String>(
            segments: [
              ButtonSegment(value: 'off', label: Text(context.t('paid_off'))),
              ButtonSegment(value: 'ask', label: Text(context.t('paid_ask'))),
              ButtonSegment(value: 'auto', label: Text(context.t('paid_auto'))),
            ],
            selected: {'${paid['fallback'] ?? 'off'}'},
            onSelectionChanged: (v) => _patch({'paid': {'fallback': v.first}}),
          ),
        ),
        _NumberTile(label: context.t('daily_cap'), value: (paid['daily_cap_usd'] as num? ?? 0).toDouble(),
            onChanged: (v) => _patch({'paid': {'daily_cap_usd': v}})),
        _NumberTile(label: context.t('monthly_cap'), value: (paid['monthly_cap_usd'] as num? ?? 0).toDouble(),
            onChanged: (v) => _patch({'paid': {'monthly_cap_usd': v}})),
        _Section(context.t('weights')),
        for (final (k, label) in [('quality', 'quality'), ('speed', 'speed'), ('reliability', 'reliability')])
          ListTile(
            title: Text(context.t(label)),
            subtitle: Slider(
              value: (weights[k] as num? ?? 0).toDouble().clamp(0, 1),
              divisions: 20,
              label: (weights[k] as num? ?? 0).toStringAsFixed(2),
              onChanged: (v) => setState(() => weights[k] = v),
              onChangeEnd: (v) => _patch({'weights': {k: v}}),
            ),
          ),
      ],
      AdvancedRouting(header: (t) => _Section(t)),
      _Section(context.t('mcp')),
      for (final (i, srv) in mcpServers.indexed)
        SwitchListTile(
          title: Text('${srv['name']}'),
          subtitle: Text('${srv['url'] ?? srv['command'] ?? ''}'),
          value: srv['enabled'] != false,
          onChanged: (v) async {
            mcpServers[i] = {...srv, 'enabled': v};
            await scope.backend.sendJson('PUT', '/tontolo/mcp', {'servers': mcpServers});
            setState(() {});
          },
        ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Row(children: [
          Expanded(child: TextField(controller: mcpName, decoration: InputDecoration(hintText: context.t('name_hint')))),
          const SizedBox(width: 8),
          Expanded(flex: 2, child: TextField(controller: mcpUrl, decoration: const InputDecoration(hintText: 'https://…/mcp'))),
          IconButton(
            icon: const Icon(Icons.add),
            onPressed: () async {
              if (mcpName.text.isEmpty || mcpUrl.text.isEmpty) return;
              mcpServers.add({'name': mcpName.text.trim(), 'transport': 'http', 'url': mcpUrl.text.trim(), 'enabled': true});
              await scope.backend.sendJson('PUT', '/tontolo/mcp', {'servers': mcpServers});
              mcpName.clear();
              mcpUrl.clear();
              _load();
            },
          ),
        ]),
      ),
      _Section(context.t('catalog')),
      ListTile(
        title: Text(context.t('catalog_refresh')),
        subtitle: Text(status == null ? '' : '${context.t('catalog_sources')} : ${(status!['sources'] as Map).entries.map((e) => '${e.key} ${e.value}').join(', ')}'),
        trailing: const Icon(Icons.refresh),
        onTap: () async {
          await scope.backend.sendJson('POST', '/tontolo/catalog/refresh');
          _load();
        },
      ),
      if (status != null && (status!['quotas'] as Map).isNotEmpty)
        ExpansionTile(
          title: Text(context.t('models_waiting_n', {'n': '${(status!['quotas'] as Map).length}'})),
          children: [
            for (final e in (status!['quotas'] as Map).entries)
              ListTile(
                dense: true,
                title: Text('${e.key}'),
                subtitle: Text(context.t('until_reason', {
                  'reason': '${(e.value as Map)['reason']}',
                  't': DateTime.fromMillisecondsSinceEpoch((((e.value as Map)['until'] as num) * 1000).round()).toLocal().toString().substring(0, 16),
                })),
              ),
          ],
        ),
      if (scope.backend.startupTime != null)
        ListTile(dense: true, title: Text(context.t('engine_startup', {'ms': '${scope.backend.startupTime!.inMilliseconds}'}))),
    ]);
  }
}

class _NumberTile extends StatelessWidget {
  const _NumberTile({required this.label, required this.value, required this.onChanged});
  final String label;
  final double value;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) => ListTile(
        title: Text(label),
        trailing: SizedBox(
          width: 100,
          child: TextFormField(
            initialValue: value.toStringAsFixed(2),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            textAlign: TextAlign.end,
            onFieldSubmitted: (v) => onChanged(double.tryParse(v.replaceAll(',', '.')) ?? 0),
          ),
        ),
      );
}

class _Section extends StatelessWidget {
  const _Section(this.title);
  final String title;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 6),
        child: Text(title, style: Theme.of(context).textTheme.titleSmall?.copyWith(color: Theme.of(context).colorScheme.primary)),
      );
}


/// Place occupée : données (jamais effacées ici) et cache unique, vidable d'un geste.
class _StorageSection extends StatefulWidget {
  const _StorageSection();

  @override
  State<_StorageSection> createState() => _StorageSectionState();
}

class _StorageSectionState extends State<_StorageSection> {
  Map<String, dynamic>? r;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (r == null) _load();
  }

  Future<void> _load([String method = 'GET']) async {
    final b = AppScope.of(context).backend;
    try {
      final data = method == 'GET'
          ? await b.getJson('/tontolo/storage')
          : await b.sendJson('POST', '/tontolo/storage/clear-cache', {});
      if (mounted) setState(() => r = (data as Map).cast<String, dynamic>());
    } catch (_) {}
  }

  String _mb(Object? v) => '${(((v as num?) ?? 0) / 1048576).toStringAsFixed(1)} Mo';

  @override
  Widget build(BuildContext context) {
    final data = r;
    if (data == null) return const SizedBox.shrink();
    final small = Theme.of(context).textTheme.bodySmall;
    final rows = [
      ('storage_conversations', data['conversations']),
      ('storage_creations', data['creations']),
      ('storage_tasks', data['tasks']),
      ('storage_backups', data['backups']),
      ('storage_browser', data['browser_profile']),
    ];
    return Column(children: [
      for (final (k, v) in rows)
        if (((v as num?) ?? 0) > 0) ListTile(dense: true, title: Text(context.t(k)), trailing: Text(_mb(v), style: small)),
      ListTile(
        leading: const Icon(Icons.cleaning_services_outlined),
        title: Text(context.t('storage_cache', {'s': _mb(data['cache_total'])})),
        subtitle: Text(context.t('storage_cache_help'), style: small),
        trailing: TextButton(onPressed: () => _load('POST'), child: Text(context.t('storage_clear'))),
      ),
    ]);
  }
}
