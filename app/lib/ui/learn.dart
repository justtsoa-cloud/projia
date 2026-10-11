// Mode Apprendre (élèves et étudiants) : bascule Général / Apprendre, accueil dédié (niveau,
// matières, raccourcis d'étude), actions rapides sous les réponses du tuteur, et rendu
// interactif des quiz et fiches de révision que le tuteur envoie sous forme de blocs JSON
// (```quiz … ``` et ```flashcards … ```).

import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/chat_controller.dart';
import '../main.dart';
import 'message_view.dart' show RichMarkdown;

const learnLevels = ['primaire', 'college', 'lycee', 'universite', 'adulte'];

/// Bascule bien visible entre le mode général et le mode Apprendre.
class ModeToggle extends StatelessWidget {
  const ModeToggle({super.key, required this.chat});
  final ChatController chat;

  @override
  Widget build(BuildContext context) {
    final mode = chat.mode;
    final scheme = Theme.of(context).colorScheme;
    Widget seg(String value, IconData icon, String label, VoidCallback onTap) {
      final selected = mode == value;
      final bg = switch (value) { 'learn' => scheme.tertiary, 'agent' => scheme.secondary, _ => scheme.primary };
      final fg = switch (value) { 'learn' => scheme.onTertiary, 'agent' => scheme.onSecondary, _ => scheme.onPrimary };
      return Expanded(
        child: Material(
          color: selected ? bg : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
          child: InkWell(
            borderRadius: BorderRadius.circular(20),
            // L'agent sélectionné se rechoisit d'un nouvel appui (Chercheur, Développeur…).
            onTap: selected && value != 'agent'
                ? null
                : () {
                    HapticFeedback.selectionClick();
                    onTap();
                  },
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 7),
              child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Icon(icon, size: 17, color: selected ? fg : scheme.onSurfaceVariant),
                const SizedBox(width: 5),
                Flexible(
                  // Réduit plutôt que tronqué quand la barre est étroite (menu ⋮ affiché).
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(label,
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          color: selected ? fg : scheme.onSurfaceVariant)),
                  ),
                ),
              ]),
            ),
          ),
        ),
      );
    }

    return Semantics(
      label: context.t('mode_toggle'),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 340),
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(color: scheme.surfaceContainerHighest, borderRadius: BorderRadius.circular(23)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          seg('general', Icons.chat_bubble_outline, context.t('mode_general'), () => chat.setLearn(false)),
          seg('learn', Icons.school_outlined, context.t('mode_learn'), () => chat.setLearn(true)),
          seg('agent', Icons.smart_toy_outlined, context.t('mode_agent'), () => showAgentSheet(context, chat)),
        ]),
      ),
    );
  }
}

/// Agents prêts à l'emploi et choix gratuit / payant (gratuit par défaut).
const agentKinds = [
  ('auto', Icons.auto_awesome),
  ('researcher', Icons.travel_explore),
  ('developer', Icons.code),
  ('writer', Icons.edit_note),
  ('analyst', Icons.query_stats),
];

Future<void> showAgentSheet(BuildContext context, ChatController chat) => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _AgentSheet(chat: chat),
    );

class _AgentSheet extends StatefulWidget {
  const _AgentSheet({required this.chat});
  final ChatController chat;

  @override
  State<_AgentSheet> createState() => _AgentSheetState();
}

class _AgentSheetState extends State<_AgentSheet> {
  String? paid; // off | ask | auto

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (paid == null) _load();
  }

  Future<void> _load() async {
    try {
      final s = await AppScope.of(context).backend.getJson('/tontolo/settings') as Map<String, dynamic>;
      if (mounted) setState(() => paid = '${(s['paid'] as Map?)?['fallback'] ?? 'off'}');
    } catch (_) {
      if (mounted) setState(() => paid = 'off');
    }
  }

  Future<void> _setPaid(String v) async {
    setState(() => paid = v);
    await AppScope.of(context).backend.sendJson('PUT', '/tontolo/settings', {'paid': {'fallback': v}});
  }

  @override
  Widget build(BuildContext context) {
    final chat = widget.chat;
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(8, 0, 8, 12),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
            child: Text(context.t('agent_title'), style: Theme.of(context).textTheme.titleLarge),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Text(context.t('agent_help'), style: Theme.of(context).textTheme.bodySmall),
          ),
          for (final (k, icon) in agentKinds)
            ListTile(
              leading: Icon(icon),
              title: Text(context.t('agent_$k')),
              subtitle: Text(context.t('agent_${k}_sub')),
              selected: chat.agent == k,
              onTap: () {
                chat.setAgent(k);
                Navigator.pop(context);
              },
            ),
          if (chat.agent != null)
            ListTile(
              leading: const Icon(Icons.close),
              title: Text(context.t('agent_off')),
              onTap: () {
                chat.setAgent(null);
                Navigator.pop(context);
              },
            ),
          const Divider(),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: Text(context.t('agent_paid'), style: Theme.of(context).textTheme.titleSmall),
          ),
          if (paid != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SegmentedButton<String>(
                segments: [
                  ButtonSegment(value: 'off', label: Text(context.t('agent_paid_off'))),
                  ButtonSegment(value: 'ask', label: Text(context.t('agent_paid_ask'))),
                  ButtonSegment(value: 'auto', label: Text(context.t('agent_paid_auto'))),
                ],
                selected: {paid!},
                onSelectionChanged: (s) => _setPaid(s.first),
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: Text(context.t('agent_paid_help'), style: Theme.of(context).textTheme.bodySmall),
          ),
        ]),
      ),
    );
  }
}

class _LearnShortcut {
  const _LearnShortcut(this.icon, this.key, {this.photo = false});
  final IconData icon;
  final String key; // titre : key ; sous-titre : key_sub ; texte proposé : key_p
  final bool photo;
}

/// Quatre façons d'étudier, visibles tout de suite ; le reste est replié dans « Plus ».
const _mainShortcuts = [
  _LearnShortcut(Icons.photo_camera_outlined, 'ls_exercise', photo: true),
  _LearnShortcut(Icons.lightbulb_outline, 'ls_explain'),
  _LearnShortcut(Icons.quiz_outlined, 'ls_quiz'),
  _LearnShortcut(Icons.account_tree_outlined, 'ls_mindmap'),
];
const _moreShortcuts = [
  _LearnShortcut(Icons.style_outlined, 'ls_cards'),
  _LearnShortcut(Icons.event_note_outlined, 'ls_plan'),
  _LearnShortcut(Icons.fact_check_outlined, 'ls_check'),
  _LearnShortcut(Icons.workspace_premium_outlined, 'ls_exam'),
  _LearnShortcut(Icons.record_voice_over_outlined, 'ls_oral'),
];

/// Accueil du mode Apprendre : une question, le niveau en un geste, quatre grandes actions.
class LearnEmptyState extends StatefulWidget {
  const LearnEmptyState({super.key, required this.onPrefill});
  final void Function(String text, {bool photo}) onPrefill;

  @override
  State<LearnEmptyState> createState() => _LearnEmptyStateState();
}

class _LearnEmptyStateState extends State<LearnEmptyState> {
  bool more = false;

  Widget _tile(BuildContext context, _LearnShortcut s, {bool big = false}) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.tertiaryContainer.withValues(alpha: big ? 0.7 : 0.45),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () {
          HapticFeedback.selectionClick();
          widget.onPrefill(context.t('${s.key}_p', {'subject': ''}), photo: s.photo);
        },
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: big ? 14 : 8),
          child: Row(children: [
            CircleAvatar(radius: big ? 22 : 17, backgroundColor: scheme.tertiaryContainer, child: Icon(s.icon, size: big ? 24 : 19, color: scheme.onTertiaryContainer)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(context.t(s.key), maxLines: 2, overflow: TextOverflow.ellipsis, style: (big ? Theme.of(context).textTheme.titleMedium : Theme.of(context).textTheme.titleSmall)?.copyWith(height: 1.15)),
                const SizedBox(height: 2),
                Text(context.t('${s.key}_sub'),
                    maxLines: 2, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant, height: 1.15)),
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final chat = AppScope.of(context).chat;
    final scheme = Theme.of(context).colorScheme;
    final wide = MediaQuery.sizeOf(context).width >= 600;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            CircleAvatar(radius: 28, backgroundColor: scheme.tertiaryContainer, child: Icon(Icons.school, size: 30, color: scheme.onTertiaryContainer)),
            const SizedBox(height: 10),
            Text(context.t('learn_hello'), style: Theme.of(context).textTheme.titleLarge, textAlign: TextAlign.center),
            const SizedBox(height: 4),
            Text(context.t('learn_promise'), style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant), textAlign: TextAlign.center),
            const SizedBox(height: 12),
            Center(
              child: PopupMenuButton<String>(
                tooltip: context.t('learn_level'),
                onSelected: chat.setLevel,
                itemBuilder: (context) => [
                  for (final l in learnLevels) CheckedPopupMenuItem(value: l, checked: chat.level == l, child: Text(context.t('lvl_$l'))),
                ],
                child: Chip(
                  avatar: const Icon(Icons.stairs_outlined, size: 18),
                  label: Text('${context.t('learn_level_is', {'l': context.t('lvl_${chat.level}')})}  ▾'),
                ),
              ),
            ),
            const SizedBox(height: 14),
            GridView.count(
              crossAxisCount: wide ? 2 : 1,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              childAspectRatio: wide ? 3.6 : 4.6,
              children: [for (final s in _mainShortcuts) _tile(context, s, big: true)],
            ),
            const SizedBox(height: 6),
            TextButton.icon(
              icon: Icon(more ? Icons.expand_less : Icons.expand_more),
              label: Text(context.t(more ? 'learn_less' : 'learn_more')),
              onPressed: () => setState(() => more = !more),
            ),
            if (more)
              GridView.count(
                crossAxisCount: wide ? 3 : 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 8,
                crossAxisSpacing: 8,
                childAspectRatio: wide ? 2.6 : 2.15,
                children: [for (final s in _moreShortcuts) _tile(context, s)],
              ),
          ]),
        ),
      ),
    );
  }
}

/// Actions rapides sous la dernière réponse du tuteur.
class LearnActions extends StatelessWidget {
  const LearnActions({super.key, required this.onSend, required this.onPrefill});
  final ValueChanged<String> onSend;
  final ValueChanged<String> onPrefill;

  static const _send = ['la_hint', 'la_lost', 'la_next', 'la_quiz'];

  @override
  Widget build(BuildContext context) {
    final icons = {
      'la_hint': Icons.lightbulb_outline,
      'la_lost': Icons.help_outline,
      'la_quiz': Icons.quiz_outlined,
      'la_next': Icons.arrow_forward,
    };
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 12, 6),
      child: Wrap(spacing: 6, runSpacing: 4, children: [
        ActionChip(
          avatar: const Icon(Icons.edit_note, size: 18),
          label: Text(context.t('la_answer')),
          onPressed: () => onPrefill(context.t('la_answer_p')),
        ),
        for (final k in _send)
          ActionChip(
            avatar: Icon(icons[k], size: 18),
            label: Text(context.t(k)),
            onPressed: () {
              HapticFeedback.selectionClick();
              onSend(context.t('${k}_p'));
            },
          ),
      ]),
    );
  }
}

// --- Blocs interactifs -------------------------------------------------------------------

sealed class LearnSegment {}

class MarkdownSegment extends LearnSegment {
  MarkdownSegment(this.text);
  final String text;
}

class QuizSegment extends LearnSegment {
  QuizSegment(this.title, this.questions);
  final String title;
  final List<QuizQuestion> questions;
}

class CardsSegment extends LearnSegment {
  CardsSegment(this.cards);
  final List<(String, String)> cards;
}

class PendingSegment extends LearnSegment {
  PendingSegment(this.kind);
  final String kind;
}

class QuizQuestion {
  QuizQuestion(this.q, this.choices, this.answer, this.explain);
  final String q;
  final List<String> choices;
  final int answer;
  final String explain;
}

final _block = RegExp(r'```(quiz|flashcards)[ \t]*\n([\s\S]*?)```');
final _open = RegExp(r'```(quiz|flashcards)[ \t]*\n[\s\S]*$');

/// Découpe une réponse en Markdown et blocs interactifs. Un bloc illisible reste affiché tel
/// quel (Markdown) ; un bloc pas encore terminé (réponse en cours) devient « en préparation ».
List<LearnSegment> splitLearnBlocks(String text) {
  if (!text.contains('```quiz') && !text.contains('```flashcards')) return [MarkdownSegment(text)];
  final out = <LearnSegment>[];
  var pos = 0;
  for (final m in _block.allMatches(text)) {
    if (m.start > pos) out.add(MarkdownSegment(text.substring(pos, m.start)));
    out.add(_parseBlock(m.group(1)!, m.group(2)!) ?? MarkdownSegment(m.group(0)!));
    pos = m.end;
  }
  final rest = text.substring(pos);
  final open = _open.firstMatch(rest);
  if (open != null) {
    if (open.start > 0) out.add(MarkdownSegment(rest.substring(0, open.start)));
    out.add(PendingSegment(open.group(1)!));
  } else if (rest.trim().isNotEmpty) {
    out.add(MarkdownSegment(rest));
  }
  return out.where((s) => s is! MarkdownSegment || s.text.trim().isNotEmpty).toList();
}

LearnSegment? _parseBlock(String kind, String body) {
  try {
    final data = jsonDecode(body.trim());
    if (kind == 'quiz') {
      final map = data is Map ? data : {'questions': data};
      final qs = <QuizQuestion>[];
      for (final q in (map['questions'] as List).take(20)) {
        final choices = [for (final c in (q['choices'] as List).take(6)) '$c'];
        final answer = (q['answer'] as num).toInt();
        if (choices.length < 2 || answer < 0 || answer >= choices.length) continue;
        qs.add(QuizQuestion('${q['q'] ?? q['question'] ?? ''}', choices, answer, '${q['explain'] ?? ''}'));
      }
      return qs.isEmpty ? null : QuizSegment('${map['title'] ?? ''}', qs);
    }
    final list = (data is Map ? data['cards'] : data) as List;
    final cards = [
      for (final c in list.take(60))
        if (c is Map && c['front'] != null && c['back'] != null) ('${c['front']}', '${c['back']}'),
    ];
    return cards.isEmpty ? null : CardsSegment(cards);
  } catch (_) {
    return null;
  }
}

/// Corps d'une réponse avec blocs interactifs (utilisé par MessageView).
class LearnBody extends StatelessWidget {
  const LearnBody(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    final segments = splitLearnBlocks(text);
    if (segments.length == 1 && segments.first is MarkdownSegment) return RichMarkdown(text);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final s in segments)
        switch (s) {
          MarkdownSegment(:final text) => RichMarkdown(text),
          QuizSegment() => Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: QuizCard(quiz: s)),
          CardsSegment() => Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: FlashcardsDeck(cards: s.cards)),
          PendingSegment(:final kind) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(children: [
                const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                const SizedBox(width: 10),
                Text(context.t(kind == 'quiz' ? 'quiz_preparing' : 'cards_preparing')),
              ]),
            ),
        },
    ]);
  }
}

class QuizCard extends StatefulWidget {
  const QuizCard({super.key, required this.quiz});
  final QuizSegment quiz;

  @override
  State<QuizCard> createState() => _QuizCardState();
}

class _QuizCardState extends State<QuizCard> {
  int index = 0;
  int? picked;
  final Map<int, int> answers = {};

  List<QuizQuestion> get qs => widget.quiz.questions;
  bool get finished => index >= qs.length;
  int get score => answers.entries.where((e) => qs[e.key].answer == e.value).length;

  void _pick(int i) {
    if (picked != null) return;
    HapticFeedback.lightImpact();
    setState(() {
      picked = i;
      answers[index] = i;
    });
  }

  void _next() => setState(() {
        index++;
        picked = null;
      });

  void _restart() => setState(() {
        index = 0;
        picked = null;
        answers.clear();
      });

  String _report(BuildContext context) {
    final wrong = [
      for (final e in answers.entries)
        if (qs[e.key].answer != e.value)
          context.t('quiz_wrong_line', {'n': '${e.key + 1}', 'q': qs[e.key].q, 'mine': qs[e.key].choices[e.value], 'good': qs[e.key].choices[qs[e.key].answer]}),
    ];
    return context.t(wrong.isEmpty ? 'quiz_report_perfect' : 'quiz_report',
        {'title': widget.quiz.title, 'score': '$score', 'total': '${qs.length}', 'wrong': wrong.join('\n')});
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Card(
      margin: EdgeInsets.zero,
      color: scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: scheme.tertiary.withValues(alpha: 0.4))),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: AnimatedSize(
          duration: const Duration(milliseconds: 200),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Icon(Icons.quiz, color: scheme.tertiary),
              const SizedBox(width: 8),
              Expanded(child: Text(widget.quiz.title.isEmpty ? context.t('quiz') : widget.quiz.title, style: text.titleSmall)),
              if (!finished) Text('${index + 1}/${qs.length}', style: text.labelMedium),
            ]),
            const SizedBox(height: 8),
            if (!finished) ...[
              LinearProgressIndicator(value: index / qs.length, color: scheme.tertiary),
              const SizedBox(height: 10),
              RichMarkdown(qs[index].q),
              const SizedBox(height: 8),
              for (final (i, c) in qs[index].choices.indexed)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: _Choice(
                    label: String.fromCharCode(65 + i),
                    text: c,
                    state: picked == null
                        ? _ChoiceState.idle
                        : i == qs[index].answer
                            ? _ChoiceState.good
                            : i == picked
                                ? _ChoiceState.bad
                                : _ChoiceState.dim,
                    onTap: () => _pick(i),
                  ),
                ),
              if (picked != null) ...[
                Row(children: [
                  Icon(picked == qs[index].answer ? Icons.check_circle : Icons.cancel,
                      color: picked == qs[index].answer ? Colors.green.shade600 : scheme.error),
                  const SizedBox(width: 6),
                  Text(context.t(picked == qs[index].answer ? 'quiz_right' : 'quiz_wrong'), style: text.titleSmall),
                ]),
                if (qs[index].explain.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 4), child: RichMarkdown(qs[index].explain)),
                const SizedBox(height: 8),
                Align(
                  alignment: Alignment.centerRight,
                  child: FilledButton(onPressed: _next, child: Text(context.t(index + 1 < qs.length ? 'quiz_next' : 'quiz_finish'))),
                ),
              ],
            ] else ...[
              Center(
                child: Text('$score / ${qs.length}', style: text.displaySmall?.copyWith(color: scheme.tertiary, fontWeight: FontWeight.w700)),
              ),
              Center(child: Text(context.t(score == qs.length ? 'quiz_perfect' : score * 2 >= qs.length ? 'quiz_good' : 'quiz_keep_going'))),
              const SizedBox(height: 10),
              Wrap(alignment: WrapAlignment.center, spacing: 8, runSpacing: 6, children: [
                OutlinedButton.icon(icon: const Icon(Icons.replay), label: Text(context.t('quiz_restart')), onPressed: _restart),
                FilledButton.icon(
                  icon: const Icon(Icons.send),
                  label: Text(context.t('quiz_send')),
                  onPressed: () => AppScope.of(context).chat.send(_report(context)),
                ),
              ]),
            ],
          ]),
        ),
      ),
    );
  }
}

enum _ChoiceState { idle, good, bad, dim }

class _Choice extends StatelessWidget {
  const _Choice({required this.label, required this.text, required this.state, required this.onTap});
  final String label;
  final String text;
  final _ChoiceState state;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (bg, border) = switch (state) {
      _ChoiceState.good => (Colors.green.withValues(alpha: 0.18), Colors.green.shade600),
      _ChoiceState.bad => (scheme.errorContainer, scheme.error),
      _ChoiceState.dim => (scheme.surface.withValues(alpha: 0.5), scheme.outlineVariant),
      _ChoiceState.idle => (scheme.surface, scheme.outlineVariant),
    };
    return Material(
      color: bg,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: border)),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: state == _ChoiceState.idle ? onTap : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Row(children: [
            CircleAvatar(radius: 12, backgroundColor: border.withValues(alpha: 0.2), child: Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600))),
            const SizedBox(width: 10),
            Expanded(child: RichMarkdown(text, selectable: false)),
          ]),
        ),
      ),
    );
  }
}

/// Fiches de révision : touchez pour retourner, « Je savais » / « À revoir », puis on revoit
/// seulement les cartes à retravailler.
class FlashcardsDeck extends StatefulWidget {
  const FlashcardsDeck({super.key, required this.cards});
  final List<(String, String)> cards;

  @override
  State<FlashcardsDeck> createState() => _FlashcardsDeckState();
}

class _FlashcardsDeckState extends State<FlashcardsDeck> {
  late List<int> deck = List.generate(widget.cards.length, (i) => i);
  final Set<int> toReview = {};
  int pos = 0;
  bool back = false;
  int known = 0;

  bool get done => pos >= deck.length;

  void _answer(bool knew) {
    HapticFeedback.selectionClick();
    setState(() {
      if (knew) {
        known++;
      } else {
        toReview.add(deck[pos]);
      }
      pos++;
      back = false;
    });
  }

  void _again({bool onlyReview = true}) => setState(() {
        deck = onlyReview ? toReview.toList() : List.generate(widget.cards.length, (i) => i);
        toReview.clear();
        pos = 0;
        known = 0;
        back = false;
      });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Card(
      margin: EdgeInsets.zero,
      color: scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: scheme.secondary.withValues(alpha: 0.4))),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Icon(Icons.style, color: scheme.secondary),
            const SizedBox(width: 8),
            Expanded(child: Text(context.t('cards_title'), style: text.titleSmall)),
            if (!done) Text('${pos + 1}/${deck.length}', style: text.labelMedium),
          ]),
          const SizedBox(height: 10),
          if (!done) ...[
            GestureDetector(
              onTap: () => setState(() => back = !back),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 280),
                transitionBuilder: (child, anim) => AnimatedBuilder(
                  animation: anim,
                  child: child,
                  builder: (context, child) => Transform(
                    alignment: Alignment.center,
                    transform: Matrix4.rotationY((1 - anim.value) * math.pi / 2),
                    child: child,
                  ),
                ),
                child: Container(
                  key: ValueKey('${deck[pos]}-$back'),
                  constraints: const BoxConstraints(minHeight: 120),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: back ? scheme.secondaryContainer : scheme.surface,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: scheme.outlineVariant),
                  ),
                  child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text(context.t(back ? 'cards_back' : 'cards_front'), style: text.labelSmall?.copyWith(color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 6),
                    RichMarkdown(back ? widget.cards[deck[pos]].$2 : widget.cards[deck[pos]].$1, selectable: false),
                    if (!back) ...[
                      const SizedBox(height: 8),
                      Text(context.t('cards_tap'), style: text.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
                    ],
                  ]),
                ),
              ),
            ),
            const SizedBox(height: 10),
            if (back)
              Row(children: [
                Expanded(child: OutlinedButton.icon(icon: const Icon(Icons.refresh), label: Text(context.t('cards_review')), onPressed: () => _answer(false))),
                const SizedBox(width: 8),
                Expanded(child: FilledButton.icon(icon: const Icon(Icons.check), label: Text(context.t('cards_knew')), onPressed: () => _answer(true))),
              ]),
          ] else ...[
            Center(child: Text(context.t('cards_done', {'k': '$known', 'n': '${deck.length}'}), style: text.titleMedium)),
            const SizedBox(height: 8),
            Wrap(alignment: WrapAlignment.center, spacing: 8, children: [
              if (toReview.isNotEmpty) FilledButton.icon(icon: const Icon(Icons.refresh), label: Text(context.t('cards_again', {'n': '${toReview.length}'})), onPressed: _again),
              OutlinedButton.icon(icon: const Icon(Icons.replay), label: Text(context.t('cards_all')), onPressed: () => _again(onlyReview: false)),
            ]),
          ],
        ]),
      ),
    );
  }
}
