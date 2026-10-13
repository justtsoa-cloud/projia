// Tests de l'interface : rendu Markdown/LaTeX, bandeaux, comparaison de versions.

import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/core/image_prep.dart';
import 'package:tontolo/core/speech.dart';
import 'package:tontolo/core/updater.dart';
import 'package:tontolo/l10n/strings.dart';
import 'package:tontolo/ui/message_view.dart';

void main() {
  notesTests();
  imageTests();
  test('comparaison de versions', () {
    expect(Updater.isNewer('0.2.0', '0.1.0'), isTrue);
    expect(Updater.isNewer('0.10.0', '0.9.9'), isTrue);
    expect(Updater.isNewer('0.1.0', '0.1.0'), isFalse);
  });

  test('lecture vocale : texte nettoyé du Markdown et du LaTeX', () {
    final t = Speech.plainText('# Titre\n\n**gras** [lien](https://x.y) \$\$x^2\$\$ ```code```');
    expect(t, isNot(contains('#')));
    expect(t, contains('lien'));
    expect(t, contains('(formule)'));
    expect(t, contains('(bloc de code)'));
  });

  test('traductions avec repli sur le français', () {
    expect(tr('fr', 'chat'), 'Chat');
    expect(tr('mg', 'chat'), 'Resaka');
    expect(tr('mg', 'paid_confirm', {'model': 'X', 'cost': '1'}), contains('X'));
    expect(tr('en', 'switched', {'to': 'A', 'reason': 'quota'}), 'Switched to A (quota)');
  });

  test('formule en ligne plausible ou non', () {
    expect(plausibleInlineTex('f(x) = x^2'), isTrue);
    expect(plausibleInlineTex(r'\frac{a}{b}'), isTrue);
    expect(plausibleInlineTex('a**. Géométriquement, '), isFalse); // « \$ » oublié par le modèle
    expect(plausibleInlineTex('a. Ensuite on pose b'), isFalse);
  });

  testWidgets('un « \$ » oublié ne mélange pas les formules', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: RichMarkdown(
        r'Si \$f\$ est **dérivable** en \$a**. Géométriquement, \$f(a)\$ est la pente en \$a\$.',
      ))),
    ));
    await tester.pump();
    expect(tester.takeException(), isNull);
    // « Géométriquement » reste du texte lisible (pas avalé dans une formule).
    expect(find.textContaining('Géométriquement', findRichText: true), findsOneWidget);
  });

  testWidgets('formule dans une phrase : la phrase reste un seul bloc de texte', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: RichMarkdown(
        'La formule \$\$a^2 + b^2 = c^2\$\$, puis le triplet \$3^2+4^2=5^2\$ suit.\n\n\$\$\\frac{a}{b}\$\$',
      ))),
    ));
    await tester.pump();
    expect(tester.takeException(), isNull);
    // Texte avant et après les formules dans le même paragraphe (plus de retour à la ligne).
    final para = find.byWidgetPredicate((w) => w is SelectableText &&
        (w.textSpan?.toPlainText(includePlaceholders: false) ?? '').contains('La formule') &&
        w.textSpan!.toPlainText(includePlaceholders: false).contains(', puis le triplet'));
    expect(para, findsOneWidget);
    // « \$\$…\$\$ » seul dans son paragraphe : formule centrée, défilable.
    expect(find.byType(SingleChildScrollView), findsNWidgets(2));
  });

  testWidgets('formules dans un tableau : aucune erreur de rendu', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: RichMarkdown(
        '| Fonction | Dérivée |\n|---|---|\n| \$x^2\$ | \$2x\$ |\n| \$\\frac{a}{b}\$ | \$\\sqrt{x}\$ |\n\nTexte \$a^2+b^2=c^2\$.',
      ))),
    ));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byType(RichMarkdown), findsOneWidget);
  });

  testWidgets('Markdown, code et LaTeX', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: RichMarkdown(
        '# Titre\n\nTexte **gras** et \$x^2\$.\n\n\$\$\n\\frac{a}{b}\n\$\$\n\n```python\nprint(1)\n```',
      ))),
    ));
    expect(find.text('Titre'), findsOneWidget);
    expect(find.text('print(1)'), findsOneWidget);
    expect(find.byIcon(Icons.copy), findsOneWidget);
  });
}

void notesTests() {
  test('notes de version : rubriques, sans tableau des tailles', () {
    const body = '''
### Ajouté
- **Mémoire** locale avec `compactage`
  automatique.
- Raccourcis « / ».

### Corrigé
- Lecture vocale arrêtable.

### Taille des fichiers
| Fichier | Taille |
- ceci ne doit pas apparaître
''';
    final notes = Updater.parseNotes(body);
    expect(notes.map((n) => n.$1), ['Ajouté', 'Corrigé']);
    expect(notes.first.$2.first, 'Mémoire locale avec compactage automatique.');
    expect(notes.first.$2.length, 2);
    expect(notes.expand((n) => n.$2), isNot(contains('ceci ne doit pas apparaître')));
  });
}

void imageTests() {
  testWidgets('photo réduite avant envoi', (tester) async {
    await tester.runAsync(() async {
      // Image de 2000×1000 px générée en mémoire.
      final rec = ui.PictureRecorder();
      ui.Canvas(rec).drawRect(const ui.Rect.fromLTWH(0, 0, 2000, 1000), ui.Paint()..color = const Color(0xFF3EB489));
      final img = await rec.endRecording().toImage(2000, 1000);
      final png = (await img.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
      final (out, mime) = await prepareImage(png);
      final d = await ui.ImageDescriptor.encoded(await ui.ImmutableBuffer.fromUint8List(out));
      expect(mime, 'image/png');
      expect(d.width, maxImageSide);
      expect(d.height, 512);
      // Une petite image reste intacte.
      final small = (await (await (ui.PictureRecorder()..let((r) => ui.Canvas(r).drawRect(const ui.Rect.fromLTWH(0, 0, 64, 64), ui.Paint())))
          .endRecording().toImage(64, 64)).toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
      expect((await prepareImage(small)).$1.length, small.length);
    });
  });
}

extension _Let<T> on T {
  T let(void Function(T) f) {
    f(this);
    return this;
  }
}
