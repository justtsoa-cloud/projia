// Continuer dans Tontolo une discussion commencée ailleurs (Claude, ChatGPT, Gemini) :
// lien de partage collé dans le chat ou dans « Importer une discussion », texte collé ou
// fichier d'export. Les pages Claude et Gemini ne livrent leurs données qu'à un vrai
// navigateur : sur Android elles sont ouvertes dans une vue web (l'utilisateur voit la page
// et peut passer une vérification « je ne suis pas un robot ») ; ailleurs, l'utilisateur
// ouvre le lien dans son navigateur et colle le contenu.

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../main.dart';

/// Liens de discussion reconnus (partage Claude/ChatGPT/Gemini, ou lien Claude privé).
final shareLink = RegExp(
    r'https?://(?:www\.)?(?:claude\.ai/(?:share|chat)/[0-9a-f-]{36}|'
    r'(?:chatgpt\.com|chat\.openai\.com)/share/[0-9a-f-]{36}|'
    r'(?:gemini\.google\.com/share|g\.co/gemini/share)/[0-9A-Za-z_-]{6,64})',
    caseSensitive: false);

const _maxData = 4000000;

Map<String, dynamic>? _errorBody(Object e) {
  final s = '$e';
  final i = s.indexOf('{');
  if (i < 0) return null;
  try {
    final detail = (jsonDecode(s.substring(i)) as Map)['detail'];
    return detail is Map ? detail.cast<String, dynamic>() : null;
  } catch (_) {
    return null;
  }
}

/// Importe puis ouvre la discussion ; `followUp` est envoyé ensuite dans la discussion
/// importée (ex. « continue https://claude.ai/share/… et explique la fin »).
Future<bool> importConversation(BuildContext context, {String? url, String? data, String followUp = ''}) async {
  final scope = AppScope.of(context);
  final messenger = ScaffoldMessenger.of(context);
  final t = context.t;
  messenger.showSnackBar(SnackBar(content: Text(t('import_running')), duration: const Duration(seconds: 20)));
  Map<String, dynamic>? res;
  try {
    res = await scope.backend.sendJson('POST', '/tontolo/import', {'url': ?url, 'data': ?data})
        as Map<String, dynamic>;
  } catch (e) {
    messenger.hideCurrentSnackBar();
    final err = _errorBody(e);
    final code = err?['code'] as String? ?? '';
    if (!context.mounted) return false;
    if (code == 'import_browser') {
      final got = await _viaBrowser(context, err!);
      if (got == null || !context.mounted) return false;
      return importConversation(context, data: got, followUp: followUp);
    }
    if (code == 'import_private') {
      await _explainPrivate(context);
      return false;
    }
    final known = {'import_empty', 'import_not_found', 'import_too_big', 'import_network', 'import_unsupported'};
    messenger.showSnackBar(SnackBar(content: Text(known.contains(code) ? t(code) : t('import_failed'))));
    return false;
  }
  messenger.hideCurrentSnackBar();
  final convs = (res['conversations'] as List).cast<Map<String, dynamic>>();
  if (convs.isEmpty) return false;
  final first = convs.first;
  await scope.chat.open('${first['id']}');
  scope.chat.addNotice('imported|${first['count']}|${first['source']}|${convs.length}');
  if (followUp.trim().isNotEmpty) scope.chat.send(followUp.trim());
  return true;
}

Future<String?> _viaBrowser(BuildContext context, Map<String, dynamic> err) {
  if (Platform.isAndroid) {
    return Navigator.of(context).push<String>(MaterialPageRoute(
      builder: (_) => WebImportPage(
        pageUrl: '${err['page_url']}',
        apiUrl: err['api_url'] as String?,
        extract: '${err['extract']}',
        script: err['script'] as String?,
      ),
    ));
  }
  return _pasteFromBrowser(context, (err['api_url'] ?? err['page_url']) as String);
}

/// Hors Android : ouvrir le lien dans le navigateur, tout copier, coller ici.
Future<String?> _pasteFromBrowser(BuildContext context, String link) {
  final ctrl = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(context.t('import_title')),
      content: SizedBox(
        width: 480,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(context.t('import_paste_steps')),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            icon: const Icon(Icons.open_in_new),
            label: Text(context.t('import_open_browser')),
            onPressed: () => launchUrl(Uri.parse(link), mode: LaunchMode.externalApplication),
          ),
          const SizedBox(height: 8),
          TextField(controller: ctrl, maxLines: 6, decoration: InputDecoration(hintText: context.t('import_paste_hint'), border: const OutlineInputBorder())),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
        FilledButton(onPressed: () => Navigator.pop(context, ctrl.text.trim().isEmpty ? null : ctrl.text), child: Text(context.t('import_do'))),
      ],
    ),
  );
}

Future<void> _explainPrivate(BuildContext context) => showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        icon: const Icon(Icons.lock_outline),
        title: Text(context.t('import_private_title')),
        content: Text(context.t('import_private')),
        actions: [FilledButton(onPressed: () => Navigator.pop(context), child: Text(context.t('ok')))],
      ),
    );

/// « Importer une discussion » (volet) : lien, texte collé ou fichier d'export.
Future<void> showImportDialog(BuildContext context) async {
  final ctrl = TextEditingController();
  final result = await showDialog<(String, bool)>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(context.t('import_title')),
      content: SizedBox(
        width: 480,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(context.t('import_help')),
          const SizedBox(height: 10),
          TextField(
            controller: ctrl,
            autofocus: true,
            minLines: 2,
            maxLines: 6,
            decoration: InputDecoration(hintText: context.t('import_hint'), border: const OutlineInputBorder()),
          ),
          const SizedBox(height: 8),
          TextButton.icon(
            icon: const Icon(Icons.upload_file),
            label: Text(context.t('import_file')),
            onPressed: () async {
              final picked = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: const ['json', 'txt', 'md']);
              if (picked.isEmpty) return;
              final bytes = await picked.first.xFile.readAsBytes();
              if (!context.mounted) return;
              if (bytes.length > _maxData) {
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.t('import_too_big'))));
                return;
              }
              Navigator.pop(context, (utf8.decode(bytes, allowMalformed: true), false));
            },
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
        FilledButton(
          onPressed: () {
            final v = ctrl.text.trim();
            if (v.isEmpty) return;
            final link = shareLink.firstMatch(v);
            Navigator.pop(context, link != null && v.length < link.group(0)!.length + 40 ? (link.group(0)!, true) : (v, false));
          },
          child: Text(context.t('import_do')),
        ),
      ],
    ),
  );
  if (result == null || !context.mounted) return;
  final (value, isLink) = result;
  await importConversation(context, url: isLink ? value : null, data: isLink ? null : value);
}

/// Vue web qui ouvre le lien de partage comme un navigateur ordinaire, puis récupère la
/// discussion (API JSON de la page, script d'extraction ou texte visible).
class WebImportPage extends StatefulWidget {
  const WebImportPage({super.key, required this.pageUrl, required this.extract, this.apiUrl, this.script});

  final String pageUrl;
  final String extract; // fetch_json | script | page_text
  final String? apiUrl;
  final String? script;

  @override
  State<WebImportPage> createState() => _WebImportPageState();
}

class _WebImportPageState extends State<WebImportPage> {
  late final WebViewController web;
  Timer? _poll;
  int _tries = 0;
  bool _done = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel('TontoloImport', onMessageReceived: (m) => _received(m.message))
      ..setNavigationDelegate(NavigationDelegate(
        // Uniquement des pages web : pas d'ouverture d'applications (intent://, market://…).
        onNavigationRequest: (r) => r.url.startsWith('https://') ? NavigationDecision.navigate : NavigationDecision.prevent,
        onPageFinished: (_) => _start(),
      ))
      ..loadRequest(Uri.parse(widget.pageUrl));
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  void _start() {
    _poll ??= Timer.periodic(const Duration(seconds: 3), (_) => _tryExtract());
    _tryExtract();
  }

  void _tryExtract() {
    if (_done) return;
    if (++_tries > 20) {
      _poll?.cancel();
      setState(() => _failed = true);
      return;
    }
    final js = switch (widget.extract) {
      'fetch_json' => "fetch(${jsonEncode(widget.apiUrl)}, {credentials: 'include'})"
          ".then(r => r.ok ? r.text() : Promise.reject(r.status))"
          ".then(t => TontoloImport.postMessage(t)).catch(e => TontoloImport.postMessage('ERR:' + e));",
      'script' => 'TontoloImport.postMessage(${widget.script});',
      _ => 'TontoloImport.postMessage(document.body ? document.body.innerText : "");',
    };
    web.runJavaScript(js).catchError((_) {});
  }

  void _received(String data) {
    if (_done || data.startsWith('ERR:') || data.length > _maxData) return;
    final trimmed = data.trim();
    final useful = switch (widget.extract) {
      'fetch_json' => trimmed.startsWith('{') && trimmed.contains('chat_messages'),
      'script' => trimmed.startsWith('[') && trimmed != '[]',
      _ => trimmed.length > 200,
    };
    if (!useful) return;
    _done = true;
    _poll?.cancel();
    if (mounted) Navigator.pop(context, trimmed);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.t('import_title')),
        bottom: _failed
            ? null
            : const PreferredSize(preferredSize: Size.fromHeight(3), child: LinearProgressIndicator(minHeight: 3)),
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
          child: Text(_failed ? context.t('import_web_failed') : context.t('import_web_wait'),
              style: Theme.of(context).textTheme.bodySmall),
        ),
        if (_failed)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: FilledButton.tonal(
              onPressed: () {
                setState(() {
                  _failed = false;
                  _tries = 0;
                });
                _poll?.cancel();
                _poll = null;
                _start();
              },
              child: Text(context.t('retry')),
            ),
          ),
        Expanded(child: WebViewWidget(controller: web)),
      ]),
    );
  }
}
