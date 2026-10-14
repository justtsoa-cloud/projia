// Lecteur de vidéo explicative : le scénario (données validées par le cœur) joué par
// l'application : scènes animées, formules, courbes, narration à voix haute. Marche partout
// (Android, Linux), hors ligne ; le MP4 par Manim est un export facultatif (Linux).

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:http/http.dart' as http;
import 'package:share_plus/share_plus.dart';

import '../core/speech.dart';
import '../main.dart';

const _bg = Color(0xFF0F0E2A);
const _fg = Color(0xFFF7F7FB);
const _accent = Color(0xFF67E5BE);
const _soft = Color(0xFFB9C4DF);
const _violet = Color(0xFF8A7DFF);

class ExplainerScene {
  ExplainerScene(this.type, this.data)
      : seconds = ((data['seconds'] as num?)?.toDouble() ?? 6).clamp(3, 20).toDouble();
  final String type;
  final Map<String, dynamic> data;
  final double seconds;

  String text(String key) => '${data[key] ?? ''}';
  List<String> items(String key) => [for (final i in (data[key] as List? ?? const [])) '$i'];
  String get narration => text('narration');
}

class ExplainerStory {
  ExplainerStory(this.title, this.scenes, this.json);
  final String title;
  final List<ExplainerScene> scenes;
  final Map<String, dynamic> json; // tel que reçu : renvoyé tel quel pour l'export MP4

  double get seconds => scenes.fold(0.0, (a, s) => a + s.seconds);

  /// Scénario lisible, ou null s'il est illisible (le bloc reste alors affiché en texte).
  static ExplainerStory? parse(String body) {
    try {
      final data = jsonDecode(body.trim());
      if (data is! Map<String, dynamic>) return null;
      final scenes = <ExplainerScene>[
        for (final s in (data['scenes'] as List).take(12))
          if (s is Map<String, dynamic> && s['type'] != null) ExplainerScene('${s['type']}', s),
      ];
      if (scenes.length < 3) return null;
      return ExplainerStory('${data['title'] ?? ''}', scenes, data);
    } catch (_) {
      return null;
    }
  }
}

class ExplainerPlayer extends StatefulWidget {
  const ExplainerPlayer({super.key, required this.story});
  final ExplainerStory story;

  @override
  State<ExplainerPlayer> createState() => _ExplainerPlayerState();
}

class _ExplainerPlayerState extends State<ExplainerPlayer> with SingleTickerProviderStateMixin {
  late final AnimationController _ctl = AnimationController(vsync: this);
  int index = 0;
  bool playing = false;
  bool voice = true;
  bool exporting = false;
  bool? mp4; // le cœur sait-il faire un MP4 (Manim) ? null = pas encore su

  ExplainerScene get scene => widget.story.scenes[index];

  @override
  void initState() {
    super.initState();
    _ctl.addStatusListener((s) {
      if (s == AnimationStatus.completed && playing) _sceneEnded();
    });
    _ctl.addListener(() => mounted ? setState(() {}) : null);
    WidgetsBinding.instance.addPostFrameCallback((_) => _capabilities());
  }

  @override
  void dispose() {
    Speech.instance.stop().catchError((Object _) {});
    _ctl.dispose();
    super.dispose();
  }

  Future<void> _capabilities() async {
    try {
      final r = await AppScope.of(context).backend.getJson('/tontolo/explainer/capabilities') as Map;
      if (mounted) setState(() => mp4 = r['mp4'] == true);
    } catch (_) {
      if (mounted) setState(() => mp4 = false);
    }
  }

  void _start(int i) {
    index = i.clamp(0, widget.story.scenes.length - 1);
    _ctl.duration = Duration(milliseconds: (scene.seconds * 1000).round());
    _ctl.forward(from: 0);
    if (voice && scene.narration.isNotEmpty) {
      final prefs = AppScope.of(context).prefs;
      // Pas de voix installée (ou pas de moteur) : la vidéo se lit quand même, sous-titrée.
      Speech.instance.toggle('explainer', scene.narration, locale: prefs.locale, rate: prefs.speechRate).catchError((Object _) {});
    }
    setState(() {});
  }

  /// Fin de l'animation : on attend la fin de la voix (4 s au plus) avant la scène suivante.
  Future<void> _sceneEnded() async {
    final speech = Speech.instance;
    if (voice && speech.isSpeaking('explainer')) {
      final done = Completer<void>();
      void check() {
        if (!speech.isSpeaking('explainer') && !done.isCompleted) done.complete();
      }

      speech.addListener(check);
      await done.future.timeout(const Duration(seconds: 4), onTimeout: () {});
      speech.removeListener(check);
    }
    if (!mounted || !playing) return;
    if (index + 1 < widget.story.scenes.length) {
      _start(index + 1);
    } else {
      setState(() => playing = false);
    }
  }

  void _toggle() {
    HapticFeedback.selectionClick();
    if (playing) {
      _ctl.stop();
      Speech.instance.stop().catchError((Object _) {});
      setState(() => playing = false);
    } else {
      playing = true;
      _start(_ctl.isCompleted && index == widget.story.scenes.length - 1 ? 0 : index);
    }
  }

  void _go(int i) {
    Speech.instance.stop().catchError((Object _) {});
    if (playing) {
      _start(i);
    } else {
      setState(() {
        index = i.clamp(0, widget.story.scenes.length - 1);
        _ctl.value = 1;
      });
    }
  }

  Future<void> _export() async {
    final scope = AppScope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final waiting = context.t('explainer_rendering');
    final failed = context.t('explainer_export_failed');
    setState(() => exporting = true);
    messenger.showSnackBar(SnackBar(content: Text(waiting), duration: const Duration(seconds: 3)));
    try {
      final b = scope.backend;
      final r = await http
          .post(b.uri('/tontolo/explainer/render'),
              headers: {...b.headers, 'Content-Type': 'application/json'},
              body: jsonEncode({'story': widget.story.json, 'quality': 'l'}))
          .timeout(const Duration(minutes: 6));
      if (r.statusCode != 200) throw StateError('${r.statusCode}');
      await SharePlus.instance.share(ShareParams(files: [
        XFile.fromData(r.bodyBytes, mimeType: 'video/mp4', name: 'explication.mp4'),
      ]));
    } catch (_) {
      messenger.showSnackBar(SnackBar(content: Text(failed)));
    } finally {
      if (mounted) setState(() => exporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final story = widget.story;
    final scheme = Theme.of(context).colorScheme;
    final total = story.seconds;
    final before = story.scenes.take(index).fold(0.0, (a, s) => a + s.seconds);
    final progress = ((before + scene.seconds * _ctl.value) / total).clamp(0.0, 1.0);
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 6),
      clipBehavior: Clip.antiAlias,
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        GestureDetector(
          onTap: _toggle,
          child: AspectRatio(
            aspectRatio: 16 / 9,
            child: Container(
              color: _bg,
              child: Stack(fit: StackFit.expand, children: [
                LayoutBuilder(
                  builder: (context, box) => _SceneView(scene: scene, t: _ctl.value, scale: box.maxWidth / 640),
                ),
                if (!playing)
                  const Center(child: Icon(Icons.play_circle_fill, size: 56, color: Color(0xCCF7F7FB))),
                if (scene.narration.isNotEmpty)
                  Positioned(
                    left: 8, right: 8, bottom: 6,
                    child: Text(scene.narration,
                        textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: _soft, fontSize: 11, height: 1.2)),
                  ),
              ]),
            ),
          ),
        ),
        LinearProgressIndicator(value: progress, minHeight: 3, color: _accent, backgroundColor: scheme.surfaceContainerHighest),
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 2, 4, 2),
          child: Row(children: [
            IconButton(
              tooltip: context.t('explainer_prev'),
              icon: const Icon(Icons.skip_previous),
              onPressed: index > 0 ? () => _go(index - 1) : null,
            ),
            IconButton(
              tooltip: context.t(playing ? 'explainer_pause' : 'explainer_play'),
              icon: Icon(playing ? Icons.pause_circle : Icons.play_circle, size: 30),
              onPressed: _toggle,
            ),
            IconButton(
              tooltip: context.t('explainer_next'),
              icon: const Icon(Icons.skip_next),
              onPressed: index + 1 < story.scenes.length ? () => _go(index + 1) : null,
            ),
            Expanded(
              child: Text('${index + 1}/${story.scenes.length} · ${story.title}',
                  maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodySmall),
            ),
            IconButton(
              tooltip: context.t(voice ? 'explainer_voice_off' : 'explainer_voice_on'),
              icon: Icon(voice ? Icons.volume_up : Icons.volume_off),
              onPressed: () {
                setState(() => voice = !voice);
                if (!voice) Speech.instance.stop().catchError((Object _) {});
              },
            ),
            if (mp4 == true)
              exporting
                  ? const Padding(padding: EdgeInsets.all(12), child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)))
                  : IconButton(tooltip: context.t('explainer_export'), icon: const Icon(Icons.movie_outlined), onPressed: _export),
          ]),
        ),
      ]),
    );
  }
}

// --- Scènes ------------------------------------------------------------------------------

double _ease(double t, double from, double to) => Curves.easeOut.transform(((t - from) / (to - from)).clamp(0.0, 1.0));

class _SceneView extends StatelessWidget {
  const _SceneView({required this.scene, required this.t, required this.scale});
  final ExplainerScene scene;
  final double t; // 0 → 1 sur la durée de la scène
  final double scale;

  TextStyle _style(double size, Color color, {FontWeight weight = FontWeight.w500}) =>
      TextStyle(color: color, fontSize: size * scale, fontWeight: weight, height: 1.25);

  Widget _head() => Padding(
        padding: EdgeInsets.only(top: 14 * scale),
        child: Opacity(
          opacity: _ease(t, 0, 0.1),
          child: Text(scene.text('title'), textAlign: TextAlign.center, style: _style(22, _accent, weight: FontWeight.w700)),
        ),
      );

  Widget _math(String tex, double size) => Math.tex(
        tex,
        textStyle: TextStyle(color: _fg, fontSize: size * scale),
        onErrorFallback: (e) => Text(tex, style: _style(size * 0.7, _fg)),
      );

  @override
  Widget build(BuildContext context) {
    switch (scene.type) {
      case 'title':
        return Center(
          child: Opacity(
            opacity: _ease(t, 0, 0.2),
            child: Transform.scale(
              scale: 0.9 + 0.1 * _ease(t, 0, 0.25),
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: 24 * scale),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(scene.text('text'), textAlign: TextAlign.center, style: _style(34, _fg, weight: FontWeight.w700)),
                  if (scene.text('subtitle').isNotEmpty) ...[
                    SizedBox(height: 10 * scale),
                    Opacity(opacity: _ease(t, 0.15, 0.35), child: Text(scene.text('subtitle'), textAlign: TextAlign.center, style: _style(16, _accent))),
                  ],
                ]),
              ),
            ),
          ),
        );
      case 'bullets':
      case 'recap':
        final items = scene.items('items');
        return Column(children: [
          _head(),
          SizedBox(height: 10 * scale),
          Expanded(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 28 * scale),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                for (var i = 0; i < items.length; i++)
                  Opacity(
                    opacity: _ease(t, 0.1 + 0.55 * i / items.length, 0.2 + 0.55 * i / items.length + 0.1),
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: 5 * scale),
                      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Icon(scene.type == 'recap' ? Icons.check_circle : Icons.circle, size: (scene.type == 'recap' ? 17 : 8) * scale, color: _accent),
                        SizedBox(width: 10 * scale),
                        Expanded(child: Text(items[i], style: _style(17, _fg))),
                      ]),
                    ),
                  ),
              ]),
            ),
          ),
          SizedBox(height: 22 * scale),
        ]);
      case 'equation':
        return Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Opacity(opacity: _ease(t, 0, 0.3), child: _math(scene.text('latex'), 30)),
            if (scene.text('caption').isNotEmpty) ...[
              SizedBox(height: 14 * scale),
              Opacity(opacity: _ease(t, 0.3, 0.5), child: Text(scene.text('caption'), textAlign: TextAlign.center, style: _style(16, _accent))),
            ],
          ]),
        );
      case 'steps':
        final steps = [for (final s in (scene.data['steps'] as List? ?? const [])) if (s is Map) s];
        return Column(children: [
          _head(),
          Expanded(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 24 * scale),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                for (var i = 0; i < steps.length; i++)
                  Opacity(
                    opacity: _ease(t, 0.08 + 0.6 * i / steps.length, 0.2 + 0.6 * i / steps.length),
                    child: Padding(
                      padding: EdgeInsets.symmetric(vertical: 3 * scale),
                      child: Column(children: [
                        if ('${steps[i]['text'] ?? ''}'.isNotEmpty) Text('${steps[i]['text']}', textAlign: TextAlign.center, style: _style(13, _soft)),
                        if ('${steps[i]['latex'] ?? ''}'.isNotEmpty) _math('${steps[i]['latex']}', 19),
                      ]),
                    ),
                  ),
              ]),
            ),
          ),
          SizedBox(height: 22 * scale),
        ]);
      case 'plot':
        final pts = [
          for (final p in (scene.data['points'] as List? ?? const []))
            if (p is List && p.length == 2) Offset((p[0] as num).toDouble(), (p[1] as num).toDouble()),
        ];
        return Column(children: [
          _head(),
          Expanded(
            child: Padding(
              padding: EdgeInsets.fromLTRB(36 * scale, 8 * scale, 36 * scale, 4 * scale),
              child: CustomPaint(painter: _PlotPainter(pts, _ease(t, 0.12, 0.75)), size: Size.infinite),
            ),
          ),
          if (scene.text('caption').isNotEmpty)
            Opacity(opacity: _ease(t, 0.7, 0.85), child: Text(scene.text('caption'), style: _style(14, _fg))),
          SizedBox(height: 22 * scale),
        ]);
      case 'bars':
        final labels = scene.items('labels');
        final values = [for (final v in (scene.data['values'] as List? ?? const [])) (v as num).toDouble()];
        return Column(children: [
          _head(),
          Expanded(
            child: Padding(
              padding: EdgeInsets.fromLTRB(40 * scale, 8 * scale, 40 * scale, 4 * scale),
              child: CustomPaint(
                painter: _BarsPainter(labels, values, _ease(t, 0.1, 0.7), _style(13, _soft)),
                size: Size.infinite,
              ),
            ),
          ),
          SizedBox(height: 22 * scale),
        ]);
    }
    return const SizedBox.shrink();
  }
}

class _PlotPainter extends CustomPainter {
  _PlotPainter(this.pts, this.progress);
  final List<Offset> pts;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    if (pts.length < 2) return;
    final minX = pts.map((p) => p.dx).reduce(math.min), maxX = pts.map((p) => p.dx).reduce(math.max);
    var minY = pts.map((p) => p.dy).reduce(math.min), maxY = pts.map((p) => p.dy).reduce(math.max);
    if (maxY - minY < 1e-6) {
      minY -= 1;
      maxY += 1;
    }
    final pad = (maxY - minY) * 0.12;
    minY -= pad;
    maxY += pad;
    Offset map(Offset p) => Offset(
          (p.dx - minX) / (maxX - minX) * size.width,
          size.height - (p.dy - minY) / (maxY - minY) * size.height,
        );
    final axis = Paint()..color = _soft..strokeWidth = 1.2;
    final x0 = (0 - minX) / (maxX - minX) * size.width;
    final y0 = size.height - (0 - minY) / (maxY - minY) * size.height;
    canvas.drawLine(Offset(0, y0.clamp(0, size.height)), Offset(size.width, y0.clamp(0, size.height)), axis);
    canvas.drawLine(Offset(x0.clamp(0, size.width), 0), Offset(x0.clamp(0, size.width), size.height), axis);
    final path = Path();
    final upto = (pts.length * progress).ceil().clamp(2, pts.length);
    for (var i = 0; i < upto; i++) {
      final q = map(pts[i]);
      i == 0 ? path.moveTo(q.dx, q.dy) : path.lineTo(q.dx, q.dy);
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = _accent
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3
        ..strokeJoin = StrokeJoin.round,
    );
  }

  @override
  bool shouldRepaint(_PlotPainter old) => old.progress != progress || old.pts != pts;
}

class _BarsPainter extends CustomPainter {
  _BarsPainter(this.labels, this.values, this.progress, this.labelStyle);
  final List<String> labels;
  final List<double> values;
  final double progress;
  final TextStyle labelStyle;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    final top = values.map((v) => v.abs()).reduce(math.max).clamp(1e-9, double.infinity);
    final n = values.length;
    final slot = size.width / n;
    const colors = [_accent, _violet, Color(0xFF33D6E8)];
    final baseline = size.height - 22;
    for (var i = 0; i < n; i++) {
      final h = (values[i] / top).clamp(0, 1) * (baseline - 8) * progress;
      final rect = Rect.fromLTWH(i * slot + slot * 0.2, baseline - h, slot * 0.6, h);
      canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(4)), Paint()..color = colors[i % colors.length]);
      final label = TextPainter(
        text: TextSpan(text: i < labels.length ? labels[i] : '', style: labelStyle),
        textDirection: TextDirection.ltr,
        maxLines: 1,
      )..layout(maxWidth: slot);
      label.paint(canvas, Offset(i * slot + (slot - label.width) / 2, baseline + 4));
    }
    canvas.drawLine(Offset(0, baseline), Offset(size.width, baseline), Paint()..color = _soft..strokeWidth = 1.2);
  }

  @override
  bool shouldRepaint(_BarsPainter old) => old.progress != progress;
}
