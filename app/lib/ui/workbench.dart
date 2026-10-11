// Plan de travail à côté de la discussion (écrans larges) :
// - Terminal (bureau Linux) : UNE session par discussion, ouverte dans le dossier de travail ;
//   les commandes lancées par l'agent (après confirmation) y apparaissent avec leur sortie,
//   et l'utilisateur peut y taper ses propres commandes.
// - Navigateur (tablette Android) : panneau WebView piloté par l'agent (pont avec le cœur),
//   UN onglet par discussion, réutilisé à chaque commande (6 au plus, le plus ancien fermé).
//   Sur le bureau, l'agent pilote un vrai navigateur Chromium dans sa propre fenêtre.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_pty/flutter_pty.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:xterm/xterm.dart';

import '../core/backend.dart';
import '../core/chat_controller.dart';
import '../main.dart';

const maxSessions = 6;

bool get terminalSupported => !kIsWeb && Platform.isLinux;

/// Tablette Android : écran assez grand pour un panneau navigateur.
bool browserPanelSupported(BuildContext context) =>
    !kIsWeb && Platform.isAndroid && MediaQuery.sizeOf(context).shortestSide >= 600;

// --- Terminal --------------------------------------------------------------------------

class TermSession {
  TermSession(this.terminal, this.pty);
  final Terminal terminal;
  final Pty pty;
  DateTime used = DateTime.now();
}

class Terminals extends ChangeNotifier {
  Terminals._();
  static final instance = Terminals._();

  final Map<String, TermSession> sessions = {};

  TermSession session(String key, String? cwd) {
    final s = sessions[key];
    if (s != null) {
      s.used = DateTime.now();
      return s;
    }
    if (sessions.length >= maxSessions) {
      final oldest = sessions.entries.reduce((a, b) => a.value.used.isBefore(b.value.used) ? a : b);
      oldest.value.pty.kill();
      sessions.remove(oldest.key);
    }
    final terminal = Terminal(maxLines: 5000);
    final shell = Platform.environment['SHELL'] ?? '/bin/bash';
    final dir = cwd != null && Directory(cwd).existsSync() ? cwd : Platform.environment['HOME'];
    final pty = Pty.start(shell, workingDirectory: dir, columns: terminal.viewWidth, rows: terminal.viewHeight);
    pty.output.cast<List<int>>().transform(const Utf8Decoder(allowMalformed: true)).listen(terminal.write);
    pty.exitCode.then((code) {
      terminal.write('\r\n[session terminée : $code]\r\n');
      sessions.remove(key);
      notifyListeners();
    });
    terminal.onOutput = (data) => pty.write(const Utf8Encoder().convert(data));
    terminal.onResize = (w, h, pw, ph) => pty.resize(h, w);
    final created = TermSession(terminal, pty);
    sessions[key] = created;
    return created;
  }

  /// Commande de l'agent (déjà confirmée et exécutée par le cœur) : affichée dans la session
  /// de la discussion, sans ouvrir de nouvel onglet.
  void agentCommand(String key, String? cwd, String command, String output) {
    final t = session(key, cwd).terminal;
    t.write('\r\n\x1b[36m[agent] \$ $command\x1b[0m\r\n');
    t.write('${output.replaceAll('\r\n', '\n').replaceAll('\n', '\r\n')}\r\n');
    notifyListeners();
  }

  void close(String key) {
    sessions.remove(key)?.pty.kill();
    notifyListeners();
  }
}

class TerminalPane extends StatefulWidget {
  const TerminalPane({super.key, required this.chat});
  final ChatController chat;

  @override
  State<TerminalPane> createState() => _TerminalPaneState();
}

class _TerminalPaneState extends State<TerminalPane> {
  String? cwd;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _loadCwd();
  }

  Future<void> _loadCwd() async {
    try {
      final ws = await AppScope.of(context).backend.getJson('/tontolo/workspace') as Map<String, dynamic>;
      if (mounted) setState(() => cwd = ws['path'] as String?);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final key = widget.chat.conversationId ?? '_';
    return ListenableBuilder(
      listenable: Terminals.instance,
      builder: (context, _) {
        final s = Terminals.instance.session(key, cwd);
        return Column(children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: Row(children: [
              const Icon(Icons.folder_outlined, size: 16),
              const SizedBox(width: 6),
              Expanded(
                child: Text(cwd ?? context.t('terminal_home'),
                    maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
              ),
              IconButton(
                tooltip: context.t('terminal_restart'),
                icon: const Icon(Icons.restart_alt, size: 18),
                onPressed: () => Terminals.instance.close(key),
              ),
            ]),
          ),
          Expanded(child: TerminalView(s.terminal, autofocus: true, padding: const EdgeInsets.all(6))),
        ]);
      },
    );
  }
}

// --- Navigateur (tablette) -------------------------------------------------------------

class BrowserTab {
  BrowserTab(this.controller);
  final WebViewController controller;
  Completer<void>? loading;
  DateTime used = DateTime.now();
  String url = '';
}

/// Pont avec le cœur : lit les commandes de l'agent et les exécute dans la WebView.
class BrowserBridge extends ChangeNotifier {
  BrowserBridge._();
  static final instance = BrowserBridge._();

  final Map<String, BrowserTab> tabs = {};
  String? current;
  bool _running = false;
  bool wantsPanel = false; // une commande est arrivée : le panneau doit s'afficher

  void start(Backend backend) {
    if (_running) return;
    _running = true;
    _loop(backend);
  }

  void stop() => _running = false;

  BrowserTab tab(String key) {
    final existing = tabs[key];
    if (existing != null) {
      existing.used = DateTime.now();
      return existing;
    }
    if (tabs.length >= maxSessions) {
      final oldest = tabs.entries.reduce((a, b) => a.value.used.isBefore(b.value.used) ? a : b).key;
      tabs.remove(oldest);
    }
    late final BrowserTab t;
    final controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (url) {
          t.url = url;
          t.loading ??= Completer<void>();
          notifyListeners();
        },
        onPageFinished: (url) {
          t.url = url;
          final c = t.loading;
          t.loading = null;
          if (c != null && !c.isCompleted) c.complete();
          notifyListeners();
        },
        // Seules les pages web : pas d'ouverture d'applications ni de schémas exotiques.
        onNavigationRequest: (r) => r.url.startsWith('http://') || r.url.startsWith('https://') || r.url == 'about:blank'
            ? NavigationDecision.navigate
            : NavigationDecision.prevent,
      ));
    t = BrowserTab(controller);
    tabs[key] = t;
    return t;
  }

  Future<void> _loop(Backend backend) async {
    while (_running) {
      if (backend.state != BackendState.ready) {
        await Future<void>.delayed(const Duration(seconds: 3));
        continue;
      }
      try {
        final r = await backend.getJson('/tontolo/browser/next', {'wait': 25}) as Map<String, dynamic>;
        final cmd = (r['command'] as Map?)?.cast<String, dynamic>();
        if (cmd == null) continue;
        Map<String, dynamic> data;
        try {
          data = await _execute(cmd);
        } catch (e) {
          data = {'error': '$e'};
        }
        await backend.sendJson('POST', '/tontolo/browser/result', {'id': cmd['id'], 'data': data});
      } catch (_) {
        await Future<void>.delayed(const Duration(seconds: 3));
      }
    }
  }

  Future<void> _waitLoaded(BrowserTab t) async {
    await Future<void>.delayed(const Duration(milliseconds: 300));
    final c = t.loading;
    if (c != null) await c.future.timeout(const Duration(seconds: 20), onTimeout: () {});
  }

  Future<Object?> _js(WebViewController c, String script) async {
    final raw = await c.runJavaScriptReturningResult(script);
    // Android renvoie les chaînes encodées en JSON (avec leurs guillemets).
    if (raw is String && raw.startsWith('"')) {
      try {
        return jsonDecode(raw);
      } catch (_) {}
    }
    return raw;
  }

  Future<Map<String, dynamic>> _execute(Map<String, dynamic> cmd) async {
    final key = '${cmd['conversation_id']}';
    final args = (cmd['args'] as Map?)?.cast<String, dynamic>() ?? const {};
    final t = tab(key);
    current = key;
    wantsPanel = true;
    notifyListeners();
    final c = t.controller;
    switch (cmd['action']) {
      case 'open':
        t.loading = Completer<void>();
        await c.loadRequest(Uri.parse('${args['url']}'));
        await _waitLoaded(t);
      case 'back':
        if (await c.canGoBack()) {
          t.loading = Completer<void>();
          await c.goBack();
          await _waitLoaded(t);
        }
      case 'click':
        final out = await _js(c, '(${cmd['click_js']})(${jsonEncode(args['id'])}, ${jsonEncode(args['text'] ?? '')})');
        if (out == 'introuvable') return {'error': 'élément introuvable : relis la page (browser_read)'};
        await _waitLoaded(t);
      case 'type':
        final out = await _js(c, '(${cmd['type_js']})(${jsonEncode(args['id'])}, ${jsonEncode('${args['text'] ?? ''}')}, ${jsonEncode(args['submit'] == true)})');
        if (out != 'ok') return {'error': '$out'};
        if (args['submit'] == true) await _waitLoaded(t);
      case 'scroll':
        await c.runJavaScript('window.scrollBy(0, window.innerHeight * 0.9)');
    }
    final page = await _js(c, '${cmd['read_js']}');
    return (jsonDecode('$page') as Map).cast<String, dynamic>();
  }
}

class BrowserPane extends StatefulWidget {
  const BrowserPane({super.key, required this.chat});
  final ChatController chat;

  @override
  State<BrowserPane> createState() => _BrowserPaneState();
}

class _BrowserPaneState extends State<BrowserPane> {
  final url = TextEditingController();

  @override
  void dispose() {
    url.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bridge = BrowserBridge.instance;
    return ListenableBuilder(
      listenable: bridge,
      builder: (context, _) {
        final key = widget.chat.conversationId ?? bridge.current ?? '_';
        final t = bridge.tab(key);
        if (!url.selection.isValid) url.text = t.url;
        return Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
            child: Row(children: [
              IconButton(
                icon: const Icon(Icons.arrow_back, size: 20),
                onPressed: () async {
                  if (await t.controller.canGoBack()) await t.controller.goBack();
                },
              ),
              Expanded(
                child: TextField(
                  controller: url,
                  keyboardType: TextInputType.url,
                  decoration: InputDecoration(isDense: true, hintText: context.t('browser_url')),
                  onSubmitted: (v) {
                    final u = v.contains('://') ? v : 'https://$v';
                    if (u.startsWith('http')) t.controller.loadRequest(Uri.parse(u));
                  },
                ),
              ),
              IconButton(icon: const Icon(Icons.refresh, size: 20), onPressed: t.controller.reload),
            ]),
          ),
          if (t.loading != null) const LinearProgressIndicator(minHeight: 2),
          Expanded(child: WebViewWidget(controller: t.controller)),
        ]);
      },
    );
  }
}

// --- Plan de travail -------------------------------------------------------------------

class Workbench extends StatefulWidget {
  const Workbench({super.key, required this.chat, required this.onClose});
  final ChatController chat;
  final VoidCallback onClose;

  @override
  State<Workbench> createState() => _WorkbenchState();
}

class _WorkbenchState extends State<Workbench> {
  int tab = 0;

  @override
  Widget build(BuildContext context) {
    final browser = browserPanelSupported(context);
    final terminal = terminalSupported;
    final panes = [
      if (browser) (Icons.public, context.t('browser'), BrowserPane(chat: widget.chat)),
      if (!browser) (Icons.public, context.t('browser'), const _DesktopBrowserInfo()),
      if (terminal) (Icons.terminal, context.t('terminal'), TerminalPane(chat: widget.chat)),
    ];
    final i = tab.clamp(0, panes.length - 1);
    return Material(
      child: Column(children: [
        Row(children: [
          const SizedBox(width: 8),
          for (final (k, p) in panes.indexed)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: ChoiceChip(
                avatar: Icon(p.$1, size: 16),
                label: Text(p.$2),
                selected: k == i,
                onSelected: (_) => setState(() => tab = k),
              ),
            ),
          const Spacer(),
          IconButton(icon: const Icon(Icons.close), tooltip: context.t('close'), onPressed: widget.onClose),
        ]),
        const Divider(height: 1),
        Expanded(child: IndexedStack(index: i, children: [for (final p in panes) p.$3])),
      ]),
    );
  }
}

/// Bureau : l'agent pilote un vrai navigateur (fenêtre séparée, profil dédié).
class _DesktopBrowserInfo extends StatefulWidget {
  const _DesktopBrowserInfo();

  @override
  State<_DesktopBrowserInfo> createState() => _DesktopBrowserInfoState();
}

class _DesktopBrowserInfoState extends State<_DesktopBrowserInfo> {
  Map<String, dynamic>? status;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    AppScope.of(context).backend.getJson('/tontolo/browser').then((s) {
      if (mounted) setState(() => status = (s as Map).cast<String, dynamic>());
    }).catchError((_) {});
  }

  @override
  Widget build(BuildContext context) {
    final exe = status?['executable'] as String?;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(context.t('browser'), style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text(exe == null
            ? context.t('browser_none')
            : context.t('browser_desktop', {'b': exe.split('/').last, 'n': '${status?['tabs'] ?? 0}'})),
      ]),
    );
  }
}
