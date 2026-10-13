// Mode Apprendre : découpage des blocs interactifs et quiz jouable.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/ui/learn.dart';

const _quiz = '''Voici un quiz :
```quiz
{"title": "Fractions", "questions": [
 {"q": "1/2 + 1/2 = ?", "choices": ["1", "2"], "answer": 0, "explain": "Deux demis font un."},
 {"q": "Bad", "choices": ["x"], "answer": 3}
]}
```
Bon courage !''';

void main() {
  test('blocs quiz et fiches reconnus, texte autour conservé', () {
    final s = splitLearnBlocks(_quiz);
    expect(s.length, 3);
    expect((s[0] as MarkdownSegment).text, contains('Voici'));
    final q = s[1] as QuizSegment;
    expect(q.title, 'Fractions');
    expect(q.questions.length, 1); // question invalide ignorée
    expect((s[2] as MarkdownSegment).text, contains('courage'));
    final cards = splitLearnBlocks('```flashcards\n[{"front":"H2O","back":"eau"}]\n```');
    expect((cards.single as CardsSegment).cards.single, ('H2O', 'eau'));
  });

  test('bloc illisible affiché tel quel, bloc en cours = en préparation', () {
    expect(splitLearnBlocks('```quiz\n{pas du json}\n```').single, isA<MarkdownSegment>());
    final live = splitLearnBlocks('Un instant\n```quiz\n{"title": "F');
    expect(live.last, isA<PendingSegment>());
    expect(splitLearnBlocks('rien de spécial').single, isA<MarkdownSegment>());
  });

  testWidgets('quiz jouable : réponse, explication, score', (tester) async {
    final quiz = splitLearnBlocks(_quiz)[1] as QuizSegment;
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(child: QuizCard(quiz: quiz)))));
    await tester.tap(find.text('1').first);
    await tester.pumpAndSettle();
    expect(find.text('Deux demis font un.'), findsOneWidget);
    await tester.tap(find.byType(FilledButton));
    await tester.pumpAndSettle();
    expect(find.text('1 / 1'), findsOneWidget);
  });

  testWidgets('fiches : retourner, « Je savais » / « À revoir », revoir les difficiles', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: SingleChildScrollView(
        child: FlashcardsDeck(cards: [('Capitale du Japon ?', 'Tokyo'), ('7 × 8 ?', '56')])))));
    expect(find.text('1/2'), findsOneWidget);
    expect(find.text('Tokyo'), findsNothing);
    await tester.tap(find.text('Capitale du Japon ?'));
    await tester.pumpAndSettle();
    expect(find.text('Tokyo'), findsOneWidget);
    await tester.tap(find.text('Je savais'));
    await tester.pumpAndSettle();
    expect(find.text('À revoir'), findsNothing); // boutons après avoir retourné la carte
    await tester.tap(find.text('7 × 8 ?'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('À revoir'));
    await tester.pumpAndSettle();
    expect(find.text('1 sur 2 sues'), findsOneWidget);
    await tester.tap(find.text('Revoir les 1 difficiles'));
    await tester.pumpAndSettle();
    expect(find.text('1/1'), findsOneWidget);
    expect(find.text('7 × 8 ?'), findsOneWidget);
  });
}
