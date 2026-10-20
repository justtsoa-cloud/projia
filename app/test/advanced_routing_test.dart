import 'package:flutter_test/flutter_test.dart';
import 'package:projia/ui/advanced_routing.dart';

void main() {
  test('message d\'erreur lisible du cœur', () {
    expect(coreError(Exception('HTTP 400 : {"error": {"message": "HTTPS obligatoire"}}')), 'HTTPS obligatoire');
    expect(coreError(Exception('HTTP 422 : {"detail": "invalide"}')), 'invalide');
    expect(coreError('HttpException: réseau'), 'réseau');
  });
}
