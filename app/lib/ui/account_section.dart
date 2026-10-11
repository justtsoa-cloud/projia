// Réglages › Compte : connexion Google / GitHub, phrase secrète, synchronisation chiffrée.

import 'package:flutter/material.dart';

import '../core/account.dart';
import '../core/cloud_sync.dart';
import '../main.dart';

class AccountSection extends StatelessWidget {
  const AccountSection({super.key});

  @override
  Widget build(BuildContext context) {
    if (!Account.configured) return const SizedBox.shrink();
    final scope = AppScope.of(context);
    return ListenableBuilder(
      listenable: Listenable.merge([scope.account, scope.cloud, scope.prefs]),
      builder: (context, _) {
        final acc = scope.account;
        final cloud = scope.cloud;
        final small = Theme.of(context).textTheme.bodySmall;
        if (!acc.signedIn) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(context.t('acc_help'), style: small),
              const SizedBox(height: 10),
              Wrap(spacing: 8, runSpacing: 8, children: [
                FilledButton.tonalIcon(icon: const Icon(Icons.g_mobiledata, size: 28), label: Text(context.t('acc_google')), onPressed: () => _signIn(context, 'google')),
                FilledButton.tonalIcon(icon: const Icon(Icons.code), label: Text(context.t('acc_github')), onPressed: () => _signIn(context, 'github')),
              ]),
            ]),
          );
        }
        final s = acc.session!;
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          ListTile(
            leading: const CircleAvatar(child: Icon(Icons.person)),
            title: Text(s.email.isEmpty ? context.t('acc_signed_in') : s.email),
            subtitle: Text(context.t('acc_via', {'p': s.provider == 'github' ? 'GitHub' : 'Google'})),
            trailing: TextButton(onPressed: () => _signOut(context), child: Text(context.t('acc_sign_out'))),
          ),
          if (!cloud.ready)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Card(
                margin: EdgeInsets.zero,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      const Icon(Icons.lock_outline),
                      const SizedBox(width: 8),
                      Expanded(child: Text(context.t('sync_phrase_title'), style: Theme.of(context).textTheme.titleSmall)),
                    ]),
                    const SizedBox(height: 6),
                    Text(context.t('sync_phrase_help'), style: small),
                    const SizedBox(height: 8),
                    FilledButton(onPressed: () => _askPhrase(context), child: Text(context.t('sync_phrase_set'))),
                  ]),
                ),
              ),
            )
          else ...[
            SwitchListTile(
              secondary: const Icon(Icons.sync),
              title: Text(context.t('sync_auto')),
              subtitle: Text(context.t('sync_auto_help')),
              value: scope.prefs.cloudSync,
              onChanged: (v) {
                scope.prefs.cloudSync = v;
                if (v) _run(context);
              },
            ),
            ListTile(
              leading: cloud.running ? const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.cloud_sync_outlined),
              title: Text(context.t('sync_now')),
              subtitle: Text(cloud.lastError != null
                  ? context.t(cloud.lastError!)
                  : cloud.lastRun != null
                      ? context.t('sync_last', {'t': TimeOfDay.fromDateTime(cloud.lastRun!).format(context)})
                      : context.t('sync_e2e')),
              onTap: cloud.running ? null : () => _run(context),
            ),
            ListTile(
              leading: const Icon(Icons.delete_forever_outlined),
              title: Text(context.t('sync_wipe')),
              subtitle: Text(context.t('sync_wipe_help'), style: small),
              onTap: () => _wipe(context),
            ),
          ],
        ]);
      },
    );
  }

  Future<void> _signIn(BuildContext context, String provider) async {
    final messenger = ScaffoldMessenger.of(context);
    final t = context.t;
    try {
      await AppScope.of(context).account.signIn(provider);
    } on AccountError catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(t(e.code))));
    } catch (_) {
      messenger.showSnackBar(SnackBar(content: Text(t('acc_failed'))));
    }
  }

  Future<void> _signOut(BuildContext context) async {
    final scope = AppScope.of(context);
    scope.prefs.cloudSync = false;
    await scope.cloud.forget();
    await scope.account.signOut();
  }

  Future<void> _askPhrase(BuildContext context) async {
    final scope = AppScope.of(context);
    final ctrl = TextEditingController();
    final messenger = ScaffoldMessenger.of(context);
    final t = context.t;
    final phrase = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(builder: (context, setLocal) {
        final ok = ctrl.text.trim().length >= 8;
        return AlertDialog(
          title: Text(context.t('sync_phrase_title')),
          content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(context.t('sync_phrase_rules'), style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 8),
            TextField(
              controller: ctrl,
              obscureText: true,
              autofocus: true,
              onChanged: (_) => setLocal(() {}),
              decoration: InputDecoration(labelText: context.t('sync_phrase'), helperText: context.t('sync_phrase_min')),
            ),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
            FilledButton(onPressed: ok ? () => Navigator.pop(context, ctrl.text.trim()) : null, child: Text(context.t('save'))),
          ],
        );
      }),
    );
    if (phrase == null) return;
    messenger.showSnackBar(SnackBar(content: Text(t('sync_deriving')), duration: const Duration(seconds: 30)));
    try {
      await scope.cloud.setup(phrase);
      messenger.hideCurrentSnackBar();
      scope.prefs.cloudSync = true;
      await scope.cloud.run();
      messenger.showSnackBar(SnackBar(content: Text(t('sync_ready'))));
    } on SyncError catch (e) {
      messenger.hideCurrentSnackBar();
      messenger.showSnackBar(SnackBar(content: Text(t(e.code))));
    }
  }

  Future<void> _run(BuildContext context) async {
    final scope = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final t = context.t;
    try {
      final n = await scope.cloud.run();
      messenger.showSnackBar(SnackBar(content: Text(t('sync_done', {'n': '$n'}))));
    } on SyncError catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(t(e.code))));
    }
  }

  Future<void> _wipe(BuildContext context) async {
    final scope = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final t = context.t;
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.warning_amber),
        title: Text(context.t('sync_wipe')),
        content: Text(context.t('sync_wipe_confirm')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(context.t('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(context.t('delete'))),
        ],
      ),
    );
    if (yes != true) return;
    try {
      scope.prefs.cloudSync = false;
      await scope.cloud.wipeRemote();
      messenger.showSnackBar(SnackBar(content: Text(t('sync_wiped'))));
    } on SyncError catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(t(e.code))));
    }
  }
}
