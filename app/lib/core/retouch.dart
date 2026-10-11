// Retouche de photo fidèle, entièrement sur l'appareil.
//
// Aucun service gratuit ne retouche réellement une photo : les IA en ligne recréent une
// image (et changent la personne). Pour une consigne comme « édite cette photo de façon
// professionnelle sans changer la personne ni la composition », Tontolo applique donc de
// vraies corrections d'image (lumière, contraste, couleurs, netteté, filtres) sur la photo
// elle-même : rien n'est envoyé nulle part, la personne et la composition sont intactes.

import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show compute;
import 'package:image/image.dart' as img;

/// Réglages appliqués à la photo.
class RetouchPlan {
  bool autoLevels = false;
  double brightness = 0; // -1 … 1 (ajout)
  double contrast = 1; // multiplicateur autour du gris moyen
  double saturation = 1;
  double gamma = 1; // < 1 éclaircit les tons moyens
  double warmth = 0; // -1 froid … 1 chaud
  double sharpen = 0; // 0 … 1
  double soften = 0; // 0 … 1 (adoucissement / lueur)
  double vignette = 0; // 0 … 1
  double grain = 0; // 0 … 1
  double fade = 0; // 0 … 1 (noirs relevés, rendu « film »)
  bool grayscale = false;
  bool sepia = false;
  final List<String> steps = []; // clés de traduction (rt_…), affichées dans la langue de l'interface

  Map<String, Object> toMap() => {
        'autoLevels': autoLevels, 'brightness': brightness, 'contrast': contrast,
        'saturation': saturation, 'gamma': gamma, 'warmth': warmth, 'sharpen': sharpen,
        'soften': soften, 'vignette': vignette, 'grain': grain, 'fade': fade,
        'grayscale': grayscale, 'sepia': sepia,
      };

  static RetouchPlan fromMap(Map<dynamic, dynamic> m) => RetouchPlan()
    ..autoLevels = m['autoLevels'] as bool
    ..brightness = (m['brightness'] as num).toDouble()
    ..contrast = (m['contrast'] as num).toDouble()
    ..saturation = (m['saturation'] as num).toDouble()
    ..gamma = (m['gamma'] as num).toDouble()
    ..warmth = (m['warmth'] as num).toDouble()
    ..sharpen = (m['sharpen'] as num).toDouble()
    ..soften = (m['soften'] as num).toDouble()
    ..vignette = (m['vignette'] as num).toDouble()
    ..grain = (m['grain'] as num).toDouble()
    ..fade = (m['fade'] as num).toDouble()
    ..grayscale = m['grayscale'] as bool
    ..sepia = m['sepia'] as bool;
}

enum EditMode {
  /// Retouche fidèle faite sur l'appareil.
  local,

  /// Transformation créative : réinterprétation par une IA en ligne (la personne peut changer).
  creative,
}

class EditIntent {
  EditIntent(this.mode, this.plan, {required this.preservesSubject, required this.contentChange});
  final EditMode mode;
  final RetouchPlan plan;

  /// La consigne demande de ne pas changer la personne / la composition.
  final bool preservesSubject;

  /// La consigne demande de modifier le contenu (fond, objets, style artistique…).
  final bool contentChange;
}

String _norm(String s) {
  const from = 'àâäáãåçéèêëíìîïñóòôöõúùûüýÿœ';
  const to = 'aaaaaaceeeeiiiinooooouuuuyyo';
  final b = StringBuffer();
  for (final c in s.toLowerCase().split('')) {
    final i = from.indexOf(c);
    b.write(i >= 0 ? to[i] : c);
  }
  return b.toString().replaceAll('’', "'");
}

final _preserve = RegExp(
    r"sans (rien )?(changer|modifier|alterer|toucher|deformer)|ne (change|modifie|touche|deforme) pas|"
    r"\b(garde|gardez|conserve|conservez|respecte|preserve)\b|identique|inchange|"
    r"meme (personne|visage|photo|composition|cadrage)|fidele|without changing|keep the (same|person)|"
    r"don't change|do not change|tsy (ovaina|ovana|ovay)");

/// Changements de contenu : impossibles à faire fidèlement avec de simples retouches.
final _contentChange = RegExp(
    r"\b(remplace|remplacer|ajoute|ajouter|supprime|supprimer|enleve|enlever|efface|effacer|retire|"
    r"retirer|change le|changer le|change la|changer la)\b|arriere-?plan|\bfond\b|decor|"
    r"dessin anime|cartoon|manga|anime\b|caricature|aquarelle|peinture|croquis|pixar|ghibli|"
    r"futuriste|cyberpunk|monstre|robot|vieillis|rajeunis|maquill|coiffure|cheveux|vetement|habille|"
    r"transforme (en|la|le)|\ben style (de|d')|portrait en|replace|remove|add a|cartoonish");

final _creativeFuzzy =
    RegExp(r"creati|artistique|original|surprenan|unique|fantas|imagin|reinterpret|inattendu|folle?");

/// Analyse la consigne d'édition d'une photo.
EditIntent analyzeEdit(String text) {
  final original = _norm(text);
  // Les propos de préservation (« sans changer la personne ni la composition… ») ne doivent
  // pas être pris pour des demandes de changement : on les retire avant d'analyser le reste.
  final t = original
      .replaceAll(RegExp(r"(sans|without)( rien)? (changer|modifier|alterer|toucher|deformer|changing|altering)[^,.;]*"), ' ')
      .replaceAll(RegExp(r"\b(ne|n') ?(change|modifie|touche|deforme)\w* pas[^,.;]*"), ' ')
      .replaceAll(RegExp(r"(don't|do not) change[^,.;]*"), ' ')
      .replaceAll(RegExp(r"tsy (ovaina|ovana|ovay)[^,.;]*"), ' ');
  final plan = RetouchPlan();
  var matched = false;
  bool has(String re) => RegExp(re).hasMatch(t);

  void step(String s) => plan.steps.add(s);

  if (has(r'professionnel|\bpro\b|corporate|linkedin|cv\b|portrait soigne|propre|soigne|elegant|matihanina')) {
    plan
      ..autoLevels = true
      ..contrast *= 1.08
      ..saturation *= 1.05
      ..warmth += 0.05
      ..sharpen = math.max(plan.sharpen, 0.5)
      ..vignette = math.max(plan.vignette, 0.12);
    step('rt_pro');
    matched = true;
  }
  if (has(r'eclaircis|eclaircir|plus clair|lumineu|luminosite|trop sombre|illumine|brighten|mazava kokoa|hazavao')) {
    plan..brightness += 0.10..gamma *= 0.88;
    step('rt_bright');
    matched = true;
  }
  if (has(r'assombris|assombrir|plus sombre|trop clair|surexpos')) {
    plan..brightness -= 0.10..gamma *= 1.12;
    step('rt_dark');
    matched = true;
  }
  if (has(r'contraste|contrast|punch|percutant')) {
    plan.contrast *= 1.2;
    step('rt_contrast');
    matched = true;
  }
  if (has(r'\bvif|vives|vivid|vibrant|eclatant|sature|colore|couleurs? (plus )?(intense|riche)')) {
    plan.saturation *= 1.3;
    step('rt_vivid');
    matched = true;
  }
  if (has(r'terne|desature|pale|pastel|moins de couleur')) {
    plan.saturation *= 0.7;
    step('rt_muted');
    matched = true;
  }
  if (has(r'noir et blanc|noir & blanc|\bn&b\b|\bn/b\b|monochrome|niveaux de gris|black and white|grayscale|mainty sy fotsy')) {
    plan..grayscale = true..contrast *= 1.1;
    step('rt_bw');
    matched = true;
  }
  if (has(r'sepia')) {
    plan.sepia = true;
    step('rt_sepia');
    matched = true;
  }
  if (has(r'vintage|retro|ancien|argentique|film\b|nostalg|polaroid')) {
    plan
      ..fade = 0.35
      ..saturation *= 0.85
      ..warmth += 0.15
      ..grain = 0.45
      ..vignette = math.max(plan.vignette, 0.3);
    step('rt_vintage');
    matched = true;
  }
  if (has(r'dramatique|cinema|cinematograph|moody|sombre et|intense')) {
    plan
      ..contrast *= 1.25
      ..saturation *= 0.9
      ..gamma *= 1.1
      ..vignette = math.max(plan.vignette, 0.4);
    step('rt_drama');
    matched = true;
  }
  if (has(r'chaud|warm|dore|golden|coucher de soleil')) {
    plan.warmth += 0.25;
    step('rt_warm');
    matched = true;
  }
  if (has(r'froid|cool|bleute|glacial')) {
    plan.warmth -= 0.25;
    step('rt_cool');
    matched = true;
  }
  if (has(r'\bdoux|douce|soft|glamour|adouci|lisse|eclat de peau|lueur')) {
    plan.soften = 0.3;
    step('rt_soft');
    matched = true;
  }
  if (has(r'\bnet\b|nette|nettete|sharp|precis|detail')) {
    plan.sharpen = math.max(plan.sharpen, 0.8);
    step('rt_sharp');
    matched = true;
  }
  if (has(r'\bhdr\b')) {
    plan
      ..autoLevels = true
      ..contrast *= 1.2
      ..saturation *= 1.2
      ..sharpen = math.max(plan.sharpen, 0.8);
    step('rt_hdr');
    matched = true;
  }

  final preserves = _preserve.hasMatch(original);
  final change = _contentChange.hasMatch(t);
  final fuzzy = _creativeFuzzy.hasMatch(t);

  if (!matched) {
    // « édite / améliore / retouche cette photo » : amélioration automatique, fidèle.
    plan
      ..autoLevels = true
      ..contrast = 1.06
      ..saturation = 1.08
      ..sharpen = 0.4
      ..vignette = 0.08;
    step('rt_auto');
  }

  final mode = (change || (fuzzy && !matched && !preserves)) ? EditMode.creative : EditMode.local;
  return EditIntent(mode, plan, preservesSubject: preserves, contentChange: change);
}

/// Au-delà (≈ 60 mégapixels), la retouche locale est refusée (protection de la mémoire).
const maxRetouchPixels = 60000000;

/// Applique les réglages (dans un autre fil d'exécution). Renvoie un JPEG.
Future<Uint8List> retouchPhoto(Uint8List bytes, RetouchPlan plan, {int maxSide = 2048}) =>
    compute(_retouchIsolate, {'bytes': bytes, 'plan': plan.toMap(), 'maxSide': maxSide});

Uint8List _retouchIsolate(Map<String, Object> args) {
  final bytes = args['bytes'] as Uint8List;
  final plan = RetouchPlan.fromMap(args['plan'] as Map);
  final maxSide = args['maxSide'] as int;
  // Garde-fou mémoire : une image piégée (dimensions énormes) n'est jamais décodée en entier.
  final info = img.findDecoderForData(bytes)?.startDecode(bytes);
  if (info == null || info.width * info.height > maxRetouchPixels) {
    throw const FormatException('Image illisible ou trop grande');
  }
  var im = img.decodeImage(bytes);
  if (im == null) throw const FormatException('Image illisible');
  im = img.bakeOrientation(im); // photos de téléphone : on respecte l'orientation EXIF
  if (im.width > maxSide || im.height > maxSide) {
    im = im.width >= im.height
        ? img.copyResize(im, width: maxSide, interpolation: img.Interpolation.average)
        : img.copyResize(im, height: maxSide, interpolation: img.Interpolation.average);
  }
  final out = applyPlan(im, plan);
  return Uint8List.fromList(img.encodeJpg(out, quality: 92));
}

/// Cœur de la retouche (pur Dart, testable).
img.Image applyPlan(img.Image src, RetouchPlan p) {
  final rgba = src.convert(format: img.Format.uint8, numChannels: 4);
  final w = rgba.width, h = rgba.height;
  final d = Uint8List.fromList(rgba.getBytes(order: img.ChannelOrder.rgba));

  double lo = 0, hi = 255;
  if (p.autoLevels) {
    // Étirement des niveaux sur les percentiles 1 % / 99 % de la luminance.
    final hist = List<int>.filled(256, 0);
    for (var i = 0; i < d.length; i += 4) {
      hist[((d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) ~/ 1000)]++;
    }
    final total = w * h;
    var acc = 0;
    for (var v = 0; v < 256; v++) {
      acc += hist[v];
      if (acc >= total * 0.01) {
        lo = v.toDouble();
        break;
      }
    }
    acc = 0;
    for (var v = 255; v >= 0; v--) {
      acc += hist[v];
      if (acc >= total * 0.01) {
        hi = v.toDouble();
        break;
      }
    }
    if (hi - lo < 40) {
      lo = 0;
      hi = 255; // image déjà très plate : on ne force pas
    }
  }
  final scale = 255.0 / (hi - lo);
  final lut = Uint8List(256); // niveaux + gamma + luminosité + contraste (par canal)
  for (var v = 0; v < 256; v++) {
    var x = ((v - lo) * scale).clamp(0.0, 255.0) / 255.0;
    if (p.gamma != 1) x = math.pow(x, p.gamma).toDouble();
    x += p.brightness;
    x = (x - 0.5) * p.contrast + 0.5;
    if (p.fade > 0) x = p.fade * 0.08 + x * (1 - p.fade * 0.12); // noirs relevés
    lut[v] = (x.clamp(0.0, 1.0) * 255).round();
  }

  for (var i = 0; i < d.length; i += 4) {
    var r = lut[d[i]].toDouble(), g = lut[d[i + 1]].toDouble(), b = lut[d[i + 2]].toDouble();
    final lum = 0.299 * r + 0.587 * g + 0.114 * b;
    if (p.saturation != 1) {
      r = lum + (r - lum) * p.saturation;
      g = lum + (g - lum) * p.saturation;
      b = lum + (b - lum) * p.saturation;
    }
    if (p.warmth != 0) {
      r += 22 * p.warmth;
      b -= 22 * p.warmth;
    }
    if (p.grayscale) {
      r = g = b = lum;
    } else if (p.sepia) {
      final l = 0.299 * r + 0.587 * g + 0.114 * b;
      r = l * 1.07 + 18;
      g = l * 0.95 + 8;
      b = l * 0.78;
    }
    d[i] = r.clamp(0, 255).round();
    d[i + 1] = g.clamp(0, 255).round();
    d[i + 2] = b.clamp(0, 255).round();
  }

  var out = img.Image.fromBytes(
      width: w, height: h, bytes: d.buffer, order: img.ChannelOrder.rgba, numChannels: 4);

  if (p.sharpen > 0 || p.soften > 0) {
    final blur = img.gaussianBlur(out.clone(), radius: math.max(1, (math.min(w, h) / 600).round() + 1));
    final b = blur.getBytes(order: img.ChannelOrder.rgba);
    final o = out.getBytes(order: img.ChannelOrder.rgba);
    final res = Uint8List(o.length);
    for (var i = 0; i < o.length; i += 4) {
      for (var c = 0; c < 3; c++) {
        var v = o[i + c].toDouble();
        if (p.sharpen > 0) v += p.sharpen * 0.9 * (v - b[i + c]);
        if (p.soften > 0) v = v * (1 - p.soften) + b[i + c] * p.soften;
        res[i + c] = v.clamp(0, 255).round();
      }
      res[i + 3] = 255;
    }
    out = img.Image.fromBytes(
        width: w, height: h, bytes: res.buffer, order: img.ChannelOrder.rgba, numChannels: 4);
  }

  if (p.vignette > 0 || p.grain > 0) {
    final o = out.getBytes(order: img.ChannelOrder.rgba);
    final res = Uint8List.fromList(o);
    final rnd = math.Random(7);
    final cx = w / 2, cy = h / 2;
    final maxD = math.sqrt(cx * cx + cy * cy);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final i = (y * w + x) * 4;
        var k = 1.0;
        if (p.vignette > 0) {
          final dist = math.sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy)) / maxD;
          k -= p.vignette * math.pow(dist, 2.2);
        }
        final n = p.grain > 0 ? (rnd.nextDouble() - 0.5) * 22 * p.grain : 0.0;
        for (var c = 0; c < 3; c++) {
          res[i + c] = (res[i + c] * k + n).clamp(0, 255).round();
        }
      }
    }
    out = img.Image.fromBytes(
        width: w, height: h, bytes: res.buffer, order: img.ChannelOrder.rgba, numChannels: 4);
  }
  return out;
}
