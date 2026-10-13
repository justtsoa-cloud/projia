// Avancement d'une réponse : noms courts, pourcentage monotone, journal lisible.
import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/core/turn_progress.dart';
import 'package:tontolo/l10n/strings.dart';

void main() {
  test('noms courts des modèles', () {
    expect(shortModelName('nvidia/nemotron-3-ultra-550b-a55b:free'), 'Nemotron 3 Ultra');
    expect(shortModelName('inclusionai/ling-3.1-flash'), 'Ling 3.1 Flash');
    expect(shortModelName('meta-llama/llama-3.3-70b-instruct:free'), 'Llama 3.3 70B');
    expect(shortModelName('Gemini 2.5 Flash (free)'), 'Gemini 2.5 Flash');
    expect(shortModelName('qwen/qwen3-coder-480b-a35b-instruct'), 'Qwen3 Coder 480B');
    expect(shortModelName('Qwen3.8-27B'), 'Qwen3.8 27B');
    expect(shortModelName(null), '');
  });

  test('pourcentage : monte avec la réponse, jamais en recul, 100 seulement à la fin', () {
    final p = TurnProgress()..start();
    final t0 = DateTime.now();
    final a = p.percent(t0);
    p.onEvent({'type': 'route', 'model': 'groq:llama', 'name': 'Llama 3.3 70B Instruct'});
    p.onEvent({'type': 'delta', 'content': '', 'reasoning': 'Je réfléchis'});
    expect(p.chars, 0); // réflexion : pas encore la réponse
    expect(p.percent(t0.add(const Duration(seconds: 1))), greaterThanOrEqualTo(10));
    expect(p.model, 'Llama 3.3 70B');
    final b = p.percent(t0.add(const Duration(seconds: 10)));
    expect(b, greaterThan(a));
    for (var i = 0; i < 60; i++) {
      p.onEvent({'type': 'delta', 'content': 'x' * 100});
    }
    final c = p.percent(t0.add(const Duration(seconds: 20)));
    expect(c, greaterThan(b));
    expect(p.percent(t0), c); // l'horloge recule : le pourcentage ne baisse pas
    p.onEvent({'type': 'delta', 'content': 'x' * 100000});
    expect(p.percent(t0.add(const Duration(minutes: 30))), lessThanOrEqualTo(97));
    p.finish();
    expect(p.percent(), 100);
  });

  test('création en sections : le pourcentage suit les sections écrites', () {
    final p = TurnProgress()..start();
    final now = DateTime.now();
    p.onEvent({'type': 'step', 'step': 'slides_section', 'n': 1, 'total': 4});
    final one = p.percent(now);
    p.onEvent({'type': 'step', 'step': 'slides_section', 'n': 3, 'total': 4});
    final three = p.percent(now);
    expect(three - one, greaterThan(30));
    p.onEvent({'type': 'step', 'step': 'doc_building'});
    expect(p.percent(now), greaterThanOrEqualTo(84));
    expect(p.log.map((e) => e.status), ['slides_section|1|4', 'slides_section|3|4', 'doc_building']);
  });

  test('plusieurs modèles : parties et modèles journalisés, textes traduits', () {
    final p = TurnProgress()..start();
    p.onEvent({'type': 'orchestration', 'subtasks': [{}, {}, {}]});
    p.onEvent({'type': 'subtask', 'index': 0, 'status': 'running'});
    p.onEvent({'type': 'subtask', 'index': 0, 'status': 'done', 'model': 'g:x', 'name': 'Gemini 2.5 Flash'});
    p.onEvent({'type': 'subtask', 'index': 1, 'status': 'failed', 'model': '', 'name': ''});
    expect(p.partsTotal, 3);
    expect(p.parts[0], ('done', 'Gemini 2.5 Flash'));
    expect(p.log.map((e) => e.status),
        ['orchestrating|3', 'part_running|1', 'part_done|1|Gemini 2.5 Flash', 'part_failed|2|']);
    expect(p.percent(DateTime.now()), greaterThan(50));
    for (final l in ['fr', 'en', 'mg']) {
      for (final k in ['role_writing', 'first_token', 'log_route', 'part_done', 'parts_progress', 'progress_details']) {
        expect(tr(l, k), isNot(k), reason: '$k manquant en $l');
      }
    }
  });
}
