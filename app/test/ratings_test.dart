import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:projia/core/chat_controller.dart';
import 'package:projia/ui/message_view.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('pouces sous une réponse : 👍, re-toucher annule, 👎 ; rien sous un message de l\'utilisateur', (tester) async {
    final notes = <int>[];
    // Sans texte : pas de bouton de lecture à voix haute (il demande AppScope).
    final answer = ChatMessage(role: 'assistant', model: 'groq:llama')..modelName = 'Llama';
    Future<void> show(ChatMessage m) => tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(
        child: MessageView(message: m, onRate: (r) {
          notes.add(r);
          m.rating = r;
        })))));
    await show(answer);
    await tester.tap(find.byIcon(Icons.thumb_up_outlined));
    await show(answer);
    expect(find.byIcon(Icons.thumb_up), findsOneWidget); // note visible
    await tester.tap(find.byIcon(Icons.thumb_up));
    await show(answer);
    await tester.tap(find.byIcon(Icons.thumb_down_outlined));
    expect(notes, [1, 0, -1]);
    await show(ChatMessage(role: 'user', text: 'Question'));
    expect(find.byIcon(Icons.thumb_up_outlined), findsNothing);
  });
}
