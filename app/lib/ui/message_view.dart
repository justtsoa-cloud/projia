// Rendu d'un message : Markdown, LaTeX ($…$, $$…$$), code avec bouton copier,
// images jointes, créations (image, audio) et sources web.

import 'dart:convert';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:http/http.dart' as http;
import 'package:markdown/markdown.dart' as md;
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/chat_controller.dart';
import '../core/speech.dart';
import '../main.dart';

class MessageView extends StatelessWidget {
  const MessageView({super.key, required this.message, this.onWhy, this.onRegenerate, this.onEdit});

  final ChatMessage message;
  final VoidCallback? onWhy;
  final VoidCallback? onRegenerate; // dernière réponse uniquement
  final VoidCallback? onEdit; // messages de l'utilisateur

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isUser = message.role == 'user';
    final bubble = Container(
      constraints: const BoxConstraints(maxWidth: 760),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: isUser ? scheme.primaryContainer : scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final img in message.images)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.memory(_decodeDataUrl(img), height: 180, cacheHeight: 360, fit: BoxFit.cover),
            ),
          ),
        if (message.text.isEmpty && message.streaming && message.job == null)
          const _TypingSkeleton()
        else if (message.text.isNotEmpty)
          isUser ? SelectableText(message.text) : RichMarkdown(message.text),
        if (message.job != null) MediaResult(job: message.job!),
        if (message.sources.isNotEmpty && !message.streaming) _Sources(message.sources),
      ]),
    );
    final id = message.uid ?? identityHashCode(message).toString();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Column(
        crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          bubble,
          if (isUser && onEdit != null && message.text.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.edit_outlined, size: 18),
              tooltip: context.t('edit'),
              onPressed: onEdit,
              visualDensity: VisualDensity.compact,
            ),
          if (!isUser && !message.streaming && (message.modelName ?? message.model) != null)
            Padding(
              padding: const EdgeInsets.only(left: 8, top: 4),
              child: Wrap(crossAxisAlignment: WrapCrossAlignment.center, children: [
                ActionChip(
                  avatar: const Icon(Icons.info_outline, size: 16),
                  label: Text(message.modelName ?? message.model!, style: const TextStyle(fontSize: 12)),
                  tooltip: context.t('why'),
                  onPressed: onWhy,
                  visualDensity: VisualDensity.compact,
                ),
                if (message.text.isNotEmpty) ...[
                  IconButton(
                    icon: const Icon(Icons.copy, size: 18),
                    tooltip: context.t('copy'),
                    onPressed: () {
                      Clipboard.setData(ClipboardData(text: message.text));
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.t('copied'))));
                    },
                  ),
                  SpeakButton(id: id, text: message.text),
                  IconButton(
                    icon: const Icon(Icons.share_outlined, size: 18),
                    tooltip: context.t('share'),
                    onPressed: () => SharePlus.instance.share(ShareParams(text: message.text)),
                  ),
                ],
                if (onRegenerate != null)
                  IconButton(
                    icon: const Icon(Icons.refresh, size: 18),
                    tooltip: context.t('regenerate'),
                    onPressed: onRegenerate,
                  ),
              ]),
            ),
        ],
      ),
    );
  }
}

/// Bouton lecture / arrêt de la voix (une seule lecture à la fois).
class SpeakButton extends StatelessWidget {
  const SpeakButton({super.key, required this.id, required this.text});
  final String id;
  final String text;

  @override
  Widget build(BuildContext context) {
    final speech = Speech.instance;
    final prefs = AppScope.of(context).prefs;
    return ListenableBuilder(
      listenable: speech,
      builder: (context, _) {
        final on = speech.isSpeaking(id);
        return IconButton(
          icon: Icon(on ? Icons.stop_circle_outlined : Icons.volume_up_outlined, size: 20,
              color: on ? Theme.of(context).colorScheme.error : null),
          tooltip: on ? context.t('stop_reading') : context.t('listen'),
          onPressed: () async {
            final messenger = ScaffoldMessenger.of(context);
            final msg = context.t('tts_unavailable');
            await speech.toggle(id, text, locale: prefs.locale, rate: prefs.speechRate);
            // Échec immédiat ou différé (voix en cours d'installation…) : message clair.
            await Future<void>.delayed(const Duration(seconds: 2));
            if (speech.lastError != null && !speech.isSpeaking(id)) {
              speech.lastError = null;
              messenger.showSnackBar(SnackBar(content: Text(msg)));
            }
          },
        );
      },
    );
  }
}

/// Ouvre un lien uniquement s'il utilise un schéma sûr (pas de intent:, file:, javascript:…).
Future<void> openSafeLink(String? href) async {
  final uri = href == null ? null : Uri.tryParse(href);
  if (uri == null || !const {'http', 'https', 'mailto'}.contains(uri.scheme)) return;
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}

Uint8List _decodeDataUrl(String url) => base64Decode(url.substring(url.indexOf(',') + 1));

class _TypingSkeleton extends StatelessWidget {
  const _TypingSkeleton();

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.08);
    Widget bar(double w) => Container(
        width: w, height: 12, margin: const EdgeInsets.symmetric(vertical: 4),
        decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(6)));
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [bar(220), bar(160), bar(190)]);
  }
}

class _Sources extends StatelessWidget {
  const _Sources(this.sources);
  final List<Map<String, dynamic>> sources;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Wrap(spacing: 6, runSpacing: 6, children: [
          for (final (i, s) in sources.take(6).indexed)
            ActionChip(
              label: Text('[${i + 1}] ${Uri.tryParse('${s['url']}')?.host ?? ''}', style: const TextStyle(fontSize: 12)),
              onPressed: () => openSafeLink('${s['url']}'),
              visualDensity: VisualDensity.compact,
            ),
        ]),
      );
}

/// Markdown avec mathématiques LaTeX et blocs de code copiables.
class RichMarkdown extends StatelessWidget {
  const RichMarkdown(this.data, {super.key});
  final String data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MarkdownBody(
      data: data,
      selectable: true,
      softLineBreak: true,
      onTapLink: (text, href, title) => openSafeLink(href),
      extensionSet: md.ExtensionSet(
        [...md.ExtensionSet.gitHubFlavored.blockSyntaxes, _MathBlockSyntax()],
        [_MathInlineSyntax(), ...md.ExtensionSet.gitHubFlavored.inlineSyntaxes],
      ),
      builders: {'math': _MathBuilder(), 'pre': _CodeBuilder(theme)},
      styleSheet: MarkdownStyleSheet.fromTheme(theme).copyWith(
        code: theme.textTheme.bodyMedium!.copyWith(fontFamily: 'monospace', backgroundColor: theme.colorScheme.surfaceContainerHighest),
        codeblockDecoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(10)),
      ),
    );
  }
}

class _MathInlineSyntax extends md.InlineSyntax {
  _MathInlineSyntax() : super(r'\$\$([^$]+)\$\$|\$([^$\n]+?)\$|\\\((.+?)\\\)');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    final display = match.group(1) != null;
    final tex = match.group(1) ?? match.group(2) ?? match.group(3) ?? '';
    parser.addNode(md.Element.text('math', tex)..attributes['display'] = '$display');
    return true;
  }
}

class _MathBlockSyntax extends md.BlockSyntax {
  @override
  RegExp get pattern => RegExp(r'^\s*(\$\$|\\\[)\s*$');

  @override
  md.Node parse(md.BlockParser parser) {
    parser.advance();
    final lines = <String>[];
    while (!parser.isDone && !RegExp(r'^\s*(\$\$|\\\])\s*$').hasMatch(parser.current.content)) {
      lines.add(parser.current.content);
      parser.advance();
    }
    if (!parser.isDone) parser.advance();
    return md.Element.text('math', lines.join('\n'))..attributes['display'] = 'true';
  }
}

class _MathBuilder extends MarkdownElementBuilder {
  @override
  Widget visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final display = element.attributes['display'] == 'true';
    final math = Math.tex(
      element.textContent,
      mathStyle: display ? MathStyle.display : MathStyle.text,
      textStyle: preferredStyle,
      onErrorFallback: (e) => Text(element.textContent, style: preferredStyle),
    );
    return display
        ? SingleChildScrollView(scrollDirection: Axis.horizontal, child: Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: math))
        : math;
  }
}

class _CodeBuilder extends MarkdownElementBuilder {
  _CodeBuilder(this.theme);
  final ThemeData theme;

  @override
  Widget visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final code = element.textContent.replaceAll(RegExp(r'\n$'), '');
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 6),
      decoration: BoxDecoration(color: theme.colorScheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(10)),
      child: Stack(children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.fromLTRB(12, 12, 44, 12),
          child: SelectableText(code, style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
        ),
        Positioned(
          right: 0, top: 0,
          child: IconButton(
            icon: const Icon(Icons.copy, size: 18),
            tooltip: 'Copier',
            onPressed: () => Clipboard.setData(ClipboardData(text: code)),
          ),
        ),
      ]),
    );
  }
}

/// Résultat média intégré : image zoomable, lecteur audio, partage en un appui.
class MediaResult extends StatefulWidget {
  const MediaResult({super.key, required this.job});
  final Map<String, dynamic> job;

  @override
  State<MediaResult> createState() => _MediaResultState();
}

class _MediaResultState extends State<MediaResult> {
  Uint8List? bytes;
  final player = AudioPlayer();
  bool playing = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  @override
  void didUpdateWidget(MediaResult old) {
    super.didUpdateWidget(old);
    if (old.job['status'] != widget.job['status']) _load();
  }

  @override
  void dispose() {
    player.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (widget.job['status'] != 'done' || bytes != null) return;
    final params = (widget.job['params'] as Map?) ?? {};
    if (params['local_tts'] == true) return;
    final backend = AppScope.of(context).backend;
    final r = await http.get(backend.uri('/tontolo/media/${widget.job['id']}/file'), headers: backend.headers);
    if (r.statusCode == 200 && mounted) setState(() => bytes = r.bodyBytes);
  }

  @override
  Widget build(BuildContext context) {
    final job = widget.job;
    final status = job['status'];
    final params = (job['params'] as Map?)?.cast<String, dynamic>() ?? {};
    if (status == 'failed') {
      return Text('${job['error'] ?? context.t('error_generic')}',
          style: TextStyle(color: Theme.of(context).colorScheme.error));
    }
    if (status != 'done') {
      return Row(mainAxisSize: MainAxisSize.min, children: [
        const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        const SizedBox(width: 10),
        Text(context.t('generating')),
      ]);
    }
    final mime = '${params['mime'] ?? ''}';
    final warning = params['warning'];
    if (params['local_tts'] == true) {
      return SpeakButton(id: 'job-${job['id']}', text: '${params['text'] ?? job['prompt']}');
    }
    if (bytes == null) return const SizedBox(height: 120, child: Center(child: CircularProgressIndicator()));
    final share = IconButton(
      icon: const Icon(Icons.share_outlined),
      tooltip: context.t('share'),
      onPressed: () => SharePlus.instance.share(ShareParams(files: [
        XFile.fromData(bytes!, mimeType: mime, name: '${job['id']}.${mime.split('/').last}'),
      ])),
    );
    if (mime.startsWith('image/')) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (warning != null) Padding(padding: const EdgeInsets.only(bottom: 6), child: Text('$warning', style: Theme.of(context).textTheme.bodySmall)),
        GestureDetector(
          onTap: () => showDialog(
            context: context,
            builder: (_) => Dialog.fullscreen(
              child: Stack(children: [
                InteractiveViewer(maxScale: 6, child: Center(child: Image.memory(bytes!))),
                Positioned(top: 8, right: 8, child: IconButton.filledTonal(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context))),
              ]),
            ),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Image.memory(bytes!, width: 320, cacheWidth: 640, fit: BoxFit.cover),
          ),
        ),
        share,
      ]);
    }
    if (mime.startsWith('audio/')) {
      return Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton.filledTonal(
          icon: Icon(playing ? Icons.pause : Icons.play_arrow),
          onPressed: () async {
            if (playing) {
              await player.pause();
            } else {
              await player.play(BytesSource(bytes!, mimeType: mime));
              player.onPlayerComplete.first.then((_) => mounted ? setState(() => playing = false) : null);
            }
            setState(() => playing = !playing);
          },
        ),
        share,
      ]);
    }
    if (mime == 'text/plain') return SelectableText(utf8.decode(bytes!));
    return share;
  }
}
