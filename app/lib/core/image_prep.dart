// Préparation des photos jointes : réduction avant envoi (côté long ≤ 1024 px).
// Les photos de téléphone font plusieurs Mo : trop lourdes pour les IA de vision gratuites
// et pour la base locale. Aucune dépendance native : décodage et encodage par Flutter.

import 'dart:typed_data';
import 'dart:ui' as ui;

const maxImageSide = 1024;
const _keepAsIsBytes = 1500000;

/// Renvoie (octets, type MIME). En cas d'échec de décodage, l'image d'origine est conservée.
Future<(Uint8List, String)> prepareImage(Uint8List bytes) async {
  try {
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    final desc = await ui.ImageDescriptor.encoded(buffer);
    final w = desc.width, h = desc.height;
    if (w <= maxImageSide && h <= maxImageSide && bytes.length <= _keepAsIsBytes) {
      desc.dispose();
      buffer.dispose();
      return (bytes, guessMime(bytes));
    }
    final landscape = w >= h;
    final codec = await desc.instantiateCodec(
      targetWidth: landscape ? (w > maxImageSide ? maxImageSide : w) : null,
      targetHeight: landscape ? null : (h > maxImageSide ? maxImageSide : h),
    );
    final frame = await codec.getNextFrame();
    final data = await frame.image.toByteData(format: ui.ImageByteFormat.png);
    frame.image.dispose();
    codec.dispose();
    desc.dispose();
    buffer.dispose();
    if (data == null) return (bytes, guessMime(bytes));
    return (data.buffer.asUint8List(), 'image/png');
  } catch (_) {
    return (bytes, guessMime(bytes));
  }
}

String guessMime(Uint8List b) {
  if (b.length > 3 && b[0] == 0x89 && b[1] == 0x50) return 'image/png';
  if (b.length > 3 && b[0] == 0xFF && b[1] == 0xD8) return 'image/jpeg';
  if (b.length > 12 && b[0] == 0x52 && b[1] == 0x49 && b[8] == 0x57) return 'image/webp';
  return 'image/jpeg';
}
