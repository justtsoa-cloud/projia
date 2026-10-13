import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/chat_controller.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/core/stats.dart';
import 'package:tontolo/ui/message_view.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('notes en attente : remplacées, annulées, jamais de texte ni d\'identifiant invalide', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await Prefs.load();
    final id = 'a' * 32;
    Stats.queueRating(prefs, answerId: id, model: 'groq:llama', category: 'code', rating: 1);
    Stats.queueRating(prefs, answerId: id, model: 'groq:llama', category: 'code', rating: -1, reason: 'too_long');
    var list = Stats.pendingRatings(prefs);
    expect(list, hasLength(1));
    expect(list.single['rating'], -1);
    expect(list.single.keys.toSet(), {'answer_id', 'model', 'category', 'rating', 'reason', 'cached'});
    Stats.queueRating(prefs, answerId: id, model: 'groq:llama', category: 'code', rating: 0);
    expect(Stats.pendingRatings(prefs), isEmpty);
    Stats.queueRating(prefs, answerId: '../x', model: 'm', category: 'chat', rating: 1);
    expect(Stats.pendingRatings(prefs), isEmpty);
    // Déjà partagée : la base n'accepte qu'une note par réponse, l'avis reste local.
    prefs.sentRatings = [id];
    Stats.queueRating(prefs, answerId: id, model: 'groq:llama', category: 'code', rating: 1);
    list = Stats.pendingRatings(prefs);
    expect(list, isEmpty);
  });

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
