// ignore_for_file: invalid_use_of_visible_for_testing_member
// Banc de démonstration (développement) : fait tourner la vraie interface Tontolo en taille
// « bureau » (1440×900), branchée sur un moteur Tontolo réel (`tontolo serve`), et enregistre
// ses images pour fabriquer captures et vidéos. Lancement :
//   flutter test demo/desktop_demo_test.dart
// Variables : DEMO_URL (moteur), DEMO_OUT (dossier des images), DEMO_STILLS (captures fixes).

import 'dart:io';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart' show FontLoader, MethodChannel;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tontolo/core/backend.dart';
import 'package:tontolo/core/chat_controller.dart';
import 'package:tontolo/core/prefs.dart';
import 'package:tontolo/core/updater.dart';
import 'package:tontolo/main.dart';

final _url = Platform.environment['DEMO_URL'] ?? 'http://127.0.0.1:8777';
final _out = Platform.environment['DEMO_OUT'] ?? '/tmp/tontolo_frames';
final _stills = Platform.environment['DEMO_STILLS'] ?? '/tmp/tontolo_stills';
final _fontDir = '${Platform.environment['HOME']}/development/flutter/bin/cache/artifacts/material_fonts';

Future<void> _loadFonts() async {
  ByteData bytes(File f) => ByteData.view(f.readAsBytesSync().buffer);
  final roboto = FontLoader('Roboto');
  for (final n in ['Regular', 'Medium', 'Bold', 'Italic', 'Light']) {
    roboto.addFont(Future.value(bytes(File('$_fontDir/Roboto-$n.ttf'))));
  }
  await roboto.load();
  final mono = File('/usr/share/fonts/TTF/DejaVuSansMono.ttf');
  if (mono.existsSync()) {
    final m = FontLoader('monospace')..addFont(Future.value(bytes(mono)));
    await m.load();
  }
  final icons = FontLoader('MaterialIcons')
    ..addFont(Future.value(bytes(File('$_fontDir/MaterialIcons-Regular.otf'))));
  await icons.load();
  // Polices mathématiques KaTeX du paquet flutter_math_fork.
  final pub = '${Platform.environment['HOME']}/.pub-cache/hosted/pub.dev';
  final mathDir = Directory(pub)
      .listSync()
      .whereType<Directory>()
      .where((d) => d.path.contains('flutter_math_fork-'))
      .map((d) => Directory('${d.path}/lib/katex_fonts/fonts'))
      .firstWhere((d) => d.existsSync());
  final families = <String, FontLoader>{};
  for (final f in mathDir.listSync().whereType<File>().where((f) => f.path.endsWith('.ttf'))) {
    final family = f.uri.pathSegments.last.split('-').first;
    final loader = families.putIfAbsent(
        family, () => FontLoader('packages/flutter_math_fork/$family'));
    loader.addFont(Future.value(bytes(f)));
  }
  for (final l in families.values) {
    await l.load();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('démo bureau', timeout: const Timeout(Duration(minutes: 15)), (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android; // police Roboto
    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1.0;
    FlutterSecureStorage.setMockInitialValues({});
    SharedPreferences.setMockInitialValues({
      'onboarded': true,
      'lastSeenVersion': appVersion,
      'remoteUrl': _url,
      'locale': 'fr',
    });
    // Plugins natifs absents du banc d'essai (voix, micro, partage) : réponses neutres.
    final messenger = tester.binding.defaultBinaryMessenger;
    for (final ch in ['flutter_tts', 'com.llfbandit.record/messages', 'xyz.luan/audioplayers',
        'xyz.luan/audioplayers.global', 'dev.fluttercommunity.plus/share']) {
      messenger.setMockMethodCallHandler(MethodChannel(ch), (call) async => 1);
    }
    await tester.runAsync(_loadFonts);
    HttpOverrides.global = null; // vraies connexions réseau vers le moteur local
    Directory(_out).createSync(recursive: true);
    Directory(_stills).createSync(recursive: true);

    final key = GlobalKey();
    late Prefs prefs;
    late Backend backend;
    late ChatController chat;
    await tester.runAsync(() async {
      prefs = await Prefs.load();
      backend = Backend(prefs);
      chat = ChatController(backend);
    });
    await tester.pumpWidget(RepaintBoundary(
      key: key,
      child: AppScope(prefs: prefs, backend: backend, updater: Updater(prefs), chat: chat, child: const TontoloApp()),
    ));

    // Le logo est une image d'application : on la précharge (décodage asynchrone).
    await tester.runAsync(() async {
      await precacheImage(const AssetImage('assets/icon.png'), tester.element(find.byType(MaterialApp)));
    });
    await tester.pump();

    var n = 0;
    String? lastHash;
    Future<Uint8List> shot() async {
      final b = key.currentContext!.findRenderObject() as RenderRepaintBoundary;
      return (await tester.runAsync(() async {
        final img = await b.toImage(pixelRatio: 1.0);
        final data = await img.toByteData(format: ui.ImageByteFormat.png);
        return data!.buffer.asUint8List();
      }))!;
    }

    Future<void> frame({bool force = false}) async {
      final png = await shot();
      final h = md5.convert(png).toString();
      if (!force && h == lastHash) return; // image identique : on l'ignore (compresse l'attente)
      lastHash = h;
      File('$_out/${(n++).toString().padLeft(5, '0')}.png').writeAsBytesSync(png);
    }

    void mark(String name) =>
        File('$_out/markers.txt').writeAsStringSync('$n $name\n', mode: FileMode.append);

    Future<void> still(String name) async => File('$_stills/$name.png').writeAsBytesSync(await shot());

    /// Laisse le temps réel s'écouler (réseau) en capturant les images au passage.
    Future<void> run(Duration d, {Duration every = const Duration(milliseconds: 220)}) async {
      final end = DateTime.now().add(d);
      while (DateTime.now().isBefore(end)) {
        await tester.runAsync(() => Future.delayed(every));
        await tester.pump(const Duration(milliseconds: 40));
        await frame();
      }
    }

    Future<void> hold(int frames) async {
      await tester.pump(const Duration(milliseconds: 60));
      for (var i = 0; i < frames; i++) {
        await frame(force: true);
      }
    }

    Future<void> until(bool Function() cond, Duration max) async {
      final end = DateTime.now().add(max);
      while (!cond() && DateTime.now().isBefore(end)) {
        await run(const Duration(milliseconds: 400));
      }
    }

    // --- Démarrage : le moteur répond, l'interface est prête ---
    await tester.runAsync(backend.start);
    await until(() => backend.state == BackendState.ready, const Duration(seconds: 60));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(milliseconds: 600));
    await hold(14);
    await still('d01-accueil');

    // --- Scène 1 : question saisie au clavier, réponse avec formules ---
    mark('chat');
    const question = 'Explique la dérivée avec un exemple et la formule';
    final field = find.byType(TextField).last;
    for (var i = 1; i <= question.length; i++) {
      await tester.enterText(field, question.substring(0, i));
      await tester.pump(const Duration(milliseconds: 30));
      await frame(force: true);
    }
    await hold(6);
    await tester.tap(find.byIcon(Icons.arrow_upward));
    await tester.pump();
    await until(() => chat.busy, const Duration(seconds: 5));
    await until(() => !chat.busy, const Duration(seconds: 150));
    await run(const Duration(seconds: 2));
    await still('d02-reponse-formules');
    await hold(10);

    // --- Scène 2 : sélecteur de modèles gratuits ---
    mark('modeles');
    await tester.tap(find.textContaining('Auto'));
    await run(const Duration(seconds: 2));
    await still('d03-selecteur-modeles');
    await hold(20);
    await tester.tapAt(const Offset(150, 150)); // ferme la feuille
    await run(const Duration(seconds: 1));

    // --- Scène 3 : réglages (clés gratuites) ---
    mark('reglages');
    await tester.tap(find.text('Réglages'));
    await run(const Duration(seconds: 3));
    await still('d04-reglages');
    await hold(16);

    // --- Scène 4 : galerie des créations ---
    mark('creations');
    await tester.tap(find.text('Créations'));
    await run(const Duration(seconds: 3));
    await still('d05-creations');
    await hold(12);
    // --- Scène finale (optionnelle, DEMO_IMAGE=1) : création d'une image, sans clé ---
  if (Platform.environment['DEMO_IMAGE'] == '1') {
    mark('image');
    await tester.tap(find.byIcon(Icons.edit_square));
    await run(const Duration(seconds: 1));
    await tester.tap(find.text('Dessine un phare au coucher du soleil'));
    await tester.pump();
    await until(() => chat.busy, const Duration(seconds: 5));
    await until(() => !chat.busy, const Duration(seconds: 100));
    await run(const Duration(seconds: 4)); // le temps d'afficher l'image
    await still('d06-image-phare');
    await hold(18);
  }

    mark('fin');
    debugDefaultTargetPlatformOverride = null;
  });
}
