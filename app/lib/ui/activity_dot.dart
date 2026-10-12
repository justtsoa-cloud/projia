// Pastille d'activité d'une discussion : trois états distincts, jamais ambigus.
//  - orange « ? » : attend votre réponse ;
//  - vert qui tourne : en cours sur CET appareil ;
//  - bleu « appareils » : en cours sur un AUTRE appareil.

import 'package:flutter/material.dart';

import '../core/activity.dart';
import '../main.dart';

Color dotColor(BuildContext context, Dot? dot) => switch (dot) {
      Dot.waiting => const Color(0xFFE59A1F),
      Dot.local => const Color(0xFF2E9E6B),
      Dot.remote => Theme.of(context).colorScheme.tertiary,
      null => Colors.transparent,
    };

class ActivityDot extends StatelessWidget {
  const ActivityDot(this.dot, {super.key});
  final Dot dot;

  @override
  Widget build(BuildContext context) {
    final color = dotColor(context, dot);
    final Widget icon = switch (dot) {
      Dot.waiting => Icon(Icons.help, size: 18, color: color),
      Dot.local => SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2.2, color: color)),
      Dot.remote => Icon(Icons.devices_other, size: 18, color: color),
    };
    return Tooltip(
      message: context.t('dot_${dot.name}'),
      child: Semantics(label: context.t('dot_${dot.name}'), child: icon),
    );
  }
}
