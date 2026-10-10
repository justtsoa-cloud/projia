// Thème Material You : bleu indigo + vert menthe + blanc cassé, clair et sombre.
// Contrastes vérifiés WCAG AA pour le texte principal.

import 'package:flutter/material.dart';

const indigo = Color(0xFF3F51B5);
const mint = Color(0xFF3EB489);
const offWhite = Color(0xFFFAF9F6);

ThemeData buildTheme(Brightness brightness, {bool reduceMotion = false}) {
  final scheme = ColorScheme.fromSeed(
    seedColor: indigo,
    secondary: mint,
    brightness: brightness,
    surface: brightness == Brightness.light ? offWhite : null,
  );
  final duration = reduceMotion ? Duration.zero : const Duration(milliseconds: 180);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    visualDensity: VisualDensity.standard,
    materialTapTargetSize: MaterialTapTargetSize.padded, // cibles ≥ 48 dp
    pageTransitionsTheme: PageTransitionsTheme(builders: {
      for (final p in TargetPlatform.values)
        p: reduceMotion ? const _NoTransition() : const FadeForwardsPageTransitionsBuilder(),
    }),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(24), borderSide: BorderSide.none),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
    ),
    chipTheme: ChipThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
    extensions: [MotionPrefs(duration)],
  );
}

class MotionPrefs extends ThemeExtension<MotionPrefs> {
  const MotionPrefs(this.duration);
  final Duration duration;
  @override
  MotionPrefs copyWith({Duration? duration}) => MotionPrefs(duration ?? this.duration);
  @override
  MotionPrefs lerp(MotionPrefs? other, double t) => other ?? this;
}

class _NoTransition extends PageTransitionsBuilder {
  const _NoTransition();
  @override
  Widget buildTransitions<T>(PageRoute<T> route, BuildContext context, Animation<double> animation,
          Animation<double> secondaryAnimation, Widget child) =>
      child;
}

extension MotionX on BuildContext {
  Duration get motion => Theme.of(this).extension<MotionPrefs>()?.duration ?? const Duration(milliseconds: 180);
}
