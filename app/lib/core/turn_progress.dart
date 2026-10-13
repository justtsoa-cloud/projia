// Avancement d'une réponse en cours : pourcentage estimé, modèle(s) en action et journal
// court de ce qui se passe derrière (affiché en une ligne, détaillé au toucher).

import 'dart:math' as math;

/// Ligne du journal : instant (depuis le début du tour) et état au format des statuts
/// (`doc_writing`, `tool|web_search`, `part_done|2|Llama 3.3`…), traduit à l'affichage.
class ProgressEntry {
  ProgressEntry(this.at, this.status);
  final Duration at;
  final String status;
}

/// Nom court d'un modèle : « nvidia/nemotron-3-ultra-550b-a55b:free » → « Nemotron 3 Ultra ».
String shortModelName(String? name) {
  if (name == null || name.trim().isEmpty) return '';
  var s = name.trim();
  if (s.contains('/')) s = s.split('/').last;
  s = s.split(':').first;
  s = s.replaceAll(RegExp(r'\((free|gratuit)\)', caseSensitive: false), '');
  const drop = {'instruct', 'chat', 'it', 'preview', 'latest', 'versatile', 'free', 'hf', 'exp',
      'experimental', 'turbo', 'online', 'fp8', 'awq', 'gguf'};
  final words = <String>[];
  for (final w in s.split(RegExp(r'[\s_\-]+'))) {
    final low = w.toLowerCase();
    if (w.isEmpty || drop.contains(low)) continue;
    if (RegExp(r'^a\d+b$').hasMatch(low) || RegExp(r'^\d{4,8}$').hasMatch(low)) continue;
    if (RegExp(r'^\d+(\.\d+)?[bmk]$').hasMatch(low)) {
      words.add(low.toUpperCase());
    } else if (w == low && RegExp(r'^[a-z]').hasMatch(w)) {
      words.add(w[0].toUpperCase() + w.substring(1));
    } else {
      words.add(w);
    }
  }
  // Trois mots suffisent ; la taille (70B…) ne passe qu'en troisième position.
  final kept = <String>[];
  for (final w in words) {
    if (kept.length >= 3) break;
    if (RegExp(r'^\d+(\.\d+)?[BMK]$').hasMatch(w) && kept.isEmpty) continue;
    kept.add(w);
  }
  final out = kept.join(' ');
  return out.length > 24 ? '${out.substring(0, 23)}…' : out;
}

class TurnProgress {
  DateTime _start = DateTime.now();
  double _pct = 0;
  bool active = false;
  String? model; // nom court du modèle qui écrit
  int chars = 0;
  bool reasoning = false;
  String? _phase; // dernier statut d'étape reçu
  DateTime _phaseAt = DateTime.now();
  int _n = 0, _total = 0;
  final Map<int, (String, String)> parts = {}; // partie → (état, modèle)
  int partsTotal = 0;
  final List<ProgressEntry> log = [];

  Duration get elapsed => DateTime.now().difference(_start);

  void start() {
    _start = DateTime.now();
    _pct = 0;
    active = true;
    model = null;
    chars = 0;
    reasoning = false;
    _phase = null;
    _n = _total = 0;
    parts.clear();
    partsTotal = 0;
    log.clear();
  }

  void finish() {
    active = false;
    _pct = 100;
  }

  void _note(String status) {
    if (log.isNotEmpty && log.last.status == status) return;
    log.add(ProgressEntry(elapsed, status));
    if (log.length > 80) log.removeAt(0);
  }

  void _setPhase(String phase) {
    if (_phase != phase) _phaseAt = DateTime.now();
    _phase = phase;
  }

  /// Met à jour l'état à partir d'un événement du flux du cœur.
  void onEvent(Map<String, dynamic> ev, {String Function(Map<String, dynamic>)? reason}) {
    switch (ev['type']) {
      case 'route':
        model = shortModelName((ev['name'] ?? ev['model']) as String?);
        _note('log_route|$model');
      case 'model_switched':
        model = shortModelName((ev['to_name'] ?? ev['to']) as String?);
        _note('log_switched|$model');
      case 'delta':
        // Les morceaux de réflexion portent souvent un `content` vide : ce n'est pas encore
        // la réponse.
        final content = (ev['content'] as String?) ?? '';
        final thought = (ev['reasoning'] ?? ev['reasoning_content']) as String? ?? '';
        if (content.isNotEmpty) {
          if (chars == 0) _note('first_token');
          chars += content.length;
          _setPhase('writing');
        } else if (thought.isNotEmpty) {
          if (!reasoning) _note('thinking');
          reasoning = true;
          _setPhase('thinking');
        }
      case 'step':
        final step = '${ev['step']}';
        if (step == 'doc_done') return;
        _n = (ev['n'] as num?)?.toInt() ?? 0;
        _total = (ev['total'] as num?)?.toInt() ?? 0;
        _setPhase(step);
        _note(_total > 0 ? '$step|$_n|$_total' : (step == 'synthesizing' ? '$step|${ev['n'] ?? partsTotal}' : step));
      case 'orchestration':
        partsTotal = (ev['subtasks'] as List?)?.length ?? 2;
        _setPhase('orchestrating');
        _note('orchestrating|$partsTotal');
      case 'subtask':
        final i = (ev['index'] as num).toInt();
        final name = shortModelName((ev['name'] ?? ev['model']) as String?);
        parts[i] = ('${ev['status']}', name);
        _note(ev['status'] == 'running' ? 'part_running|${i + 1}' : 'part_${ev['status']}|${i + 1}|$name');
      case 'plan_step':
        final i = (ev['i'] as num).toInt();
        parts[i] = ('${ev['status']}', shortModelName(ev['model'] as String?));
        _setPhase('plan_running');
        _note(ev['status'] == 'running' ? 'part_running|${i + 1}' : 'part_${ev['status']}|${i + 1}|${parts[i]!.$2}');
      case 'plan':
        partsTotal = ((ev['plan'] as Map?)?['steps'] as List?)?.length ?? partsTotal;
      case 'tool_call':
        _note('tool|${ev['name']}');
      case 'web_search':
        _note('searching_web');
      case 'waiting':
        _note('waiting|${ev['seconds']}');
      case 'job':
        _setPhase('generating');
        _note('generating');
      case 'review':
        _note('log_reviewed|${shortModelName(ev['name'] as String?)}');
      case 'continuing':
        _note('continuing');
    }
  }

  /// Pourcentage estimé (0–100) : jamais en recul, jamais 100 avant la fin.
  double percent([DateTime? now]) {
    if (!active) return _pct;
    final t = (now ?? DateTime.now()).difference(_start).inMilliseconds / 1000;
    final since = (now ?? DateTime.now()).difference(_phaseAt).inMilliseconds / 1000;
    double creep(double from, double to, double seconds, double tau) =>
        from + (to - from) * (1 - math.exp(-seconds / tau));
    var p = creep(2, 20, t, 25); // en attente du premier mot
    if (chars > 0) p = math.max(p, creep(22, 92, chars.toDouble(), 1800));
    if (reasoning && chars == 0) p = math.max(p, creep(10, 30, since, 40));
    final done = parts.values.where((s) => s.$1 == 'done' || s.$1 == 'failed').length;
    if (partsTotal > 0) p = math.max(p, 8 + 72 * done / partsTotal + creep(0, 70 / partsTotal, since, 30));
    switch (_phase) {
      case 'planning' || 'book_outline' || 'slides_outline' || 'doc_reading':
        p = math.max(p, creep(5, 15, since, 30));
      case 'doc_writing':
        p = math.max(p, creep(15, 75, since, 60));
      case 'book_chapter' || 'slides_section' when _total > 0:
        p = math.max(p, 12 + 70 * _n / _total + creep(0, 70 / _total, since, 60));
      case 'doc_building':
        p = math.max(p, creep(84, 90, since, 30));
      case 'doc_reviewing':
        p = math.max(p, creep(88, 93, since, 30));
      case 'doc_fixing':
        p = math.max(p, creep(90, 95, since, 40));
      case 'answer_reviewing':
        p = math.max(p, creep(93, 97, since, 20));
      case 'synthesizing':
        p = math.max(p, creep(85, 95, since, 25));
      case 'generating':
        p = math.max(p, creep(10, 90, since, 45));
    }
    _pct = math.max(_pct, math.min(p, 97));
    return _pct;
  }
}
