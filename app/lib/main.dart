// Tontolo — application Flutter (Android + Linux).
// L'interface s'affiche immédiatement ; le cœur Python démarre en arrière-plan.

import 'dart:io';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'core/backend.dart';
import 'core/chat_controller.dart';
import 'core/prefs.dart';
import 'core/stats.dart';
import 'core/updater.dart';
import 'core/whats_new.dart';
import 'l10n/strings.dart';
import 'ui/chat_screen.dart';
import 'core/account.dart';
import 'core/activity.dart';
import 'core/cloud_sync.dart';
import 'core/notifier.dart';
import 'ui/creations_screen.dart';
import 'ui/onboarding.dart';
import 'ui/search_dialog.dart';
import 'ui/update_sheet.dart';
import 'ui/settings_screen.dart';
import 'ui/theme.dart';

/// Synchronisation silencieuse (démarrage, retour au premier plan) si elle est activée.
void syncSoon(Prefs prefs, Account account, CloudSync cloud) {
  if (!prefs.cloudSync || !account.signedIn || !cloud.ready) return;
  cloud.run().catchError((_) => 0);
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await Prefs.load();
  final backend = Backend(prefs);
  final updater = Updater(prefs);
  final chat = ChatController(backend);
  final account = Account();
  final cloud = CloudSync(backend, account);
  final activity = ActivityWatcher(backend, cloud, chat);
  await Future.wait([account.load(), cloud.load()]).catchError((_) => <void>[]);
  runApp(AppScope(prefs: prefs, backend: backend, updater: updater, chat: chat, account: account, cloud: cloud, activity: activity, child: const TontoloApp()));
  backend.start().then((_) {
    activity.start();
    syncSoon(prefs, account, cloud);
    updater.startAuto();
    Stats.maybeSend(prefs);
    // Langue de réponse par défaut du moteur = langue de l'interface.
    if (backend.state == BackendState.ready) {
      backend.sendJson('PUT', '/tontolo/settings', {'language': prefs.locale}).catchError((_) => null);
    }
  });
}

class AppScope extends InheritedWidget {
  const AppScope({
    super.key,
    required this.prefs,
    required this.backend,
    required this.updater,
    required this.chat,
    required this.account,
    required this.cloud,
    required this.activity,
    required super.child,
  });

  final Prefs prefs;
  final Backend backend;
  final Updater updater;
  final ChatController chat;
  final Account account;
  final CloudSync cloud;
  final ActivityWatcher activity;

  static AppScope of(BuildContext context) => context.dependOnInheritedWidgetOrNull<AppScope>()!;

  @override
  bool updateShouldNotify(AppScope oldWidget) => false;
}

extension TrX on BuildContext {
  String t(String key, [Map<String, String> args = const {}]) =>
      tr(dependOnInheritedWidgetOfExactType<AppScope>()?.prefs.locale ?? 'fr', key, args);
}

extension on BuildContext {
  T? dependOnInheritedWidgetOrNull<T extends InheritedWidget>() => dependOnInheritedWidgetOfExactType<T>();
}

class TontoloApp extends StatelessWidget {
  const TontoloApp({super.key});

  @override
  Widget build(BuildContext context) {
    final prefs = AppScope.of(context).prefs;
    return ListenableBuilder(
      listenable: prefs,
      builder: (context, _) => MaterialApp(
        title: 'Tontolo',
        debugShowCheckedModeBanner: false,
        themeMode: prefs.themeMode,
        theme: buildTheme(Brightness.light, reduceMotion: prefs.reduceMotion),
        darkTheme: buildTheme(Brightness.dark, reduceMotion: prefs.reduceMotion),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(prefs.textScale)),
          child: child!,
        ),
        home: prefs.onboarded ? const Shell() : const Onboarding(),
      ),
    );
  }
}

/// Navigation entre Discussion / Créations / Réglages, accessible depuis les écrans enfants.
class ShellNav extends InheritedWidget {
  const ShellNav({super.key, required this.index, required this.go, required this.wide, required super.child});

  final int index;
  final ValueChanged<int> go;
  final bool wide;

  static ShellNav? maybeOf(BuildContext context) => context.dependOnInheritedWidgetOfExactType<ShellNav>();

  /// Flèche de retour vers la discussion (mobile, hors de l'écran de chat).
  Widget? backButton(BuildContext context) => wide ? null : BackButton(onPressed: () => go(0));

  @override
  bool updateShouldNotify(ShellNav old) => old.index != index || old.wide != wide;
}

/// Coquille adaptative : barre du bas (mobile) ou barre latérale (desktop/tablette).
class Shell extends StatefulWidget {
  const Shell({super.key});

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> with WidgetsBindingObserver {
  int index = 0;
  bool _sheetOpen = false;
  Updater? _updater;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Retour au premier plan : un message en attente de réseau part tout de suite.
    final scope = AppScope.of(context);
    scope.activity.foreground = state == AppLifecycleState.resumed;
    if (state == AppLifecycleState.resumed) {
      scope.activity.poll();
      scope.chat.checkOfflineQueue();
      scope.chat.resumeIfStale(); // réponse générée pendant l'absence : on s'y rattache
      syncSoon(scope.prefs, scope.account, scope.cloud);
      _startLive(scope);
    } else if (state == AppLifecycleState.paused) {
      scope.cloud.stopLive(); // en arrière-plan : pas de synchro périodique
    }
  }

  /// Synchro toutes les ~20 s tant que l'application est ouverte : discussions, créations et
  /// tâches en cours suivies d'un appareil à l'autre.
  void _startLive(AppScope scope) {
    scope.cloud.startLive(() => scope.prefs.cloudSync && scope.account.signedIn);
  }

  CloudSync? _cloud;

  /// Une discussion attend la réponse de l'utilisateur alors qu'il est ailleurs : bandeau
  /// avec « Ouvrir » (application ouverte) ou notification (arrière-plan).
  void _attention(String id, String title, String reason) {
    if (!mounted) return;
    final scope = AppScope.of(context);
    final label = context.t('attention_$reason', {'t': title.isEmpty ? '…' : title});
    if (!scope.activity.foreground) {
      Notifier.attention('attention-$id', 'Tontolo', label);
      return;
    }
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(label),
        duration: const Duration(seconds: 12),
        action: SnackBarAction(
          label: context.t('open'),
          onPressed: () {
            setState(() => index = 0);
            scope.chat.open(id);
          },
        ),
      ));
  }

  void _onCloud() {
    final scope = AppScope.of(context);
    final chat = scope.chat;
    final id = chat.conversationId;
    // La discussion affichée a reçu la suite depuis un autre appareil : on la recharge.
    if (id != null && !chat.busy && scope.cloud.lastImported.contains(id)) {
      scope.cloud.lastImported = {};
      chat.open(id);
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Après le premier affichage : nouveautés de la version (après mise à jour) et annonce
    // d'une nouvelle version dès qu'elle est prête.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _cloud = AppScope.of(context).cloud..addListener(_onCloud);
      AppScope.of(context).activity.onAttention = _attention;
      _startLive(AppScope.of(context));
      _updater = AppScope.of(context).updater..addListener(_onUpdate);
      _maybeWhatsNew();
      _onUpdate();
      _listenShortcut();
    });
  }

  /// Raccourci d'appui long et widget « Demander à Tontolo » (Android) : nouvelle discussion,
  /// clavier prêt ; que l'application soit fermée (« initialAsk ») ou déjà ouverte (« ask »).
  void _listenShortcut() {
    if (kIsWeb || !Platform.isAndroid) return;
    const channel = MethodChannel('tontolo/shortcut');
    channel.setMethodCallHandler((call) async {
      if (call.method == 'ask' && mounted) _ask();
    });
    channel.invokeMethod<bool>('initialAsk').then((asked) {
      if (asked == true && mounted) _ask();
    }).catchError((Object _) {});
  }

  void _ask() {
    final chat = AppScope.of(context).chat;
    if (!chat.busy) chat.newChat();
    setState(() => index = 0);
    chat.requestInputFocus();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _updater?.removeListener(_onUpdate);
    _cloud?.removeListener(_onCloud);
    _cloud?.stopLive();
    super.dispose();
  }

  Future<void> _maybeWhatsNew() async {
    final prefs = AppScope.of(context).prefs;
    if (prefs.lastSeenVersion == appVersion) return;
    final since = prefs.lastSeenVersion;
    prefs.lastSeenVersion = appVersion;
    // 1re installation : l'accueil suffit. Après un saut de plusieurs versions, on présente
    // toutes les nouveautés intermédiaires.
    if (since.isEmpty || newsBetween(since, appVersion).isEmpty) return;
    _sheetOpen = true;
    await showWhatsNew(context, since: since);
    _sheetOpen = false;
  }

  Future<void> _onUpdate() async {
    final up = AppScope.of(context).updater;
    final prefs = AppScope.of(context).prefs;
    if (_sheetOpen || up.status != UpdateStatus.ready || up.latest == null) return;
    if (prefs.promptedUpdate == up.latest) return; // annoncé une seule fois par version
    prefs.promptedUpdate = up.latest!;
    _sheetOpen = true;
    await showUpdateSheet(context);
    _sheetOpen = false;
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 840;
    final pages = [const ChatScreen(), const CreationsScreen(), const SettingsScreen()];
    final destinations = [
      (Icons.chat_bubble_outline, Icons.chat_bubble, context.t('chat')),
      (Icons.photo_library_outlined, Icons.photo_library, context.t('creations')),
      (Icons.settings_outlined, Icons.settings, context.t('settings')),
    ];
    final body = AnimatedSwitcher(duration: context.motion, child: KeyedSubtree(key: ValueKey(index), child: pages[index]));
    return ShellNav(
      index: index,
      wide: wide,
      go: (i) => setState(() => index = i),
      // Retour système depuis Créations/Réglages : revient à la discussion au lieu de quitter.
      child: PopScope(
      canPop: index == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) setState(() => index = 0);
      },
      child: CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyK, control: true): () => showSearchDialog(context),
        const SingleActivator(LogicalKeyboardKey.keyN, control: true): () {
          AppScope.of(context).chat.newChat();
          setState(() => index = 0);
        },
      },
      child: Focus(
        autofocus: true,
        child: wide
            ? Scaffold(
                body: Row(children: [
                  NavigationRail(
                    selectedIndex: index,
                    onDestinationSelected: (i) => setState(() => index = i),
                    labelType: NavigationRailLabelType.all,
                    leading: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      child: Image.asset('assets/icon.png', width: 40, height: 40),
                    ),
                    destinations: [
                      for (final d in destinations)
                        NavigationRailDestination(icon: Icon(d.$1), selectedIcon: Icon(d.$2), label: Text(d.$3)),
                    ],
                  ),
                  const VerticalDivider(width: 1),
                  Expanded(child: body),
                ]),
              )
            : Scaffold(body: body), // mobile : Créations et Réglages sont dans le volet des discussions
      ),
    )));
  }
}
