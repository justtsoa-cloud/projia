// Questions à choix posées par Tontolo pour préciser la demande (réponse en un toucher).
import 'package:flutter/material.dart';

import '../core/chat_controller.dart';
import '../main.dart';

class QuestionCard extends StatefulWidget {
  const QuestionCard({super.key, required this.questions, required this.onSend});
  final List<AskedQuestion> questions;
  final void Function(String text) onSend;

  /// Réponse envoyée : une ligne « question → choix » par question répondue.
  static String compose(List<AskedQuestion> qs, List<Set<String>> picked) => [
        for (var i = 0; i < qs.length; i++)
          if (picked[i].isNotEmpty) '${qs[i].question} → ${picked[i].join(', ')}',
      ].join('\n');

  @override
  State<QuestionCard> createState() => _QuestionCardState();
}

class _QuestionCardState extends State<QuestionCard> {
  late List<Set<String>> picked = [for (final _ in widget.questions) <String>{}];

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
    if (widget.questions.length == 1 && !q.multiple) {
      widget.onSend(QuestionCard.compose(widget.questions, picked));
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final any = picked.any((p) => p.isNotEmpty);
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
        if (!single) ...[
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(
              onPressed: any
                  ? () => widget.onSend(QuestionCard.compose(widget.questions, picked))
                  : null,
              child: Text(context.t('ask_send')),
            ),
          ),
        ],
      ]),
    );
  }
}
