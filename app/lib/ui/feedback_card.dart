// Carte de retour d'expérience (accueil) et note de l'application (À propos).
// Rare, discrète, jamais pendant une tâche ; tout reste sur l'appareil sauf si la personne coche
// « Envoyer à l'auteur » pour CE retour.

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/feedback.dart';
import '../core/prefs.dart';
import '../main.dart';

const _repoUrl = 'https://github.com/justtsoa-cloud/projia';

class FeedbackCard extends StatefulWidget {
  const FeedbackCard({super.key, required this.prefs, required this.onClose});
  final Prefs prefs;
  final VoidCallback onClose;

  @override
  State<FeedbackCard> createState() => _FeedbackCardState();
}

class _FeedbackCardState extends State<FeedbackCard> {
  int _mood = 0; // 0 = question, 1 = bof, 2 = bien, 3 = très bien
  final _why = <String>{};
  final _note = TextEditingController();
  bool _send = false; // jamais coché d'office
  bool _thanks = false;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _finish() async {
    final entry = AppFeedback.payload(
        mood: _mood, why: _why.toList(), note: _note.text.trim(), locale: widget.prefs.locale);
    AppFeedback.keep(widget.prefs, entry);
    if (_send) await AppFeedback.send(entry);
    if (mounted) setState(() => _thanks = true);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    Widget body;
    if (_thanks) {
      body = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(context.t('fb_thanks'), style: text.titleMedium),
        if (_mood >= 2) ...[
          const SizedBox(height: 6),
          Text(context.t('fb_share_help'), style: text.bodySmall),
          Wrap(spacing: 8, children: [
            ActionChip(
              avatar: const Icon(Icons.star_outline, size: 18),
              label: Text(context.t('fb_star')),
              onPressed: () => launchUrl(Uri.parse(_repoUrl), mode: LaunchMode.externalApplication),
            ),
          ]),
        ],
        Align(alignment: Alignment.centerRight, child: TextButton(onPressed: widget.onClose, child: Text(context.t('got_it')))),
      ]);
    } else if (_mood == 0) {
      body = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(context.t('fb_question'), style: text.titleMedium),
        const SizedBox(height: 8),
        Row(mainAxisAlignment: MainAxisAlignment.spaceEvenly, children: [
          for (final (mood, face, label) in [(1, '🙁', 'fb_bad'), (2, '🙂', 'fb_ok'), (3, '😍', 'fb_great')])
            Column(children: [
              IconButton(
                iconSize: 34,
                tooltip: context.t(label),
                onPressed: () {
                  setState(() => _mood = mood);
                  if (mood >= 2) _finish();
                },
                icon: Text(face, style: const TextStyle(fontSize: 30)),
              ),
              Text(context.t(label), style: text.labelSmall),
            ]),
        ]),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            onPressed: () {
              AppFeedback.dismiss(widget.prefs);
              widget.onClose();
            },
            child: Text(context.t('fb_later')),
          ),
        ),
      ]);
    } else {
      body = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(context.t('fb_why'), style: text.titleMedium),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 4, children: [
          for (final r in AppFeedback.reasons)
            FilterChip(
              label: Text(context.t('fb_r_$r')),
              selected: _why.contains(r),
              onSelected: (on) => setState(() => on ? _why.add(r) : _why.remove(r)),
            ),
        ]),
        TextField(
          controller: _note,
          maxLength: 280,
          maxLines: 2,
          decoration: InputDecoration(hintText: context.t('fb_note')),
        ),
        CheckboxListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          value: _send,
          onChanged: (v) => setState(() => _send = v ?? false),
          title: Text(context.t('fb_send')),
          subtitle: Text(context.t('fb_send_help')),
          controlAffinity: ListTileControlAffinity.leading,
        ),
        Align(alignment: Alignment.centerRight, child: FilledButton(onPressed: _finish, child: Text(context.t('fb_done')))),
      ]);
    }
    return Material(
      color: scheme.surfaceContainerHigh,
      borderRadius: BorderRadius.circular(20),
      child: Padding(padding: const EdgeInsets.fromLTRB(16, 14, 12, 8), child: body),
    );
  }
}

/// Note de l'application (1 à 5), donnée quand on veut ; gardée sur l'appareil.
class AppRatingTile extends StatefulWidget {
  const AppRatingTile({super.key, required this.prefs});
  final Prefs prefs;

  @override
  State<AppRatingTile> createState() => _AppRatingTileState();
}

class _AppRatingTileState extends State<AppRatingTile> {
  bool _sent = false;

  @override
  Widget build(BuildContext context) {
    final rating = widget.prefs.appRating;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ListTile(title: Text(context.t('rate_app')), subtitle: Text(context.t('rate_app_help'))),
      Row(children: [
        const SizedBox(width: 8),
        for (var i = 1; i <= 5; i++)
          IconButton(
            tooltip: '$i',
            icon: Icon(i <= rating ? Icons.star : Icons.star_border),
            onPressed: () => setState(() {
              widget.prefs.appRating = i;
              _sent = false;
            }),
          ),
        if (rating > 0)
          TextButton(
            onPressed: _sent
                ? null
                : () async {
                    final ok = await AppFeedback.send(AppFeedback.payload(
                        mood: rating >= 4 ? 3 : (rating == 3 ? 2 : 1), rating: rating, locale: widget.prefs.locale));
                    if (mounted) setState(() => _sent = ok);
                  },
            child: Text(context.t(_sent ? 'fb_sent' : 'fb_send_rating')),
          ),
      ]),
    ]);
  }
}
