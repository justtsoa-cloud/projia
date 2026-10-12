// Questions à choix posées par Tontolo pour préciser la demande (réponse en un toucher).
import 'package:flutter/material.dart';

import '../core/chat_controller.dart';
import '../main.dart';

class QuestionCard extends StatefulWidget {
  const QuestionCard({super.key, required this.questions, required this.onSend});
  final List<AskedQuestion> questions;
  final void Function(String text) onSend;

  /// Réponse envoyée : une ligne « question → choix » par question répondue.
  static String compose(List<AskedQuestion> qs, List<Set<String>> picked, [String other = '']) => [
        for (var i = 0; i < qs.length; i++)
          if (picked[i].isNotEmpty) '${qs[i].question} → ${picked[i].join(', ')}',
        if (other.trim().isNotEmpty) other.trim(),
      ].join('\n');

  @override
  State<QuestionCard> createState() => _QuestionCardState();
}

class _QuestionCardState extends State<QuestionCard> {
  late List<Set<String>> picked = [for (final _ in widget.questions) <String>{}];
  final other = TextEditingController(); // précision libre, en plus des choix

  @override
  void dispose() {
    other.dispose();
    super.dispose();
  }

  void _send() => widget.onSend(QuestionCard.compose(widget.questions, picked, other.text));

  @override
  void didUpdateWidget(QuestionCard old) {
    super.didUpdateWidget(old);
    if (old.questions != widget.questions) {
      picked = [for (final _ in widget.questions) <String>{}];
    }
  }

  void _toggle(int i, String option) {
    final q = widget.questions[i];
    setState(() {
      if (picked[i].contains(option)) {
        picked[i].remove(option);
      } else {
        if (!q.multiple) picked[i].clear();
        picked[i].add(option);
      }
    });
    // Une seule question à choix unique : un toucher suffit.
    if (widget.questions.length == 1 && !q.multiple && other.text.trim().isEmpty) _send();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final any = picked.any((p) => p.isNotEmpty) || other.text.trim().isNotEmpty;
    final single = widget.questions.length == 1 && !widget.questions.first.multiple;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.primary.withValues(alpha: 0.4)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(context.t('ask_title'),
            style: Theme.of(context).textTheme.labelLarge?.copyWith(color: scheme.primary)),
        for (var i = 0; i < widget.questions.length; i++) ...[
          const SizedBox(height: 10),
          Text(widget.questions[i].question, style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 6, children: [
            for (final o in widget.questions[i].options)
              FilterChip(
                label: Text(o),
                selected: picked[i].contains(o),
                onSelected: (_) => _toggle(i, o),
              ),
          ]),
        ],
        const SizedBox(height: 10),
        TextField(
          controller: other,
          minLines: 1,
          maxLines: 3,
          textInputAction: TextInputAction.send,
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => any ? _send() : null,
          decoration: InputDecoration(
            isDense: true,
            hintText: context.t('ask_other'),
            border: const OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(12))),
          ),
        ),
        if (!single || other.text.trim().isNotEmpty) ...[
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(
              onPressed: any ? _send : null,
              child: Text(context.t('ask_send')),
            ),
          ),
        ],
      ]),
    );
  }
}
