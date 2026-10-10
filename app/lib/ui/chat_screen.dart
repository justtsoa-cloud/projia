// Écran principal : conversation + champ de saisie. Rien d'autre par défaut.

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:share_plus/share_plus.dart';

import '../core/backend.dart';
import '../core/chat_controller.dart';
import '../core/updater.dart';
import 'update_sheet.dart';
import '../main.dart';
import 'message_view.dart';
import 'model_picker.dart';
import 'search_dialog.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final input = TextEditingController();
  final scroll = ScrollController();
  final focus = FocusNode();
  final List<String> attachments = [];
  String? forcedCategory;
  final recorder = AudioRecorder();
  bool recording = false;
  // Suivi automatique du bas : désactivé dès que l'utilisateur remonte le fil.
  bool stickToBottom = true;

  @override
  void dispose() {
    input.dispose();
    scroll.dispose();
    focus.dispose();
    recorder.dispose();
    super.dispose();
  }

  void update(VoidCallback fn) => setState(fn);

  void _send(ChatController chat) {
    final text = input.text.trim();
    if (text.isEmpty && attachments.isEmpty) return;
    stickToBottom = true;
    chat.send(text, images: List.of(attachments), category: forcedCategory);
    input.clear();
    setState(() {
      attachments.clear();
      forcedCategory = null;
    });
  }

  Future<void> _pickFile() async {
    final res = await FilePicker.pickFiles(type: FileType.image);
    if (res.isEmpty) return;
    final f = res.first;
    final bytes = await f.xFile.readAsBytes();
    final ext = (f.extension ?? 'png').replaceFirst('.', '').toLowerCase();
    setState(() => attachments.add(ChatController.dataUrl(bytes, 'image/${ext == 'jpg' ? 'jpeg' : ext}')));
  }

  /// Dictée : enregistrement local puis transcription (même bascule que le texte).
  Future<void> _toggleMic(Backend backend) async {
    final locale = AppScope.of(context).prefs.locale;
    if (recording) {
      final path = await recorder.stop();
      setState(() => recording = false);
      if (path == null) return;
      final req = http.MultipartRequest('POST', backend.uri('/v1/audio/transcriptions'))
        ..headers.addAll(backend.headers)
        ..fields['model'] = 'auto'
        ..fields['language'] = locale
        ..files.add(await http.MultipartFile.fromPath('file', path));
      final resp = await http.Response.fromStream(await req.send());
      if (!mounted) return;
      if (resp.statusCode == 200) {
        final text = RegExp(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"').firstMatch(resp.body)?.group(1) ?? '';
        input.text = '${input.text} ${text.replaceAll(r'\n', '\n')}'.trim();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.t('error_generic'))));
      }
      return;
    }
    if (!await recorder.hasPermission()) return;
    final dir = await getTemporaryDirectory();
    await recorder.start(const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
        path: '${dir.path}/dictee.wav');
    setState(() => recording = true);
  }

  Future<void> _editMessage(ChatController chat, ChatMessage m) async {
    final ctrl = TextEditingController(text: m.text);
    final text = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(context.t('edit')),
        content: TextField(controller: ctrl, autofocus: true, minLines: 1, maxLines: 8),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(context, ctrl.text), child: Text(context.t('send'))),
        ],
      ),
    );
    if (text != null) chat.editAndResend(m, text);
  }

  Future<void> _export(ChatController chat) async {
    final b = AppScope.of(context).backend;
    final r = await http.get(b.uri('/tontolo/conversations/${chat.conversationId}/export'), headers: b.headers);
    if (r.statusCode != 200) return;
    await SharePlus.instance.share(ShareParams(files: [
      XFile.fromData(r.bodyBytes, mimeType: 'text/markdown', name: 'tontolo-conversation.md'),
    ]));
  }

  Future<void> _pin(ChatController chat) async {
    await AppScope.of(context).backend.sendJson('PUT', '/tontolo/conversations/${chat.conversationId}/pin', {'pinned': true});
  }

  /// Suivi du bas : jamais pendant que le doigt est posé ou que le fil défile (inertie
  /// comprise) ; il ne reprend que si l'utilisateur s'arrête en bas.
  bool _touching = false;

  void _scrollToEnd({bool force = false}) {
    if (!force && (!stickToBottom || _touching)) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!scroll.hasClients) return;
      // Revérifié ici : l'état a pu changer (doigt posé, remontée) depuis la programmation.
      if (!force && (!stickToBottom || _touching || scroll.position.isScrollingNotifier.value)) return;
      // jumpTo : pas d'animation concurrente avec le doigt de l'utilisateur.
      scroll.jumpTo(scroll.position.maxScrollExtent);
    });
  }

  void _updateStick() {
    if (!scroll.hasClients) return;
    final nearBottom = scroll.position.maxScrollExtent - scroll.position.pixels < 80;
    if (nearBottom != stickToBottom) {
      stickToBottom = nearBottom; // immédiat, avant tout saut déjà programmé
      if (mounted) setState(() {});
    }
  }

  bool _onScroll(ScrollNotification n) {
    if (n is ScrollEndNotification) {
      if (!_touching) _updateStick();
    }
    return false;
  }

  Future<void> _showWhy(ChatMessage m) async {
    final r = m.reason;
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(context.t('why'), style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          Text(m.modelName ?? m.model ?? ''),
          if (r != null) ...[
            const SizedBox(height: 8),
            Text('Catégorie : ${r['category']}'),
            Text('${context.t('quality')} : ${r['quality']} · ${context.t('speed')} : ${r['speed']} · '
                '${context.t('reliability')} : ${r['reliability']}'),
            Text('Score : ${r['score']}${r['free'] == true ? ' · gratuit' : ''}'
                '${r['preferred'] == true ? ' · modèle préféré' : ''}'
                '${r['provisional'] == true ? ' · score provisoire' : ''}'),
          ],
          const SizedBox(height: 12),
          Text('Classements : Artificial Analysis, LMArena (CC BY 4.0).', style: Theme.of(context).textTheme.bodySmall),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final chat = scope.chat;
    final backend = scope.backend;
    return ListenableBuilder(
      listenable: Listenable.merge([chat, backend, scope.updater]),
      builder: (context, _) {
        _scrollToEnd();
        return Scaffold(
          appBar: AppBar(
            title: Text(context.t('app')),
            actions: [
              IconButton(icon: const Icon(Icons.search), tooltip: context.t('search'), onPressed: () => showSearchDialog(context)),
              IconButton(icon: const Icon(Icons.edit_square), tooltip: context.t('new_chat'), onPressed: chat.newChat),
              if (chat.conversationId != null)
                PopupMenuButton<String>(
                  onSelected: (v) => v == 'export' ? _export(chat) : _pin(chat),
                  itemBuilder: (context) => [
                    PopupMenuItem(value: 'pin', child: ListTile(leading: const Icon(Icons.push_pin_outlined), title: Text(context.t('pin')))),
                    PopupMenuItem(value: 'export', child: ListTile(leading: const Icon(Icons.ios_share), title: Text(context.t('export')))),
                  ],
                ),
            ],
          ),
          drawer: const HistoryDrawer(),
          body: SafeArea(
            child: Column(children: [
              _UpdateBanner(),
              if (backend.state == BackendState.starting) const LinearProgressIndicator(minHeight: 2),
              if (backend.state == BackendState.failed)
                MaterialBanner(
                  content: Text('${context.t('error_generic')} ${backend.error ?? ''}'),
                  actions: [TextButton(onPressed: backend.start, child: Text(context.t('retry')))],
                ),
              Expanded(
                child: chat.messages.isEmpty
                    ? _EmptyState(onPick: (s) {
                        input.text = s;
                        _send(chat);
                      })
                    : Listener(
                        onPointerDown: (_) => _touching = true,
                        onPointerUp: (_) {
                          _touching = false;
                          _updateStick(); // position finale du geste ; l'inertie met à jour en fin de défilement
                        },
                        onPointerCancel: (_) => _touching = false,
                        child: NotificationListener<ScrollNotification>(
                        onNotification: _onScroll,
                        child: ListView.builder(
                        controller: scroll,
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        itemCount: chat.messages.length,
                        itemBuilder: (context, i) {
                          final m = chat.messages[i];
                          if (m.role == 'notice') return _Notice(m.text, onRetry: chat.retry);
                          final isLast = i == chat.messages.length - 1;
                          return MessageView(
                            message: m,
                            onWhy: () => _showWhy(m),
                            onRegenerate: isLast && m.role == 'assistant' && chat.canRegenerate ? chat.regenerate : null,
                            onEdit: m.role == 'user' && m.seq != null && !chat.busy ? () => _editMessage(chat, m) : null,
                          );
                        },
                      ))),
              ),
              if (!stickToBottom && chat.messages.isNotEmpty)
                Align(
                  alignment: Alignment.centerRight,
                  child: Padding(
                    padding: const EdgeInsets.only(right: 12, bottom: 4),
                    child: FloatingActionButton.small(
                      heroTag: 'toBottom',
                      tooltip: context.t('to_bottom'),
                      onPressed: () {
                        setState(() => stickToBottom = true);
                        _scrollToEnd(force: true);
                      },
                      child: const Icon(Icons.arrow_downward),
                    ),
                  ),
                ),
              if (chat.status != null) _StatusLine(chat.status!),
              if (chat.pending != null) _PendingBar(chat),
              _InputBar(this, chat, backend),
            ]),
          ),
        );
      },
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar(this.state, this.chat, this.backend);
  final _ChatScreenState state;
  final ChatController chat;
  final Backend backend;

  @override
  Widget build(BuildContext context) {
    final ready = backend.state == BackendState.ready;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          ModelChip(chat: chat),
          if (state.forcedCategory != null)
            Padding(
              padding: const EdgeInsets.only(left: 6),
              child: InputChip(
                label: Text(state.forcedCategory == 'image_gen' ? context.t('force_image') : context.t('force_voice')),
                onDeleted: () => state.update(() => state.forcedCategory = null),
              ),
            ),
        ]),
        _SlashTemplates(state.input),
        if (state.attachments.isNotEmpty)
          SizedBox(
            height: 64,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final (i, _) in state.attachments.indexed)
                Padding(
                  padding: const EdgeInsets.all(4),
                  child: InputChip(
                    avatar: const Icon(Icons.image_outlined),
                    label: Text('${i + 1}'),
                    onDeleted: () => state.update(() => state.attachments.removeAt(i)),
                  ),
                ),
            ]),
          ),
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          PopupMenuButton<String>(
            icon: const Icon(Icons.add_circle_outline),
            tooltip: context.t('attach'),
            onSelected: (v) {
              switch (v) {
                case 'file':
                  state._pickFile();
                case 'mic':
                  state._toggleMic(backend);
                default:
                  state.update(() => state.forcedCategory = v);
              }
            },
            itemBuilder: (context) => [
              PopupMenuItem(value: 'file', child: ListTile(leading: const Icon(Icons.image_outlined), title: Text(context.t('photo')))),
              PopupMenuItem(value: 'mic', child: ListTile(leading: const Icon(Icons.mic_none), title: Text(context.t('mic')))),
              PopupMenuItem(value: 'image_gen', child: ListTile(leading: const Icon(Icons.brush_outlined), title: Text(context.t('force_image')))),
              PopupMenuItem(value: 'tts', child: ListTile(leading: const Icon(Icons.record_voice_over_outlined), title: Text(context.t('force_voice')))),
            ],
          ),
          if (state.recording)
            IconButton.filled(icon: const Icon(Icons.stop), onPressed: () => state._toggleMic(backend)),
          Expanded(
            child: CallbackShortcuts(
              bindings: {
                const SingleActivator(LogicalKeyboardKey.enter, control: true): () => state._send(chat),
              },
              child: TextField(
                controller: state.input,
                focusNode: state.focus,
                minLines: 1,
                maxLines: 6,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(hintText: context.t('write')),
              ),
            ),
          ),
          const SizedBox(width: 4),
          chat.busy
              ? IconButton.filledTonal(icon: const Icon(Icons.stop_circle_outlined), tooltip: context.t('stop'), onPressed: chat.stop)
              : IconButton.filled(
                  icon: const Icon(Icons.arrow_upward),
                  tooltip: '${context.t('send')} (Ctrl+Entrée)',
                  onPressed: ready ? () => state._send(chat) : null,
                ),
        ]),
      ]),
    );
  }
}

/// Raccourcis « / » : modèles de demandes prêts à compléter (comme les « prompts » enregistrés).
class _SlashTemplates extends StatelessWidget {
  const _SlashTemplates(this.input);
  final TextEditingController input;

  static const keys = ['tpl_resume', 'tpl_explain', 'tpl_translate', 'tpl_fix', 'tpl_code', 'tpl_quiz', 'tpl_email'];

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<TextEditingValue>(
        valueListenable: input,
        builder: (context, value, _) {
          if (!value.text.startsWith('/')) return const SizedBox.shrink();
          final q = value.text.substring(1).toLowerCase();
          final matches = keys.where((k) => context.t(k).toLowerCase().contains(q) || k.contains(q)).toList();
          return SizedBox(
            height: 44,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final k in matches)
                Padding(
                  padding: const EdgeInsets.only(right: 6, top: 4),
                  child: ActionChip(
                    label: Text(context.t(k).split(RegExp(r'[:\n]')).first),
                    onPressed: () {
                      final t = context.t(k);
                      input.value = TextEditingValue(text: t, selection: TextSelection.collapsed(offset: t.length));
                    },
                  ),
                ),
            ]),
          );
        },
      );
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onPick});
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Image.asset('assets/icon.png', width: 72, height: 72),
            const SizedBox(height: 16),
            Text(context.t('hello'), style: Theme.of(context).textTheme.titleLarge, textAlign: TextAlign.center),
            const SizedBox(height: 20),
            for (final k in ['sugg1', 'sugg2', 'sugg3'])
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: ActionChip(label: Text(context.t(k)), onPressed: () => onPick(context.t(k))),
              ),
          ]),
        ),
      );
}

/// Bandeau discret non bloquant : bascule, retour, erreur (phrase humaine + une action).
class _Notice extends StatelessWidget {
  const _Notice(this.raw, {required this.onRetry});
  final String raw;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final parts = raw.split('|');
    final scheme = Theme.of(context).colorScheme;
    final (icon, text, color, action) = switch (parts.first) {
      'switched' => (Icons.swap_horiz, context.t('switched', {'to': parts[1], 'reason': parts.length > 2 ? parts[2] : ''}), scheme.tertiary, false),
      'returned' => (Icons.undo, context.t('returned', {'model': parts[1]}), scheme.secondary, false),
      'stream_reset' => (Icons.refresh, context.t('stream_interrupted'), scheme.tertiary, false),
      'memory' => (Icons.bookmark_added_outlined, context.t('memory_saved', {'text': parts.skip(1).join('|')}), scheme.secondary, false),
      _ => (Icons.error_outline, parts.skip(1).join('|'), scheme.error, true),
    };
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
      child: Row(children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: color))),
        if (action) TextButton(onPressed: onRetry, child: Text(context.t('retry'))),
      ]),
    );
  }
}

class _StatusLine extends StatelessWidget {
  const _StatusLine(this.status);
  final String status;

  @override
  Widget build(BuildContext context) {
    final text = status == 'thinking'
        ? context.t('thinking')
        : status.startsWith('tool|')
        ? '⚙ ${status.substring(5)}'
        : status.startsWith('waiting|')
            ? context.t('waiting', {'s': status.substring(8)})
            : context.t(status);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 2),
      child: Row(children: [
        const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
        const SizedBox(width: 8),
        Text(text, style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}

class _PendingBar extends StatelessWidget {
  const _PendingBar(this.chat);
  final ChatController chat;

  @override
  Widget build(BuildContext context) {
    final p = chat.pending!;
    final text = p.kind == 'paid'
        ? context.t('paid_confirm', {'model': p.model ?? '', 'cost': (p.cost ?? 0).toStringAsFixed(4)})
        : context.t('tool_confirm', {'name': p.tools.map((t) => t['name']).join(', ')});
    return MaterialBanner(
      content: Text(text),
      actions: [
        TextButton(onPressed: () => p.kind == 'paid' ? chat.resolvePaid(false) : chat.resolveTools(false), child: Text(context.t('decline'))),
        FilledButton(onPressed: () => p.kind == 'paid' ? chat.resolvePaid(true) : chat.resolveTools(true), child: Text(context.t('accept'))),
      ],
    );
  }
}

class _UpdateBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final up = AppScope.of(context).updater;
    if (up.latest == null || (up.status != UpdateStatus.ready && up.status != UpdateStatus.downloading)) {
      return const SizedBox.shrink();
    }
    final downloading = up.status == UpdateStatus.downloading;
    return MaterialBanner(
      leading: const Icon(Icons.system_update),
      content: Text(downloading
          ? '${context.t('update_downloading')} ${(up.progress * 100).round()} %'
          : context.t('update_ready', {'v': up.latest!})),
      actions: [
        TextButton(onPressed: () => showUpdateSheet(context), child: Text(context.t('see_changes'))),
      ],
    );
  }
}

/// Tiroir d'historique : conversations récentes, renommer, supprimer.
class HistoryDrawer extends StatefulWidget {
  const HistoryDrawer({super.key});

  @override
  State<HistoryDrawer> createState() => _HistoryDrawerState();
}

class _HistoryDrawerState extends State<HistoryDrawer> {
  List<Map<String, dynamic>> items = [];

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final data = await b.getJson('/tontolo/conversations', {'limit': 100}) as List;
    if (mounted) setState(() => items = data.cast<Map<String, dynamic>>());
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    return NavigationDrawer(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 16, 16, 10),
          child: Text(context.t('history'), style: Theme.of(context).textTheme.titleSmall),
        ),
        ListTile(
          leading: const Icon(Icons.add),
          title: Text(context.t('new_chat')),
          onTap: () {
            scope.chat.newChat();
            Navigator.pop(context);
          },
        ),
        const Divider(),
        for (final c in items)
          ListTile(
            leading: c['pinned'] == 1 ? const Icon(Icons.push_pin, size: 18) : null,
            title: Text('${c['title']}'.isEmpty ? '…' : '${c['title']}', maxLines: 1, overflow: TextOverflow.ellipsis),
            selected: c['id'] == scope.chat.conversationId,
            onTap: () {
              scope.chat.open('${c['id']}');
              Navigator.pop(context);
            },
            trailing: PopupMenuButton<String>(
              onSelected: (v) async {
                if (v == 'pin') {
                  await scope.backend.sendJson('PUT', '/tontolo/conversations/${c['id']}/pin', {'pinned': c['pinned'] != 1});
                } else if (v == 'delete') {
                  await scope.backend.sendJson('DELETE', '/tontolo/conversations/${c['id']}');
                  if (scope.chat.conversationId == c['id']) scope.chat.newChat();
                } else {
                  final ctrl = TextEditingController(text: '${c['title']}');
                  final title = await showDialog<String>(
                    context: context,
                    builder: (context) => AlertDialog(
                      title: Text(context.t('rename')),
                      content: TextField(controller: ctrl, autofocus: true),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
                        FilledButton(onPressed: () => Navigator.pop(context, ctrl.text), child: Text(context.t('save'))),
                      ],
                    ),
                  );
                  if (title != null) {
                    await scope.backend.sendJson('PATCH', '/tontolo/conversations/${c['id']}', {'title': title});
                  }
                }
                _load();
              },
              itemBuilder: (context) => [
                PopupMenuItem(value: 'pin', child: Text(c['pinned'] == 1 ? context.t('unpin') : context.t('pin'))),
                PopupMenuItem(value: 'rename', child: Text(context.t('rename'))),
                PopupMenuItem(value: 'delete', child: Text(context.t('delete'))),
              ],
            ),
          ),
      ],
    );
  }
}
