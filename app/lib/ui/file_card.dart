// Carte « fichier » d'une création (DOCX, PDF, XLSX, PPTX, code…) : ouvrir avec l'application
// du système, partager, enregistrer ; et le travail de l'équipe de modèles (rédaction,
// relecture, corrections) affiché en une ligne.

import 'dart:io';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:share_plus/share_plus.dart';

import '../core/storage_dirs.dart';
import '../main.dart';

IconData fileIcon(String filename) => switch (filename.split('.').last.toLowerCase()) {
      'pdf' => Icons.picture_as_pdf_outlined,
      'docx' || 'doc' || 'md' || 'txt' => Icons.description_outlined,
      'xlsx' || 'csv' => Icons.table_chart_outlined,
      'pptx' => Icons.slideshow_outlined,
      'png' || 'svg' => Icons.image_outlined,
      'ics' => Icons.event_outlined,
      'zip' => Icons.folder_zip_outlined,
      _ => Icons.code,
    };

String sizeText(BuildContext context, int bytes) => bytes < 1024
    ? context.t('size_b', {'n': '$bytes'})
    : bytes < 1024 * 1024
        ? context.t('size_kb', {'n': (bytes / 1024).toStringAsFixed(0)})
        : context.t('size_mb', {'n': (bytes / 1024 / 1024).toStringAsFixed(1)});

/// « Rédigé par X · relu par Y · 2 corrections ».
String teamLine(BuildContext context, Map<String, dynamic> params) {
  final steps = (params['steps'] as List?)?.cast<Map>() ?? const [];
  final writer = steps.where((s) => s['step'] == 'doc_writing').map((s) => '${s['model']}').firstOrNull;
  final reviewer = steps.where((s) => s['step'] == 'doc_reviewing').map((s) => '${s['model']}').firstOrNull;
  final fixes = steps.where((s) => s['step'] == 'doc_fixing').length;
  return [
    if (writer != null) context.t('team_writer', {'m': writer}),
    if (reviewer != null) context.t('team_reviewer', {'m': reviewer}),
    if (fixes > 0) context.t('team_fixes', {'n': '$fixes'}),
    context.t('team_checked'),
  ].join(' · ');
}

Future<File> _temp(Uint8List bytes, String name) async {
  final dir = await tmpDir();
  final f = File('${dir.path}/$name');
  await f.writeAsBytes(bytes, flush: true);
  return f;
}

class FileCard extends StatelessWidget {
  const FileCard({super.key, required this.bytes, required this.params});
  final Uint8List bytes;
  final Map<String, dynamic> params;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final name = '${params['filename'] ?? 'fichier'}';
    final mime = '${params['mime'] ?? 'application/octet-stream'}'.split(';').first;
    final messenger = ScaffoldMessenger.of(context);
    final t = context.t;
    return Card(
      margin: EdgeInsets.zero,
      color: scheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            CircleAvatar(radius: 22, backgroundColor: scheme.primaryContainer, child: Icon(fileIcon(name), color: scheme.onPrimaryContainer)),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${params['title'] ?? name}', style: Theme.of(context).textTheme.titleSmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                Text('$name · ${sizeText(context, bytes.length)}', style: Theme.of(context).textTheme.bodySmall),
              ]),
            ),
          ]),
          const SizedBox(height: 8),
          Text(teamLine(context, params), style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 6, children: [
            FilledButton.icon(
              icon: const Icon(Icons.open_in_new, size: 18),
              label: Text(t('file_open')),
              onPressed: () async {
                final f = await _temp(bytes, name);
                final r = await OpenFilex.open(f.path, type: mime);
                if (r.type != ResultType.done) messenger.showSnackBar(SnackBar(content: Text(t('file_no_app'))));
              },
            ),
            OutlinedButton.icon(
              icon: const Icon(Icons.share_outlined, size: 18),
              label: Text(t('share')),
              onPressed: () => SharePlus.instance.share(ShareParams(files: [XFile.fromData(bytes, mimeType: mime, name: name)])),
            ),
            OutlinedButton.icon(
              icon: const Icon(Icons.download_outlined, size: 18),
              label: Text(t('file_save')),
              onPressed: () async {
                try {
                  final uri = await FilePicker.saveFile(fileName: name, bytes: bytes, mimeType: mime);
                  if (uri != null) messenger.showSnackBar(SnackBar(content: Text(t('file_saved'))));
                } catch (_) {
                  messenger.showSnackBar(SnackBar(content: Text(t('error_generic'))));
                }
              },
            ),
          ]),
        ]),
      ),
    );
  }
}
