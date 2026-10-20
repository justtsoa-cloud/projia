// Export d'une discussion en page web autonome (un seul fichier HTML, sans dépendance).
// Sécurité : la page interdit tout script (Content-Security-Policy) et le HTML brut écrit
// par les modèles est neutralisé : on peut l'ouvrir et la partager sans risque.

import 'dart:convert';

import 'package:markdown/markdown.dart' as md;

import 'author.dart';
import 'chat_controller.dart';

String _escape(String s) => const HtmlEscape().convert(s);

/// Markdown → HTML sans balises brutes (le texte « <script> » reste du texte).
String safeMarkdown(String text) {
  final escaped = text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  final html = md.markdownToHtml(escaped, extensionSet: md.ExtensionSet.gitHubFlavored);
  // Liens : seulement http(s), jamais javascript: ni data:.
  return html.replaceAllMapped(RegExp(r'href="(?!https?://)[^"]*"'), (_) => 'href="#"');
}

String conversationHtml(List<ChatMessage> messages, {required String title, required String locale}) {
  final buf = StringBuffer()
    ..writeln('<!doctype html><html lang="$locale"><head><meta charset="utf-8">')
    ..writeln('<meta name="viewport" content="width=device-width, initial-scale=1">')
    ..writeln('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; img-src data:">')
    ..writeln('<title>${_escape(title)}</title><style>')
    ..writeln(':root{--bg:#f7f6fb;--card:#fff;--me:#e1e3fb;--ink:#1d1b26;--muted:#6b6880;--accent:#4b4fa0}'
        '@media(prefers-color-scheme:dark){:root{--bg:#141320;--card:#1f1e2c;--me:#2d3060;--ink:#ecebf5;--muted:#a7a4bd;--accent:#aab0ff}}'
        'body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}'
        'main{max-width:760px;margin:0 auto;padding:24px 16px}h1{font-size:1.3rem;margin:0 0 4px}'
        '.meta{color:var(--muted);font-size:.85rem;margin-bottom:20px}'
        '.msg{background:var(--card);border-radius:16px;padding:12px 16px;margin:10px 0;overflow-x:auto}'
        '.me{background:var(--me);margin-left:15%}.model{color:var(--muted);font-size:.78rem;margin-top:6px}'
        'pre{background:rgba(127,127,127,.12);padding:10px;border-radius:8px;overflow-x:auto}'
        'code{font-family:ui-monospace,monospace;font-size:.9em}table{border-collapse:collapse}'
        'td,th{border:1px solid rgba(127,127,127,.35);padding:4px 8px}a{color:var(--accent)}'
        'footer{color:var(--muted);font-size:.8rem;margin-top:28px;text-align:center}')
    ..writeln('</style></head><body><main>')
    ..writeln('<h1>${_escape(title)}</h1><div class="meta">Projia · ${DateTime.now().toIso8601String().substring(0, 10)}</div>');
  for (final m in messages) {
    if (m.role != 'user' && m.role != 'assistant') continue;
    if (m.text.trim().isEmpty) continue;
    final cls = m.role == 'user' ? 'msg me' : 'msg';
    buf.writeln('<div class="$cls">${safeMarkdown(m.text)}');
    if (m.role == 'assistant' && (m.modelName ?? m.model) != null) {
      buf.writeln('<div class="model">${_escape(m.modelName ?? m.model!)}</div>');
    }
    buf.writeln('</div>');
  }
  buf.writeln('<footer>Projia — $authorName · $authorGithub</footer></main></body></html>');
  return buf.toString();
}
