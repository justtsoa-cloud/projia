// Accueil d'une nouvelle discussion, vivant mais sobre : salutation selon l'heure et le prénom
// (« Bonsoir » + prénom de l'utilisateur) qui s'écrit lettre par lettre, logo qui respire, et suggestions qui
// changent (heure, jour, mode, sujets récents), apparues en cascade et renouvelées en fondu.
// Tout s'arrête si « Réduire les animations » est activé.

import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/backend.dart';
import '../core/chat_controller.dart';
import '../main.dart';
import 'theme.dart';

class Suggestion {
  const Suggestion(this.icon, this.key, {this.photo = false, this.send = true});
  final IconData icon;
  final String key; // texte : context.t(key)
  final bool photo; // demande une photo d'abord
  final bool send; // envoyée telle quelle (sinon pré-remplie pour être complétée)
}

const _always = [
  Suggestion(Icons.brush_outlined, 'hs_image'),
  Suggestion(Icons.movie_outlined, 'hs_video'),
  Suggestion(Icons.translate, 'hs_translate', send: false),
  Suggestion(Icons.picture_as_pdf_outlined, 'hs_pdf', send: false),
  Suggestion(Icons.account_tree_outlined, 'hs_mindmap', send: false),
  Suggestion(Icons.auto_fix_high_outlined, 'hs_retouch', photo: true, send: false),
  Suggestion(Icons.travel_explore, 'hs_news'),
  Suggestion(Icons.lightbulb_outline, 'hs_explain', send: false),
];
const _morning = [
  Suggestion(Icons.today_outlined, 'hs_plan_day', send: false),
  Suggestion(Icons.newspaper_outlined, 'hs_morning_news'),
  Suggestion(Icons.free_breakfast_outlined, 'hs_breakfast'),
];
const _afternoon = [
  Suggestion(Icons.mail_outline, 'hs_email', send: false),
  Suggestion(Icons.summarize_outlined, 'hs_summary', send: false),
  Suggestion(Icons.psychology_outlined, 'hs_brainstorm', send: false),
];
const _evening = [
  Suggestion(Icons.restaurant_outlined, 'hs_dinner'),
  Suggestion(Icons.auto_stories_outlined, 'hs_story'),
  Suggestion(Icons.event_note_outlined, 'hs_tomorrow', send: false),
];
const _night = [
  Suggestion(Icons.bedtime_outlined, 'hs_sleep'),
  Suggestion(Icons.quiz_outlined, 'hs_quiz_night'),
];
const _weekend = [
  Suggestion(Icons.park_outlined, 'hs_outing'),
  Suggestion(Icons.handyman_outlined, 'hs_diy', send: false),
];
const _agent = [
  Suggestion(Icons.compare_arrows, 'hs_agent_compare', send: false),
  Suggestion(Icons.query_stats, 'hs_agent_analyze', send: false),
  Suggestion(Icons.code, 'hs_agent_script', send: false),
  Suggestion(Icons.description_outlined, 'hs_agent_report', send: false),
];

/// Salutation selon l'heure : matin, après-midi, soir, nuit.
String greetingKey(DateTime now) => switch (now.hour) {
      >= 5 && < 12 => 'greet_morning',
      >= 12 && < 18 => 'greet_afternoon',
      >= 18 && < 23 => 'greet_evening',
      _ => 'greet_night',
    };

/// Réserve de suggestions pour ce moment (heure, jour, mode), mélangée de façon stable
/// pendant la vie de l'écran.
List<Suggestion> suggestionPool(DateTime now, {required bool agent, Random? random}) {
  final pool = <Suggestion>[
    if (agent) ..._agent,
    ...switch (greetingKey(now)) {
      'greet_morning' => _morning,
      'greet_afternoon' => _afternoon,
      'greet_evening' => _evening,
      _ => _night,
    },
    if (now.weekday >= DateTime.saturday) ..._weekend,
    ..._always,
  ];
  return pool..shuffle(random ?? Random());
}

class HomeView extends StatefulWidget {
  const HomeView({super.key, required this.chat, required this.onSend, required this.onPrefill});
  final ChatController chat;
  final ValueChanged<String> onSend;
  final void Function(String text, {bool photo}) onPrefill;

  @override
  State<HomeView> createState() => _HomeViewState();
}

class _HomeViewState extends State<HomeView> with TickerProviderStateMixin {
  late final AnimationController _typing;
  late final AnimationController _breath;
  late final AnimationController _cascade;
  Timer? _rotate;
  String _name = '';
  List<Map<String, dynamic>> _recent = [];
  List<Map<String, dynamic>> _tracks = []; // « piste du jour » : calculée sur l'appareil
  late List<Suggestion> _pool;
  final List<Object> _shown = []; // Suggestion ou sujet récent (Map)
  int _next = 0;
  int _subtitle = Random().nextInt(4);
  bool _still = false;
  bool _loaded = false;
  Backend? _backend;

  @override
  void initState() {
    super.initState();
    _typing = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
    _breath = AnimationController(vsync: this, duration: const Duration(seconds: 3));
    _cascade = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));
    _pool = suggestionPool(DateTime.now(), agent: widget.chat.agent != null);
    _fill();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final still = AppScope.of(context).prefs.reduceMotion;
    if (still != _still || (!_typing.isAnimating && _typing.value == 0)) {
      _still = still;
      _start();
    }
    // Démarrage à froid : le cœur n'est pas encore prêt ; on charge dès qu'il l'est.
    _backend ??= AppScope.of(context).backend..addListener(_onBackend);
    if (!_loaded) _load();
  }

  void _onBackend() {
    if (!_loaded && _backend?.state == BackendState.ready) _load();
  }

  void _start() {
    _rotate?.cancel();
    if (_still) {
      _typing.value = 1;
      _cascade.value = 1;
      _breath.stop();
      return;
    }
    _typing.forward(from: 0);
    _cascade.forward(from: 0);
    _breath.repeat(reverse: true);
    // Une suggestion change toutes les 7 s ; la phrase d'invitation aussi, plus lentement.
    _rotate = Timer.periodic(const Duration(seconds: 7), (t) {
      if (!mounted || _shown.isEmpty) return;
      setState(() {
        final i = Random().nextInt(_shown.length);
        if (_shown[i] is Suggestion) _shown[i] = _take();
        if (t.tick % 2 == 0) _subtitle = (_subtitle + 1) % 4;
      });
    });
  }

  /// Phrase d'invitation : quatre générales, plus une propre au soir (« Hariva indray… »).
  String _subtitleKey() {
    final evening = const {'greet_evening', 'greet_night'}.contains(greetingKey(DateTime.now()));
    return evening && _subtitle == 3 ? 'greet_sub_evening' : 'greet_sub$_subtitle';
  }

  Suggestion _take() {
    for (var k = 0; k < _pool.length; k++) {
      final s = _pool[_next++ % _pool.length];
      if (!_shown.contains(s)) return s;
    }
    return _pool[_next++ % _pool.length];
  }

  /// Quatre suggestions : la discussion la plus récente à reprendre (s'il y en a une), puis
  /// des idées pour ce moment.
  void _fill() {
    _shown
      ..clear()
      ..addAll(_recent.take(1));
    while (_shown.length < 4) {
      _shown.add(_take());
    }
  }

  Future<void> _load() async {
    final scope = AppScope.of(context);
    final account = scope.account.session?.firstName ?? '';
    if (account.isNotEmpty && _name.isEmpty) setState(() => _name = account);
    if (scope.backend.state != BackendState.ready) return;
    try {
      final home = await scope.backend.getJson('/tontolo/home') as Map<String, dynamic>;
      // Ordre : prénom du réglage, puis du compte, puis appris dans la mémoire.
      final fromSettings = home['name_from'] == 'settings' ? '${home['name']}' : '';
      final name = fromSettings.isNotEmpty ? fromSettings.split(' ').first : (account.isNotEmpty ? account : '${home['name'] ?? ''}');
      if (!mounted) return;
      _loaded = true;
      setState(() {
        _name = name;
        _recent = ((home['recent'] as List?) ?? const []).cast<Map<String, dynamic>>();
        _tracks = ((home['tracks'] as List?) ?? const []).cast<Map<String, dynamic>>();
        _fill();
      });
      if (!_still) _typing.forward(from: 0);
    } catch (_) {
      // Ancien cœur ou cœur indisponible : nouvel essai au prochain changement d'état.
    }
  }

  @override
  void dispose() {
    _backend?.removeListener(_onBackend);
    _rotate?.cancel();
    _typing.dispose();
    _breath.dispose();
    _cascade.dispose();
    super.dispose();
  }

  /// « Pas pour moi » : ce thème n'est plus proposé pendant deux semaines.
  Future<void> _dismissTrack(Map<String, dynamic> t) async {
    HapticFeedback.selectionClick();
    final topic = '${t['topic']}';
    setState(() => _tracks.removeWhere((x) => x['topic'] == topic));
    try {
      await AppScope.of(context).backend.sendJson('POST', '/tontolo/home/dismiss', {'topic': topic});
    } catch (_) {} // ancien cœur : le thème reviendra, sans conséquence
  }

  void _pickTrack(Map<String, dynamic> t) {
    HapticFeedback.selectionClick();
    widget.onSend('${t['prompt']}');
  }

  void _pick(Object item) {
    HapticFeedback.selectionClick();
    if (item is Map<String, dynamic>) {
      widget.chat.open('${item['id']}');
      return;
    }
    final s = item as Suggestion;
    final text = context.t(s.key);
    if (s.send && !s.photo) {
      widget.onSend(text);
    } else {
      widget.onPrefill(text, photo: s.photo);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final hello = context.t(greetingKey(DateTime.now()));
    final greeting = context.t(_name.isEmpty ? 'greet_alone' : 'greet_name', {'g': hello, 'n': _name});
    final wide = MediaQuery.sizeOf(context).width >= 600;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            AnimatedBuilder(
              animation: _breath,
              builder: (context, child) => Transform.scale(
                scale: 1 + 0.05 * Curves.easeInOut.transform(_breath.value),
                child: child,
              ),
              child: Image.asset('assets/icon.png', width: 64, height: 64),
            ),
            const SizedBox(height: 16),
            AnimatedBuilder(
              animation: _typing,
              builder: (context, _) {
                final n = (greeting.length * _typing.value).round().clamp(0, greeting.length);
                return Text.rich(
                  TextSpan(children: [
                    TextSpan(text: greeting.substring(0, n)),
                    // Le reste, invisible : la ligne ne saute pas pendant l'écriture.
                    TextSpan(text: greeting.substring(n), style: const TextStyle(color: Colors.transparent)),
                  ]),
                  textAlign: TextAlign.center,
                  style: text.headlineMedium?.copyWith(fontWeight: FontWeight.w600),
                );
              },
            ),
            const SizedBox(height: 6),
            AnimatedSwitcher(
              duration: context.motion * 3,
              child: Text(context.t(_subtitleKey()),
                  key: ValueKey(_subtitle),
                  textAlign: TextAlign.center,
                  style: text.titleMedium?.copyWith(color: scheme.onSurfaceVariant)),
            ),
            if (_tracks.isNotEmpty) ...[
              const SizedBox(height: 20),
              _TrackCard(
                track: _tracks.first,
                others: _tracks.skip(1).toList(),
                onTap: _pickTrack,
                onDismiss: _dismissTrack,
              ),
            ],
            const SizedBox(height: 24),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: 10,
              runSpacing: 10,
              children: [
                for (final (i, item) in _shown.indexed)
                  _Cascade(
                    controller: _cascade,
                    index: i,
                    child: SizedBox(
                      width: wide ? 330 : double.infinity,
                      child: AnimatedSwitcher(
                        duration: context.motion * 3,
                        child: _SuggestionCard(
                          key: ValueKey(item is Suggestion ? item.key : 'recent-${(item as Map)['id']}'),
                          item: item,
                          onTap: () => _pick(item),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ]),
        ),
      ),
    );
  }
}

/// Apparition en cascade (fondu + léger glissement), décalée selon la position.
class _Cascade extends StatelessWidget {
  const _Cascade({required this.controller, required this.index, required this.child});
  final AnimationController controller;
  final int index;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final start = (0.12 * index).clamp(0.0, 0.6);
    final anim = CurvedAnimation(parent: controller, curve: Interval(start, (start + 0.5).clamp(0.0, 1.0), curve: Curves.easeOutCubic));
    return FadeTransition(
      opacity: anim,
      child: SlideTransition(
        position: Tween(begin: const Offset(0, 0.25), end: Offset.zero).animate(anim),
        child: child,
      ),
    );
  }
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard({super.key, required this.item, required this.onTap});
  final Object item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final recent = item is Map;
    final label = recent ? context.t('hs_resume', {'t': '${(item as Map)['title']}'}) : context.t((item as Suggestion).key);
    final icon = recent ? Icons.history : (item as Suggestion).icon;
    return Material(
      color: recent ? scheme.secondaryContainer.withValues(alpha: 0.6) : scheme.surfaceContainerHigh,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(children: [
            Icon(icon, size: 20, color: scheme.primary),
            const SizedBox(width: 12),
            Expanded(child: Text(label, maxLines: 2, overflow: TextOverflow.ellipsis)),
            Icon(Icons.north_east, size: 16, color: scheme.onSurfaceVariant),
          ]),
        ),
      ),
    );
  }
}


/// La piste du jour : une invitation précise tirée des centres d'intérêt de la personne, avec deux
/// variantes plus discrètes et « Pas pour moi » pour écarter le thème.
class _TrackCard extends StatelessWidget {
  const _TrackCard({required this.track, required this.others, required this.onTap, required this.onDismiss});
  final Map<String, dynamic> track;
  final List<Map<String, dynamic>> others;
  final void Function(Map<String, dynamic>) onTap;
  final void Function(Map<String, dynamic>) onDismiss;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Material(
      color: scheme.primaryContainer.withValues(alpha: 0.55),
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: () => onTap(track),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 14, 8, 10),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Icon(Icons.auto_awesome, size: 16, color: scheme.primary),
              const SizedBox(width: 6),
              Expanded(child: Text(context.t('track_for_you'), style: text.labelMedium?.copyWith(color: scheme.primary))),
              TextButton(
                onPressed: () => onDismiss(track),
                style: TextButton.styleFrom(visualDensity: VisualDensity.compact),
                child: Text(context.t('track_not_me')),
              ),
            ]),
            Padding(
              padding: const EdgeInsets.only(right: 8, bottom: 4),
              child: Text('${track['title']}', style: text.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
            ),
            if (others.isNotEmpty)
              Wrap(spacing: 8, runSpacing: 4, children: [
                for (final o in others)
                  ActionChip(
                    label: Text('${o['title']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                    onPressed: () => onTap(o),
                  ),
              ]),
          ]),
        ),
      ),
    );
  }
}
