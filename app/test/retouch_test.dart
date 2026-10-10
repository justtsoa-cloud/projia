// Retouche locale : analyse des consignes et corrections d'image.

import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:tontolo/core/retouch.dart';

void main() {
  group('analyse de la consigne', () {
    test('consigne exacte signalée : professionnel sans changer la personne → retouche locale', () {
      final i = analyzeEdit("edite cette photo de façon très professionnel sans changer la personne ni la composition de l'image");
      expect(i.mode, EditMode.local);
      expect(i.preservesSubject, isTrue);
      expect(i.contentChange, isFalse);
      expect(i.plan.autoLevels, isTrue);
      expect(i.plan.steps.first, contains('professionnel'));
    });

    test('simple « édite cette photo » → amélioration automatique fidèle', () {
      final i = analyzeEdit('Edite cette photo');
      expect(i.mode, EditMode.local);
      expect(i.plan.steps.single, contains('automatique'));
    });

    test('filtres usuels', () {
      expect(analyzeEdit('mets-la en noir et blanc').plan.grayscale, isTrue);
      expect(analyzeEdit('effet sépia').plan.sepia, isTrue);
      expect(analyzeEdit('plus lumineuse et plus de contraste').plan.contrast, greaterThan(1.1));
      expect(analyzeEdit('rendu vintage argentique').plan.grain, greaterThan(0));
      expect(analyzeEdit('tons chauds').plan.warmth, greaterThan(0));
    });

    test('transformations de contenu → créatif (jamais en local)', () {
      for (final t in [
        'remplace le fond par une plage',
        'transforme-la en dessin animé',
        'supprime la personne à gauche',
        'en style de Pixar',
        'ajoute un chapeau',
      ]) {
        expect(analyzeEdit(t).mode, EditMode.creative, reason: t);
      }
    });

    test('consigne créative vague → créatif ; mais « sans changer la personne » → local', () {
      expect(analyzeEdit('edite cette photo de façon très créative').mode, EditMode.creative);
      expect(analyzeEdit('sois créatif sans changer la personne').mode, EditMode.local);
    });

    test('changement de contenu + interdiction de changer la personne est détecté', () {
      final i = analyzeEdit('remplace le décor sans changer la personne');
      expect(i.mode, EditMode.creative);
      expect(i.preservesSubject, isTrue);
      expect(i.contentChange, isTrue);
    });
  });

  group('corrections d\'image', () {
    img.Image sample() {
      final im = img.Image(width: 64, height: 48, numChannels: 4);
      for (var y = 0; y < 48; y++) {
        for (var x = 0; x < 64; x++) {
          im.setPixelRgba(x, y, 60 + x, 80 + y, 120, 255);
        }
      }
      return im;
    }

    test('noir et blanc : R = G = B', () {
      final out = applyPlan(sample(), analyzeEdit('noir et blanc').plan);
      final p = out.getPixel(10, 10);
      expect(p.r, p.g);
      expect(p.g, p.b);
    });

    test('la composition est préservée : mêmes dimensions, structure conservée', () {
      final src = sample();
      final out = applyPlan(src, analyzeEdit('style professionnel').plan);
      expect(out.width, src.width);
      expect(out.height, src.height);
      // Le dégradé reste croissant de gauche à droite : rien n'a été recomposé.
      expect(out.getPixel(60, 20).r, greaterThan(out.getPixel(4, 20).r));
    });

    test('éclaircir augmente la luminosité moyenne', () {
      double mean(img.Image im) {
        var s = 0.0;
        for (final p in im) {
          s += p.luminance;
        }
        return s / (im.width * im.height);
      }

      final src = sample();
      expect(mean(applyPlan(src, analyzeEdit('éclaircis').plan)), greaterThan(mean(src)));
    });

    test('retouchPhoto renvoie un JPEG décodable de même taille', () async {
      final png = img.encodePng(sample());
      final out = await retouchPhoto(png, analyzeEdit('professionnel').plan);
      final back = img.decodeJpg(out)!;
      expect(back.width, 64);
      expect(back.height, 48);
    });
  });
}
