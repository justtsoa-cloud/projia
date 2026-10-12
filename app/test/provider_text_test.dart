import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/core/provider_text.dart';

void main() {
  test('nom et description dans la langue de l\'app, français sinon', () {
    final p = {
      'name': 'Ollama (sur l\'appareil)', 'description': 'Sans Internet.',
      'i18n': {'mg': {'name': 'Ollama (amin\'ity fitaovana ity)', 'description': 'Tsy misy Internet.'},
               'en': {'description': 'Without Internet.'}},
    };
    expect(providerText(p, 'mg', 'name'), 'Ollama (amin\'ity fitaovana ity)');
    expect(providerText(p, 'en', 'name'), 'Ollama (sur l\'appareil)'); // pas de traduction du nom
    expect(providerText(p, 'en', 'description'), 'Without Internet.');
    expect(providerText(p, 'fr', 'description'), 'Sans Internet.');
    expect(providerText({'name': 'X'}, 'mg', 'description'), '');
  });
}
