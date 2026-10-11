// Export HTML : aucun script ni lien dangereux ne survit.

import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/core/chat_controller.dart';
import 'package:tontolo/core/export_html.dart';

void main() {
  test('HTML brut et liens javascript neutralisés', () {
    final html = safeMarkdown('Salut <script>alert(1)</script> [x](javascript:alert(2)) **gras** [ok](https://a.b)');
    expect(html.contains('<script>'), isFalse);
    expect(html.contains('javascript:'), isFalse);
    expect(html, contains('<strong>gras</strong>'));
    expect(html, contains('href="https://a.b"'));
  });

  test('page complète avec CSP et auteur', () {
    final page = conversationHtml([
      ChatMessage(role: 'user', text: 'Question <b>'),
      ChatMessage(role: 'assistant', text: 'Réponse')..modelName = 'modèle',
    ], title: 'Essai', locale: 'fr');
    expect(page, contains("default-src 'none'"));
    expect(page, contains('RANIRIAMANJAKA Antsa'));
    expect(page.contains('<b>'), isFalse);
  });
}
