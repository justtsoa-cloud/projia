import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:projia/core/chat_controller.dart';
import 'package:projia/ui/question_card.dart';

void main() {
  final qs = AskedQuestion.parse([
    {'question': 'Pour qui ?', 'options': ['Élèves', 'Pro']},
    {'question': 'Longueur ?', 'options': ['Courte', 'Longue'], 'multiple': true},
    {'question': 'Cassée', 'options': ['seule']},
  ]);

  test('les questions mal formées sont ignorées', () {
    expect(qs.map((q) => q.question), ['Pour qui ?', 'Longueur ?']);
    expect(qs[1].multiple, isTrue);
  });

  test('la réponse reprend question → choix, sans les questions ignorées', () {
    final text = QuestionCard.compose(qs, [{'Élèves'}, {'Courte', 'Longue'}]);
    expect(text, 'Pour qui ? → Élèves\nLongueur ? → Courte, Longue');
    expect(QuestionCard.compose(qs, [{}, {'Courte'}]), 'Longueur ? → Courte');
    expect(QuestionCard.compose(qs, [{'Pro'}, {}], ' avec des chiffres '), 'Pour qui ? → Pro\navec des chiffres');
  });

  testWidgets('une seule question à choix unique : un toucher envoie', (tester) async {
    String? sent;
    final one = [AskedQuestion('Format ?', ['PDF', 'Word'], false)];
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: QuestionCard(questions: one, onSend: (t) => sent = t))));
    await tester.tap(find.text('Word'));
    expect(sent, 'Format ? → Word');
  });

  testWidgets('plusieurs questions : choix multiples, précision libre, envoi groupé', (tester) async {
    String? sent;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: QuestionCard(questions: qs, onSend: (t) => sent = t)))));
    final send = find.widgetWithText(FilledButton, 'Envoyer mes choix');
    expect(tester.widget<FilledButton>(send).onPressed, isNull); // rien choisi
    await tester.tap(find.text('Élèves'));
    await tester.tap(find.text('Pro')); // choix unique : remplace « Élèves »
    await tester.tap(find.text('Courte'));
    await tester.tap(find.text('Longue')); // choix multiple : les deux
    await tester.pump();
    expect(sent, isNull); // plusieurs questions : jamais d'envoi au premier toucher
    await tester.enterText(find.byType(TextField), 'avec des exemples');
    await tester.pump();
    await tester.tap(send);
    expect(sent, 'Pour qui ? → Pro\nLongueur ? → Courte, Longue\navec des exemples');
  });
}
