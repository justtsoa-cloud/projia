import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/core/stats.dart';

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
}
