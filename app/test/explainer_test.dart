// Lecteur de vidéo explicative : lecture du bloc, toutes les scènes, commandes, export.
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:projia/l10n/strings.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:projia/core/account.dart';
import 'package:projia/core/activity.dart';
import 'package:projia/core/backend.dart';
import 'package:projia/core/chat_controller.dart';
import 'package:projia/core/cloud_sync.dart';
import 'package:projia/core/prefs.dart';
import 'package:projia/core/updater.dart';
import 'package:projia/main.dart';
import 'package:projia/ui/explainer_player.dart';
import 'package:projia/ui/learn.dart';

final _story = {
  'title': 'Additionner des fractions',
  'seconds': 30,
  'scenes': [
    {'type': 'title', 'text': 'Additionner des fractions', 'subtitle': 'Collège', 'narration': 'Bonjour.', 'seconds': 4},
    {'type': 'bullets', 'title': 'L\'idée', 'items': ['Même dénominateur', 'On additionne'], 'narration': 'Même dénominateur.', 'seconds': 5},
    {'type': 'equation', 'latex': '\\frac{1}{2}+\\frac{1}{3}=\\frac{5}{6}', 'caption': 'Résultat', 'narration': 'Cinq sixièmes.', 'seconds': 5},
    {
      'type': 'steps',
      'title': 'Exemple',
      'steps': [
        {'text': 'On cherche 6', 'latex': '\\frac{1}{2}=\\frac{3}{6}'},
        {'text': 'On additionne', 'latex': '\\frac{3}{6}+\\frac{2}{6}=\\frac{5}{6}'},
      ],
      'narration': 'Exemple.',
      'seconds': 6,
    },
    {
      'type': 'plot',
      'title': 'Courbe',
      'caption': 'Le carré',
      'points': [for (var i = 0; i <= 20; i++) [i / 2 - 5, (i / 2 - 5) * (i / 2 - 5)]],
      'narration': 'La courbe.',
      'seconds': 5,
    },
    {'type': 'bars', 'title': 'Parts', 'labels': ['1/2', '1/3', '5/6'], 'values': [0.5, 0.33, 0.83], 'narration': 'Comparons.', 'seconds': 4},
    {'type': 'recap', 'title': 'À retenir', 'items': ['a', 'b', 'c'], 'narration': 'Fin.', 'seconds': 4},
  ],
};

class _Core extends Backend {
  _Core(super.prefs, {this.mp4 = false}) {
    state = BackendState.ready;
  }
  final bool mp4;
  @override
  Future<dynamic> getJson(String path, [Map<String, dynamic>? query]) async => {'mp4': mp4};
}

void main() {
  final block = '```explainer\n${jsonEncode(_story)}\n```';

  test('le bloc explainer est reconnu dans une réponse, un bloc cassé reste du texte', () {
    final segs = splitLearnBlocks('Voici une vidéo.\n\n$block');
    expect(segs.whereType<ExplainerSegment>(), hasLength(1));
    expect(segs.whereType<ExplainerSegment>().single.story.scenes, hasLength(7));
    final broken = splitLearnBlocks('```explainer\n{"title": "x", "scenes": []}\n```');
    expect(broken.whereType<ExplainerSegment>(), isEmpty);
    final streaming = splitLearnBlocks('Voici.\n```explainer\n{"title": "x", "sce');
    expect(streaming.whereType<PendingSegment>().single.kind, 'explainer'); // réponse en cours
    expect(ExplainerStory.parse('pas du json'), isNull);
  });

  Future<_Core> open(WidgetTester tester, {bool mp4 = false}) async {
    SharedPreferences.setMockInitialValues({'locale': 'fr'});
    final prefs = await Prefs.load();
    final core = _Core(prefs, mp4: mp4);
    final chat = ChatController(core);
    final cloud = CloudSync(core, Account());
    tester.view.physicalSize = const Size(1080, 1800);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(AppScope(
      prefs: prefs,
      backend: core,
      updater: Updater(prefs),
      chat: chat,
      account: Account(),
      cloud: cloud,
      activity: ActivityWatcher(core, cloud, chat),
      child: MaterialApp(home: Scaffold(body: SingleChildScrollView(child: ExplainerPlayer(story: ExplainerStory.parse(jsonEncode(_story))!)))),
    ));
    await tester.pump(const Duration(milliseconds: 50));
    return core;
  }

  testWidgets('le lecteur joue les sept scènes sans erreur, avance, et s\'arrête à la fin', (tester) async {
    await open(tester);
    expect(find.text('1/7 · Additionner des fractions'), findsOneWidget);
    expect(find.byIcon(Icons.movie_outlined), findsNothing); // pas de Manim : pas d'export MP4
    await tester.tap(find.byIcon(Icons.volume_up)); // sans voix : aucun moteur dans le banc de test
    await tester.pump();
    await tester.tap(find.byIcon(Icons.play_circle));
    await tester.pump();
    for (var i = 0; i < 7; i++) {
      await tester.pump(const Duration(seconds: 7)); // chaque scène dure au plus 6 s
      expect(tester.takeException(), isNull, reason: 'scène ${i + 1}');
    }
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('7/7 · Additionner des fractions'), findsOneWidget);
    expect(find.byIcon(Icons.pause_circle), findsNothing); // terminé : de nouveau « lancer »
  });

  testWidgets('scène suivante et précédente, sans lecture', (tester) async {
    await open(tester);
    await tester.tap(find.byIcon(Icons.skip_next));
    await tester.pump();
    expect(find.text('2/7 · Additionner des fractions'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.skip_next));
    await tester.tap(find.byIcon(Icons.skip_next));
    await tester.tap(find.byIcon(Icons.skip_next)); // scène « courbe »
    await tester.pump();
    expect(tester.takeException(), isNull);
    await tester.tap(find.byIcon(Icons.skip_previous));
    await tester.pump();
    expect(find.text('4/7 · Additionner des fractions'), findsOneWidget);
  });

  testWidgets('l\'export MP4 n\'apparaît que si le cœur sait le faire', (tester) async {
    await open(tester, mp4: true);
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byIcon(Icons.movie_outlined), findsOneWidget);
  });

  test('boutons « plus court » / « plus détaillée » : textes dans les trois langues', () {
    for (final k in ['la_vshort', 'la_vshort_p', 'la_vlong', 'la_vlong_p']) {
      for (final l in ['fr', 'en', 'mg']) {
        expect(tr(l, k), isNot(k), reason: '$l/$k');
      }
    }
  });
}
