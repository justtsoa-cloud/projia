// Tests de l'interface : rendu Markdown/LaTeX, bandeaux, comparaison de versions.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tontolo/core/updater.dart';
import 'package:tontolo/l10n/strings.dart';
import 'package:tontolo/ui/message_view.dart';

void main() {
  test('comparaison de versions', () {
    expect(Updater.isNewer('0.2.0', '0.1.0'), isTrue);
    expect(Updater.isNewer('0.10.0', '0.9.9'), isTrue);
    expect(Updater.isNewer('0.1.0', '0.1.0'), isFalse);
  });

  test('traductions avec repli sur le français', () {
    expect(tr('fr', 'chat'), 'Chat');
    expect(tr('mg', 'chat'), 'Resaka');
    expect(tr('mg', 'paid_confirm', {'model': 'X', 'cost': '1'}), contains('X'));
    expect(tr('en', 'switched', {'to': 'A', 'reason': 'quota'}), 'Switched to A (quota)');
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
