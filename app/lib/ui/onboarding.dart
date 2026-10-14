// Accueil : 3 écrans maximum, passable à tout moment. Aucune configuration obligatoire.

import 'package:flutter/material.dart';

import '../core/updater.dart' show appVersion;
import '../main.dart';

class Onboarding extends StatefulWidget {
  const Onboarding({super.key});

  @override
  State<Onboarding> createState() => _OnboardingState();
}

class _OnboardingState extends State<Onboarding> {
  final controller = PageController();
  int page = 0;

  void _finish() {
    final prefs = AppScope.of(context).prefs;
    prefs.lastSeenVersion = appVersion; // 1re installation : pas de « nouveautés » à afficher
    prefs.onboarded = true;
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      (Icons.auto_awesome, 'onb1_t', 'onb1_b'),
      (Icons.gesture, 'onb2_t', 'onb2_b'),
      (Icons.key_outlined, 'onb3_t', 'onb3_b'),
    ];
    return ListenableBuilder(
      listenable: AppScope.of(context).prefs,
      builder: (context, _) => Scaffold(
      body: SafeArea(
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
            child: Row(children: [
              // Langue : confirmée dès l'accueil (c'est aussi ce qui est compté, de façon anonyme).
              Expanded(
                child: Wrap(spacing: 6, children: [
                  for (final (code, name) in const [('fr', 'Français'), ('en', 'English'), ('mg', 'Malagasy')])
                    ChoiceChip(
                      label: Text(name),
                      selected: AppScope.of(context).prefs.locale == code,
                      onSelected: (_) {
                        final scope = AppScope.of(context);
                        scope.prefs.locale = code;
                        scope.backend.sendJson('PUT', '/tontolo/settings', {'language': code}).catchError((_) => null);
                      },
                    ),
                ]),
              ),
              TextButton(onPressed: _finish, child: Text(context.t('skip'))),
            ]),
          ),
          Expanded(
            child: PageView(
              controller: controller,
              onPageChanged: (i) => setState(() => page = i),
              children: [
                for (final (icon, title, body) in pages)
                  Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      if (icon == Icons.auto_awesome)
                        Image.asset('assets/icon.png', width: 96, height: 96)
                      else
                        Icon(icon, size: 72, color: Theme.of(context).colorScheme.primary),
                      const SizedBox(height: 24),
                      Text(context.t(title), style: Theme.of(context).textTheme.headlineSmall, textAlign: TextAlign.center),
                      const SizedBox(height: 12),
                      Text(context.t(body), textAlign: TextAlign.center),
                    ]),
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(context.t('stats_notice'),
                textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
          ),
          const SizedBox(height: 8),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (var i = 0; i < pages.length; i++)
              AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                margin: const EdgeInsets.all(4),
                width: i == page ? 20 : 8,
                height: 8,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary.withValues(alpha: i == page ? 1 : 0.3),
                  borderRadius: BorderRadius.circular(4)),
              ),
          ]),
          Padding(
            padding: const EdgeInsets.all(24),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: page == pages.length - 1
                    ? _finish
                    : () => controller.nextPage(duration: const Duration(milliseconds: 180), curve: Curves.easeOut),
                child: Text(page == pages.length - 1 ? context.t('start') : context.t('next')),
              ),
            ),
          ),
        ]),
      ),
    ));
  }
}
