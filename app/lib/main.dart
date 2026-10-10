// Tontolo — application Flutter (Android + Linux).
// L'interface s'affiche immédiatement ; le cœur Python démarre en arrière-plan.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'core/backend.dart';
import 'core/chat_controller.dart';
import 'core/prefs.dart';
import 'core/updater.dart';
import 'core/whats_new.dart';
import 'l10n/strings.dart';
import 'ui/chat_screen.dart';
import 'ui/creations_screen.dart';
import 'ui/onboarding.dart';
import 'ui/search_dialog.dart';
import 'ui/update_sheet.dart';
import 'ui/settings_screen.dart';
import 'ui/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await Prefs.load();
  final backend = Backend(prefs);
  final updater = Updater(prefs);
  final chat = ChatController(backend);
  runApp(AppScope(prefs: prefs, backend: backend, updater: updater, chat: chat, child: const TontoloApp()));
  backend.start().then((_) => updater.startAuto());
}

class AppScope extends InheritedWidget {
  const AppScope({
    super.key,
    required this.prefs,
    required this.backend,
    required this.updater,
    required this.chat,
    required super.child,
  });

  final Prefs prefs;
  final Backend backend;
  final Updater updater;
  final ChatController chat;

  static AppScope of(BuildContext context) => context.dependOnInheritedWidgetOrNull<AppScope>()!;

  @override
  bool updateShouldNotify(AppScope oldWidget) => false;
}

extension TrX on BuildContext {
  String t(String key, [Map<String, String> args = const {}]) => tr(AppScope.of(this).prefs.locale, key, args);
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

/// Coquille adaptative : barre du bas (mobile) ou barre latérale (desktop/tablette).
class Shell extends StatefulWidget {
  const Shell({super.key});

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int index = 0;
  bool _sheetOpen = false;
  Updater? _updater;

  @override
  void initState() {
    super.initState();
    // Après le premier affichage : nouveautés de la version (après mise à jour) et annonce
    // d'une nouvelle version dès qu'elle est prête.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _updater = AppScope.of(context).updater..addListener(_onUpdate);
      _maybeWhatsNew();
      _onUpdate();
    });
  }

  @override
  void dispose() {
    _updater?.removeListener(_onUpdate);
    super.dispose();
  }

  Future<void> _maybeWhatsNew() async {
    final prefs = AppScope.of(context).prefs;
    if (prefs.lastSeenVersion == appVersion) return;
    final firstInstall = prefs.lastSeenVersion.isEmpty;
    prefs.lastSeenVersion = appVersion;
    if (firstInstall || newsFor(appVersion).isEmpty) return; // 1re installation : l'accueil suffit
    _sheetOpen = true;
    await showWhatsNew(context);
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
    return CallbackShortcuts(
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
            : Scaffold(
                body: body,
                bottomNavigationBar: NavigationBar(
                  selectedIndex: index,
                  onDestinationSelected: (i) => setState(() => index = i),
                  height: 64,
                  destinations: [
                    for (final d in destinations)
                      NavigationDestination(icon: Icon(d.$1), selectedIcon: Icon(d.$2), label: d.$3),
                  ],
                ),
              ),
      ),
    );
  }
}
