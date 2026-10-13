import 'dart:convert';
// Écran principal : conversation + champ de saisie. Rien d'autre par défaut.


import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:record/record.dart';
import 'package:share_plus/share_plus.dart';

import '../core/backend.dart';
import '../core/chat_controller.dart';
import '../core/cloud_sync.dart' show RemoteTask;
import '../core/export_html.dart';
import '../core/image_prep.dart';
import '../core/retouch.dart';
import '../core/updater.dart';
import 'update_sheet.dart';
import '../core/storage_dirs.dart';
import '../main.dart';
import 'message_view.dart';
import 'model_picker.dart';
import 'import_flow.dart';
import 'home_view.dart';
import 'learn.dart';
import 'question_card.dart';
import 'search_dialog.dart';
import 'activity_dot.dart';
import 'task_results.dart';
import 'workbench.dart';

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
  // Plan de travail (terminal du bureau, navigateur de la tablette) à côté de la discussion.
  bool bench = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final scope = AppScope.of(context);
      if (browserPanelSupported(context)) {
        BrowserBridge.instance
          ..start(scope.backend)
          ..addListener(_onBridge);
      }
    });
  }

  /// Une commande de l'agent arrive pour le navigateur : le panneau s'affiche.
  void _onBridge() {
    final bridge = BrowserBridge.instance;
    if (!bridge.wantsPanel || !mounted) return;
    bridge.wantsPanel = false;
    if (!bench) setState(() => bench = true);
  }

  void _toggleBench(bool wide) {
    if (wide) {
      setState(() => bench = !bench);
      return;
    }
    final chat = AppScope.of(context).chat;
    Navigator.push(context, MaterialPageRoute<void>(
      builder: (context) => Scaffold(body: SafeArea(child: Workbench(chat: chat, onClose: () => Navigator.pop(context)))),
    ));
  }

  @override
  void dispose() {
    BrowserBridge.instance.removeListener(_onBridge);
    input.dispose();
    scroll.dispose();
    focus.dispose();
    recorder.dispose();
    super.dispose();
  }

  void update(VoidCallback fn) => setState(fn);

  // Photos d'origine (pleine résolution) pour la retouche locale, parallèles à `attachments`.
  final List<Uint8List> originals = [];

  /// Demande d'édition d'une photo jointe : verbes de retouche, filtres, transformations.
  static final _editRequest = RegExp(
      r'edit|retouch|modifi|chang|remplac|transform|ajout|supprim|enlev|efface|retir|amelior|'
      r'corrig|filtre|optimis|embell|eclairc|assombri|contraste|recadr|noir et blanc|sepia|'
      r'vintage|professionnel|\bstyle\b|rends|\bmets\b|'
      r'hatsarao|amboary|ahitsio|ovay|mainty sy fotsy|matihanina|mazava kokoa',
      caseSensitive: false);

  /// Tâche sur le contenu de la photo (exercice à résoudre, texte à lire…) : jamais une retouche,
  /// même si la phrase contient « rends », « corrige » ou « clair ».
  static final _contentTask = RegExp(
      r'exercice|exercise|probl[eè]me|problem|question|r[ée]sou|solve|calcul|d[ée]montr|explique|'
      r'explain|traite|r[ée]pond|answer|devoir|homework|[ée]quation|int[ée]grale|\bpdf\b|\bword\b|'
      r'docx|fanazaran|vahao|hazavao',
      caseSensitive: false);

  void _send(ChatController chat) {
    final text = input.text.trim();
    if (text.isEmpty && attachments.isEmpty) return;
    stickToBottom = true;
    // Lien d'une discussion Claude / ChatGPT / Gemini : on l'importe pour la continuer ici.
    final link = attachments.isEmpty ? shareLink.firstMatch(text) : null;
    if (link != null) {
      input.clear();
      importConversation(context, url: link.group(0), followUp: text.replaceFirst(link.group(0)!, '').trim().length > 25
          ? text.replaceFirst(link.group(0)!, '').trim()
          : '');
      return;
    }
    // Photo jointe + consigne de retouche fidèle → traitée sur l'appareil, sans envoi à une IA.
    if (attachments.length == 1 && originals.length == 1 && forcedCategory == null &&
        _editRequest.hasMatch(text.toLowerCase()) && !_contentTask.hasMatch(text.toLowerCase())) {
      final intent = analyzeEdit(text);
      if (intent.mode == EditMode.local) {
        chat.sendLocalRetouch(text, originals.first, attachments.first, intent);
        input.clear();
        setState(() {
          attachments.clear();
          originals.clear();
        });
        return;
      }
    }
    originals.clear();
    chat.send(text, images: List.of(attachments), category: forcedCategory);
    input.clear();
    setState(() {
      attachments.clear();
      forcedCategory = null;
    });
  }

  /// Raccourci : prépare la demande sans l'envoyer (l'utilisateur la complète).
  Future<void> _prefill(String text, {bool photo = false}) async {
    if (photo && attachments.isEmpty) {
      await _pickFile();
      if (attachments.isEmpty) return; // sélection annulée
    }
    if (!mounted) return;
    setState(() {
      input.text = text;
      input.selection = TextSelection.collapsed(offset: text.length);
    });
    focus.requestFocus();
  }

  static const _imageExt = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'heic', 'heif', 'bmp'];
  static const _mediaExt = ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'oga', 'opus', 'flac', 'amr', 'weba',
      'mp4', 'mov', 'mkv', 'webm', 'avi', '3gp', 'm4v'];
  static const _maxBytes = 100 * 1024 * 1024; // le cœur borne ensuite selon le type

  Future<void> _pickFile() async {
    // Tout type de fichier : images (vision), et le reste (PDF, bureautique, texte, code,
    // archives, son, vidéo…) lu ou transcrit par le cœur, qui refuse ce qu'il ne sait pas lire.
    final res = await FilePicker.pickFiles(type: FileType.any);
    if (res.isEmpty) return;
    final f = res.first;
    final ext = f.name.split('.').last.toLowerCase();
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    final tooBig = context.t('file_too_big');
    if (await f.xFile.length() > _maxBytes) {
      messenger.showSnackBar(SnackBar(content: Text(tooBig)));
      return;
    }
    final raw = await f.xFile.readAsBytes();
    if (!_imageExt.contains(ext)) {
      // Document : texte extrait (ou transcrit) par le cœur, utilisé pour répondre en citant.
      if (!mounted) return;
      final chat = AppScope.of(context).chat;
      final reading = context.t(_mediaExt.contains(ext) ? 'media_transcribing' : 'doc_reading');
      messenger.showSnackBar(SnackBar(content: Text(reading), duration: const Duration(minutes: 10)));
      final err = await chat.attachDocument(f.name, raw);
      if (!mounted) return;
      messenger.hideCurrentSnackBar();
      if (err != null) {
        messenger.showSnackBar(SnackBar(content: Text(err)));
      } else if (input.text.trim().isEmpty) {
        setState(() => input.text = context.t('doc_prefill'));
        focus.requestFocus();
      }
      return;
    }
    final (bytes, mime) = await prepareImage(raw); // photo réduite : envoi et stockage plus légers
    if (!mounted) return;
    setState(() {
      attachments.add(ChatController.dataUrl(bytes, mime));
      originals.add(raw); // pleine résolution, pour la retouche locale
    });
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
    final dir = await tmpDir();
    await recorder.start(const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
        path: '${dir.path}/dictee.wav');
    setState(() => recording = true);
  }

  /// 👍 / 👎 ; après un 👎, raisons rapides et « Réessayer avec un autre modèle ».
  Future<void> _rate(ChatController chat, ChatMessage m, int rating, bool canRetry) async {
    final ok = await chat.rate(m, rating);
    if (!ok || rating != -1 || !mounted) return;
    const reasons = ['inexact', 'off_topic', 'too_long', 'too_short', 'language', 'other'];
    final retry = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(context.t('rate_why'), style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(context.t('rate_private'), style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 10),
            Wrap(spacing: 8, runSpacing: 6, children: [
              for (final r in reasons)
                ActionChip(
                  label: Text(context.t('rate_$r')),
                  onPressed: () {
                    chat.rate(m, -1, reason: r);
                    Navigator.pop(context, false);
                  },
                ),
            ]),
            if (canRetry) ...[
              const SizedBox(height: 12),
              FilledButton.tonalIcon(
                icon: const Icon(Icons.swap_horiz),
                label: Text(context.t('rate_retry')),
                onPressed: () => Navigator.pop(context, true),
              ),
            ],
          ]),
        ),
      ),
    );
    if (retry == true && mounted) {
      stickToBottom = true;
      chat.regenerate(avoidModel: m.model);
    }
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

  /// PDF produit par le cœur, sur l'appareil (aucun service en ligne).
  Future<void> _exportPdf(ChatController chat) async {
    final b = AppScope.of(context).backend;
    final lang = AppScope.of(context).prefs.locale;
    final r = await http.get(b.uri('/tontolo/conversations/${chat.conversationId}/export', {'format': 'pdf', 'lang': lang}), headers: b.headers);
    if (r.statusCode != 200) return;
    await SharePlus.instance.share(ShareParams(files: [
      XFile.fromData(r.bodyBytes, mimeType: 'application/pdf', name: 'tontolo-discussion.pdf'),
    ]));
  }

  /// Page web autonome et sûre (sans script) de toute la discussion, à partager.
  Future<void> _exportHtml(ChatController chat) async {
    final prefs = AppScope.of(context).prefs;
    final first = chat.messages.firstWhere((m) => m.role == 'user', orElse: () => ChatMessage(role: 'user', text: 'Tontolo'));
    final title = first.text.length > 60 ? '${first.text.substring(0, 60)}…' : first.text;
    final html = conversationHtml(chat.messages, title: title, locale: prefs.locale);
    await SharePlus.instance.share(ShareParams(files: [
      XFile.fromData(utf8.encode(html), mimeType: 'text/html', name: 'tontolo-discussion.html'),
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

  /// Discussion seule, ou discussion + plan de travail côte à côte (écran large).
  Widget _withBench(BuildContext context, Widget chatColumn) {
    final width = MediaQuery.sizeOf(context).width;
    if (!bench || width < 840) return chatColumn;
    return Row(children: [
      Expanded(child: chatColumn),
      const VerticalDivider(width: 1),
      SizedBox(
        width: (width * 0.45).clamp(360.0, 900.0),
        child: Workbench(chat: AppScope.of(context).chat, onClose: () => setState(() => bench = false)),
      ),
    ]);
  }

  /// Compactage manuel : fiche structurée du début du fil (les messages restent intacts).
  Future<void> _compact(ChatController chat) async {
    final messenger = ScaffoldMessenger.of(context);
    final notFound = context.t('compact_nothing');
    messenger.showSnackBar(SnackBar(content: Text(context.t('compacting'))));
    String? summary;
    try {
      summary = await chat.compact() ?? chat.summary;
    } catch (_) {
      summary = null;
    }
    messenger.hideCurrentSnackBar();
    if (!mounted) return;
    if (summary == null || summary.isEmpty) {
      messenger.showSnackBar(SnackBar(content: Text(notFound)));
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
          children: [
            Text(context.t('compact_title'), style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(context.t('compact_help'), style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            RichMarkdown(summary!),
          ],
        ),
      ),
    );
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
            Text('${context.t('why_category')} : ${context.t('cat_${r['category']}')}'),
            Text('${context.t('quality')} : ${r['quality']} · ${context.t('speed')} : ${r['speed']} · '
                '${context.t('reliability')} : ${r['reliability']}'),
            Text('${context.t('why_score')} : ${r['score']}${r['free'] == true ? ' · ${context.t('tag_free')}' : ''}'
                '${r['preferred'] == true ? ' · ${context.t('why_preferred')}' : ''}'
                '${r['provisional'] == true ? ' · ${context.t('why_provisional')}' : ''}'),
          ],
          const SizedBox(height: 12),
          Text(context.t('why_rankings'), style: Theme.of(context).textTheme.bodySmall),
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
      listenable: Listenable.merge([chat, backend, scope.updater, scope.cloud, scope.activity]),
      builder: (context, _) {
        _scrollToEnd();
        return Scaffold(
          appBar: AppBar(
            titleSpacing: 8,
            leading: Builder(
              builder: (context) {
                final dot = scope.activity.elsewhere;
                return IconButton(
                  icon: Badge(
                    isLabelVisible: dot != null,
                    smallSize: 11,
                    backgroundColor: dotColor(context, dot),
                    child: const Icon(Icons.menu),
                  ),
                  tooltip: dot == null ? MaterialLocalizations.of(context).openAppDrawerTooltip : context.t('dot_${dot.name}'),
                  onPressed: () => Scaffold.of(context).openDrawer(),
                );
              },
            ),
            title: ModeToggle(chat: chat),
            actions: [
              if (terminalSupported || browserPanelSupported(context))
                IconButton(
                  icon: Icon(bench ? Icons.view_sidebar : Icons.view_sidebar_outlined),
                  tooltip: context.t('workbench'),
                  onPressed: () => _toggleBench(MediaQuery.sizeOf(context).width >= 840),
                ),
              IconButton(icon: const Icon(Icons.search), tooltip: context.t('search'), onPressed: () => showSearchDialog(context)),
              IconButton(icon: const Icon(Icons.edit_square), tooltip: context.t('new_chat'), onPressed: chat.newChat),
              if (chat.conversationId != null)
                PopupMenuButton<String>(
                  onSelected: (v) => switch (v) {
                    'export' => _export(chat),
                    'export_html' => _exportHtml(chat),
                    'export_pdf' => _exportPdf(chat),
                    'compact' => _compact(chat),
                    'tasks' => showTaskResults(context, chat.conversationId!),
                    _ => _pin(chat),
                  },
                  itemBuilder: (context) => [
                    PopupMenuItem(value: 'pin', child: ListTile(leading: const Icon(Icons.push_pin_outlined), title: Text(context.t('pin')))),
                    PopupMenuItem(value: 'export_html', child: ListTile(leading: const Icon(Icons.web_outlined), title: Text(context.t('export_html')))),
                    PopupMenuItem(value: 'export_pdf', child: ListTile(leading: const Icon(Icons.picture_as_pdf_outlined), title: Text(context.t('export_pdf')))),
                    PopupMenuItem(value: 'export', child: ListTile(leading: const Icon(Icons.ios_share), title: Text(context.t('export')))),
                    PopupMenuItem(value: 'compact', child: ListTile(leading: const Icon(Icons.compress), title: Text(context.t('compact')))),
                    PopupMenuItem(value: 'tasks', child: ListTile(leading: const Icon(Icons.inventory_2_outlined), title: Text(context.t('task_results')))),
                  ],
                ),
            ],
          ),
          drawer: const HistoryDrawer(),
          body: SafeArea(
            child: _withBench(context, Column(children: [
              _UpdateBanner(),
              for (final t in scope.cloud.liveTasks) _RemoteTaskBar(t, current: t.conversationId == chat.conversationId),
              if (backend.state == BackendState.starting) const LinearProgressIndicator(minHeight: 2),
              if (backend.state == BackendState.failed)
                MaterialBanner(
                  content: Text('${context.t('error_generic')} ${backend.error ?? ''}'),
                  actions: [TextButton(onPressed: backend.start, child: Text(context.t('retry')))],
                ),
              Expanded(
                child: chat.messages.isEmpty && chat.learn
                    ? LearnEmptyState(onPrefill: (text, {photo = false}) => _prefill(text, photo: photo))
                    : chat.messages.isEmpty
                    ? HomeView(
                        key: ValueKey('home-${chat.agent}'),
                        chat: chat,
                        onSend: (s) {
                          input.text = s;
                          _send(chat);
                        },
                        onPrefill: (text, {photo = false}) => _prefill(text, photo: photo),
                      )
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
                        itemCount: chat.messages.length + (chat.earlierLeft > 0 ? 1 : 0) +
                            (chat.asked.isNotEmpty && !chat.busy ? 1 : 0),
                        itemBuilder: (context, i) {
                          if (chat.earlierLeft > 0) {
                            if (i == 0) {
                              return Center(
                                child: TextButton(
                                  onPressed: chat.loadingEarlier ? null : chat.loadEarlier,
                                  child: chat.loadingEarlier
                                      ? const SizedBox(
                                          width: 18, height: 18,
                                          child: CircularProgressIndicator(strokeWidth: 2))
                                      : Text(context.t('earlier', {'n': '${chat.earlierLeft}'})),
                                ),
                              );
                            }
                            i -= 1;
                          }
                          if (i == chat.messages.length) {
                            return QuestionCard(
                              questions: chat.asked,
                              onSend: (t) {
                                stickToBottom = true;
                                chat.send(t);
                              },
                            );
                          }
                          final m = chat.messages[i];
                          if (m.role == 'notice') return _Notice(m.text, onRetry: chat.retry);
                          final isLast = i == chat.messages.length - 1;
                          final view = MessageView(
                            message: m,
                            onWhy: () => _showWhy(m),
                            onRegenerate: isLast && m.role == 'assistant' && chat.canRegenerate ? chat.regenerate : null,
                            onEdit: m.role == 'user' && m.seq != null && !chat.busy ? () => _editMessage(chat, m) : null,
                            onRate: m.role == 'assistant' && m.uid != null && !m.streaming
                                ? (r) => _rate(chat, m, r, isLast && chat.canRegenerate)
                                : null,
                          );
                          if (!(isLast && chat.learn && m.role == 'assistant' && !chat.busy && m.text.isNotEmpty)) return view;
                          return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            view,
                            LearnActions(
                              onSend: (t) {
                                stickToBottom = true;
                                chat.send(t);
                              },
                              onPrefill: (t) => _prefill(t),
                            ),
                          ]);
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
              if (chat.plan != null && (chat.planActive || chat.busy)) _PlanBar(chat),
              if (chat.status != null) _StatusLine(chat.status!),
              if (chat.pending != null) _PendingBar(chat),
              _InputBar(this, chat, backend),
            ])),
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
        if (AppScope.of(context).chat.documents.isNotEmpty)
          SizedBox(
            height: 48,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final d in AppScope.of(context).chat.documents)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: InputChip(
                    avatar: const Icon(Icons.description_outlined, size: 18),
                    label: Text('${d['name']}', overflow: TextOverflow.ellipsis),
                    tooltip: context.t('doc_remove'),
                    onDeleted: () => AppScope.of(context).chat.removeDocument(d),
                  ),
                ),
            ]),
          ),
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
                    onDeleted: () => state.update(() {
                      state.attachments.removeAt(i);
                      if (i < state.originals.length) state.originals.removeAt(i);
                    }),
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
                  tooltip: '${context.t('send')} (Ctrl+Enter)',
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

/// Raccourci de l'écran d'accueil : pré-remplit la demande (et demande une photo si besoin).
/// Bandeau discret non bloquant : bascule, retour, erreur (phrase humaine + une action).
/// Erreur du chat traduite depuis son code (`errorc|code|retry_at|message d'origine`).
String _sourceName(BuildContext context, String source) => switch (source) {
      'claude' => 'Claude',
      'chatgpt' => 'ChatGPT',
      'json' || 'text' => context.t('import_src_other'),
      _ => source,
    };

String _errorText(BuildContext context, List<String> parts) {
  final code = parts.length > 1 ? parts[1] : '';
  final at = parts.length > 2 ? double.tryParse(parts[2]) : null;
  var msg = switch (code) {
    'media_reference_missing' => context.t('err_image_reference'),
    'offline' => context.t('err_offline'),
    'all_failed' => context.t('err_all_failed'),
    'no_model' => context.t('err_no_model'),
    'strict_waiting' => context.t('err_strict'),
    'agent_timeout' => context.t('err_agent_timeout'),
    'agent_steps' => context.t('err_agent_steps'),
    _ => parts.length > 3 ? parts.sublist(3).join('|') : context.t('error_generic'),
  };
  if (at != null) {
    final d = DateTime.fromMillisecondsSinceEpoch((at * 1000).round());
    msg += ' ${context.t('err_back_at', {'t': '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}'})}';
  }
  return msg;
}

class _Notice extends StatelessWidget {
  const _Notice(this.raw, {required this.onRetry});
  final String raw;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final parts = raw.split('|');
    final scheme = Theme.of(context).colorScheme;
    final (icon, text, color, action) = switch (parts.first) {
      'switched' => (
          Icons.swap_horiz,
          context.t('switched', {'to': parts[1], 'reason': parts.length > 2 ? parts[2] : ''}) +
              ((parts.length > 3 ? int.tryParse(parts[3]) ?? 1 : 1) > 1
                  ? ' · ${context.t('switch_count', {'n': parts[3]})}'
                  : ''),
          scheme.tertiary,
          false),
      'returned' => (Icons.undo, context.t('returned', {'model': parts[1]}), scheme.secondary, false),
      'stream_reset' => (Icons.refresh, context.t('stream_interrupted'), scheme.tertiary, false),
      'media' => (Icons.auto_awesome, context.t('media_switch'), scheme.tertiary, false),
      'errorc' => (Icons.error_outline, _errorText(context, parts), scheme.error, true),
      'document' => (Icons.description_outlined, context.t('doc_attached', {'name': parts.length > 1 ? parts[1] : '', 'n': parts.length > 2 ? parts[2] : '?'}), scheme.secondary, false),
      'review' => (
          parts.length > 1 && parts[1] == '1' ? Icons.verified_outlined : Icons.report_outlined,
          parts.length > 1 && parts[1] == '1'
              ? context.t('review_ok', {'m': parts.length > 2 ? parts[2] : ''})
              : context.t('review_issues', {'m': parts.length > 2 ? parts[2] : '', 'issues': parts.skip(3).join('|').split('\u0001').join(' ; ')}),
          parts.length > 1 && parts[1] == '1' ? scheme.secondary : scheme.tertiary,
          false),
      'imported' => (Icons.download_done, context.t(parts.length > 3 && parts[3] != '1' ? 'imported_many' : 'imported', {'n': parts.length > 1 ? parts[1] : '?', 'src': _sourceName(context, parts.length > 2 ? parts[2] : ''), 'k': parts.length > 3 ? parts[3] : '1'}), scheme.secondary, false),
      'offline_queued' => (Icons.cloud_upload_outlined, context.t('offline_queued'), scheme.tertiary, false),
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
        if (parts.first == 'review' && parts.length > 1 && parts[1] == '0')
          TextButton(
            onPressed: () => AppScope.of(context).chat.send(context.t('review_fix_p', {
              'issues': parts.skip(3).join('|').split('\u0001').join(' ; '),
            })),
            child: Text(context.t('review_fix')),
          ),
        if (parts.first == 'offline_queued')
          TextButton(
            onPressed: () => AppScope.of(context).chat.cancelOfflineQueue(),
            child: Text(context.t('cancel')),
          ),
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
        : status.startsWith('offline|')
        ? context.t('offline_wait')
        : status.startsWith('book_chapter|') || status.startsWith('slides_section|')
            ? context.t(status.split('|')[0], {'n': status.split('|')[1], 't': status.split('|')[2]})
        : status.startsWith('waiting|')
            ? context.t('waiting', {'s': status.substring(8)})
        : status.startsWith('orchestrating|')
            ? context.t('orchestrating', {'n': status.substring(14)})
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

/// Plan d'une tâche complexe : étapes (et modèles en parallèle), « Continuer » pas à pas.
class _PlanBar extends StatelessWidget {
  const _PlanBar(this.chat);
  final ChatController chat;

  @override
  Widget build(BuildContext context) {
    final plan = chat.plan!;
    final steps = (plan['steps'] as List? ?? const []).cast<Map>();
    final parallel = plan['mode'] == 'parallel';
    final current = (plan['current'] as num? ?? 0).toInt();
    final active = plan['status'] == 'active';
    final scheme = Theme.of(context).colorScheme;
    final small = Theme.of(context).textTheme.bodySmall;
    Widget icon(int i) {
      final st = chat.planSteps[i]?['status'];
      if (parallel) {
        return switch (st) {
          'running' => const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
          'done' => const Icon(Icons.check_circle, size: 16, color: Color(0xFF2E9E6B)),
          'failed' => Icon(Icons.error_outline, size: 16, color: scheme.error),
          _ => Icon(Icons.circle_outlined, size: 16, color: scheme.outline),
        };
      }
      if (!active || i < current) return const Icon(Icons.check_circle, size: 16, color: Color(0xFF2E9E6B));
      if (i == current) return Icon(Icons.play_circle, size: 16, color: scheme.primary);
      return Icon(Icons.circle_outlined, size: 16, color: scheme.outline);
    }

    return Card(
      margin: const EdgeInsets.fromLTRB(12, 4, 12, 4),
      child: ExpansionTile(
        dense: true,
        initiallyExpanded: parallel && chat.busy,
        leading: Icon(parallel ? Icons.call_split : Icons.format_list_numbered, size: 20),
        title: Text(parallel
            ? context.t('plan_parallel', {'n': '${steps.length}'})
            : context.t('plan_steps', {'k': '${(current + 1).clamp(1, steps.length)}', 'n': '${steps.length}'})),
        subtitle: Text('${plan['goal'] ?? ''}', maxLines: 1, overflow: TextOverflow.ellipsis, style: small),
        trailing: active && !parallel && !chat.busy && current + 1 < steps.length
            ? FilledButton.tonal(
                onPressed: () => chat.continuePlan(context.t('plan_continue')),
                child: Text(context.t('plan_continue')),
              )
            : null,
        children: [
          for (final (i, step) in steps.indexed)
            ListTile(
              dense: true,
              leading: icon(i),
              minLeadingWidth: 16,
              title: Text('${i + 1}. ${step['title']}'),
              subtitle: parallel && chat.planSteps[i]?['model'] != null && '${chat.planSteps[i]!['model']}'.isNotEmpty
                  ? Text('${chat.planSteps[i]!['model']}', style: small)
                  : null,
            ),
          OverflowBar(alignment: MainAxisAlignment.end, children: [
            if (chat.conversationId != null)
              TextButton.icon(
                icon: const Icon(Icons.inventory_2_outlined, size: 18),
                label: Text(context.t('plan_results')),
                onPressed: () => showTaskResults(context, chat.conversationId!),
              ),
            if (active && !chat.busy) TextButton(onPressed: chat.dropPlan, child: Text(context.t('plan_drop'))),
          ]),
        ],
      ),
    );
  }
}

/// Tâche lancée sur un autre appareil, suivie en direct (synchro toutes les ~20 s).
class _RemoteTaskBar extends StatelessWidget {
  const _RemoteTaskBar(this.task, {required this.current});
  final RemoteTask task;
  final bool current;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final small = Theme.of(context).textTheme.bodySmall;
    return Material(
      color: scheme.secondaryContainer,
      child: InkWell(
        onTap: current ? null : () => AppScope.of(context).chat.open(task.conversationId),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(children: [
            const Icon(Icons.devices_other, size: 18),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(context.t('remote_task', {'d': task.device, 't': task.title.isEmpty ? '…' : task.title}),
                    maxLines: 1, overflow: TextOverflow.ellipsis),
                if (task.partial.isNotEmpty)
                  Text(task.partial.replaceAll('\n', ' ').trim(), maxLines: current ? 3 : 1, overflow: TextOverflow.ellipsis, style: small),
              ]),
            ),
            if (!current) const Icon(Icons.chevron_right),
          ]),
        ),
      ),
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
        : context.t('tool_confirm', {'name': p.tools.map((t) {
          final label = context.t('tool_${t['name']}');
          return label == 'tool_${t['name']}' ? '${t['name']}' : label;
        }).join(', ')});
    // Aperçu de l'action (différence du fichier, commande du terminal) avant d'accepter.
    final preview = p.tools.map((t) => t['preview']).whereType<String>().join('\n');
    return MaterialBanner(
      content: preview.isEmpty
          ? Text(text)
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(text),
              const SizedBox(height: 6),
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 220),
                child: SingleChildScrollView(
                  child: SelectableText.rich(TextSpan(children: [
                    for (final line in preview.split('\n'))
                      TextSpan(
                        text: '$line\n',
                        style: TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 12,
                          color: line.startsWith('+') && !line.startsWith('+++')
                              ? const Color(0xFF2E9E6B)
                              : line.startsWith('-') && !line.startsWith('---')
                                  ? Theme.of(context).colorScheme.error
                                  : null,
                        ),
                      ),
                  ])),
                ),
              ),
            ]),
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
  List<Map<String, dynamic>> folders = [];
  String? folder; // null = toutes les discussions

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _load();
  }

  Future<void> _load() async {
    final b = AppScope.of(context).backend;
    if (b.state != BackendState.ready) return;
    final data = await b.getJson('/tontolo/conversations', {'limit': 200, if (folder != null) 'folder': folder}) as List;
    List<dynamic> f = const [];
    try {
      f = await b.getJson('/tontolo/folders') as List;
    } catch (_) {} // ancien cœur distant sans dossiers
    if (mounted) {
      setState(() {
        items = data.cast<Map<String, dynamic>>();
        folders = f.cast<Map<String, dynamic>>();
      });
    }
  }

  /// « Déplacer vers un dossier » : dossiers existants, nouveau dossier, ou aucun.
  Future<void> _moveToFolder(Map<String, dynamic> c) async {
    final ctrl = TextEditingController();
    final chosen = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(context.t('move_to_folder')),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final f in folders)
              ActionChip(
                avatar: const Icon(Icons.folder_outlined, size: 16),
                label: Text('${f['folder']}'),
                onPressed: () => Navigator.pop(context, '${f['folder']}'),
              ),
            if ((c['folder'] ?? '').toString().isNotEmpty)
              ActionChip(
                avatar: const Icon(Icons.folder_off_outlined, size: 16),
                label: Text(context.t('no_folder')),
                onPressed: () => Navigator.pop(context, ''),
              ),
          ]),
          const SizedBox(height: 12),
          TextField(controller: ctrl, decoration: InputDecoration(labelText: context.t('new_folder')), maxLength: 60),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(context.t('cancel'))),
          FilledButton(onPressed: () => Navigator.pop(context, ctrl.text.trim()), child: Text(context.t('save'))),
        ],
      ),
    );
    if (chosen == null || !mounted) return;
    await AppScope.of(context).backend.sendJson('PATCH', '/tontolo/conversations/${c['id']}', {'folder': chosen});
    _load();
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
        ListTile(
          leading: const Icon(Icons.photo_library_outlined),
          title: Text(context.t('creations')),
          onTap: () {
            Navigator.pop(context);
            ShellNav.maybeOf(context)?.go(1);
          },
        ),
        ListTile(
          leading: const Icon(Icons.settings_outlined),
          title: Text(context.t('settings')),
          onTap: () {
            Navigator.pop(context);
            ShellNav.maybeOf(context)?.go(2);
          },
        ),
        ListTile(
          leading: const Icon(Icons.move_to_inbox_outlined),
          title: Text(context.t('import_title')),
          subtitle: Text(context.t('import_sub'), maxLines: 1, overflow: TextOverflow.ellipsis),
          onTap: () {
            Navigator.pop(context);
            showImportDialog(context);
          },
        ),
        const Divider(),
        if (folders.isNotEmpty)
          SizedBox(
            height: 44,
            child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 16), children: [
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: ChoiceChip(
                  label: Text(context.t('f_all')),
                  selected: folder == null,
                  onSelected: (_) {
                    folder = null;
                    _load();
                  },
                ),
              ),
              for (final f in folders)
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    avatar: const Icon(Icons.folder_outlined, size: 16),
                    label: Text('${f['folder']} · ${f['count']}'),
                    selected: folder == f['folder'],
                    onSelected: (_) {
                      folder = '${f['folder']}';
                      _load();
                    },
                  ),
                ),
            ]),
          ),
        if (folder != null)
          SwitchListTile(
            dense: true,
            secondary: const Icon(Icons.hub_outlined, size: 20),
            title: Text(context.t('folder_share')),
            subtitle: Text(context.t('folder_share_help')),
            value: folders.any((f) => f['folder'] == folder && f['shared'] == true),
            onChanged: (v) async {
              await scope.backend.sendJson('PUT', '/tontolo/folders/share', {'folder': folder, 'share': v});
              _load();
            },
          ),
        for (final c in items)
          ListTile(
            leading: c['pinned'] == 1
                ? const Icon(Icons.push_pin, size: 18)
                : '${c['mode'] ?? ''}'.startsWith('learn')
                    ? Icon(Icons.school_outlined, size: 18, color: Theme.of(context).colorScheme.tertiary)
                    : null,
            title: ListenableBuilder(
              listenable: Listenable.merge([scope.activity, scope.cloud]),
              builder: (context, _) {
                final dot = scope.activity.dotFor('${c['id']}');
                return Row(children: [
                  Expanded(child: Text('${c['title']}'.isEmpty ? '…' : '${c['title']}', maxLines: 1, overflow: TextOverflow.ellipsis)),
                  if (dot != null) ...[const SizedBox(width: 6), ActivityDot(dot)],
                ]);
              },
            ),
            selected: c['id'] == scope.chat.conversationId,
            onTap: () {
              scope.chat.open('${c['id']}');
              Navigator.pop(context);
            },
            trailing: PopupMenuButton<String>(
              onSelected: (v) async {
                if (v == 'pin') {
                  await scope.backend.sendJson('PUT', '/tontolo/conversations/${c['id']}/pin', {'pinned': c['pinned'] != 1});
                } else if (v == 'folder') {
                  await _moveToFolder(c);
                  return;
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
                PopupMenuItem(value: 'folder', child: Text(context.t('move_to_folder'))),
                PopupMenuItem(value: 'delete', child: Text(context.t('delete'))),
              ],
            ),
          ),
      ],
    );
  }
}
