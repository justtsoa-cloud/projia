// Dossier de cache unique, partagé avec le cœur : <support>/projia/cache/
// (updates/ : la mise à jour téléchargée ; tmp/ : dictée, vidéos, partages). Nettoyé par le
// cœur au démarrage (temporaires de plus d'un jour, mises à jour déjà installées).

import 'dart:io';

import 'package:path_provider/path_provider.dart';

Future<Directory> cacheDir(String sub) async {
  final dir = Directory('${(await getApplicationSupportDirectory()).path}/projia/cache/$sub');
  await dir.create(recursive: true);
  return dir;
}

Future<Directory> tmpDir() => cacheDir('tmp');
