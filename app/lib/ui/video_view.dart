// Lecture d'une vidéo générée : intégrée sous Android, lecteur du système sous Linux
// (le lecteur Flutter n'existe pas sur Linux, et un lecteur externe garde l'application légère).

import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:video_player/video_player.dart';

import '../main.dart';

class VideoBox extends StatefulWidget {
  const VideoBox({super.key, required this.bytes, required this.id});
  final Uint8List bytes;
  final String id;

  @override
  State<VideoBox> createState() => _VideoBoxState();
}

class _VideoBoxState extends State<VideoBox> {
  VideoPlayerController? _ctrl;
  File? _file;
  bool _failed = false;

  bool get _embedded => Platform.isAndroid || Platform.isIOS;

  @override
  void initState() {
    super.initState();
    _prepare();
  }

  Future<void> _prepare() async {
    final dir = await getTemporaryDirectory();
    final f = File('${dir.path}/tontolo-video-${widget.id}.mp4');
    if (!await f.exists() || await f.length() != widget.bytes.length) await f.writeAsBytes(widget.bytes);
    _file = f;
    if (!_embedded) {
      if (mounted) setState(() {});
      return;
    }
    final c = VideoPlayerController.file(f);
    try {
      await c.initialize();
      await c.setLooping(true);
      if (!mounted) {
        await c.dispose();
        return;
      }
      c.addListener(() => mounted ? setState(() {}) : null);
      setState(() => _ctrl = c);
    } catch (_) {
      await c.dispose();
      if (mounted) setState(() => _failed = true);
    }
  }

  @override
  void dispose() {
    _ctrl?.dispose();
    super.dispose();
  }

  void _external() {
    if (_file != null) OpenFilex.open(_file!.path, type: 'video/mp4');
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final c = _ctrl;
    if (!_embedded || _failed) {
      return OutlinedButton.icon(
        onPressed: _file == null ? null : _external,
        icon: const Icon(Icons.play_circle_outline),
        label: Text(context.t('play_video')),
      );
    }
    if (c == null) {
      return const SizedBox(width: 320, height: 180, child: Center(child: CircularProgressIndicator()));
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 360, maxHeight: 420),
        child: AspectRatio(
          aspectRatio: c.value.aspectRatio,
          child: GestureDetector(
            onTap: () => c.value.isPlaying ? c.pause() : c.play(),
            child: Stack(alignment: Alignment.center, children: [
              VideoPlayer(c),
              if (!c.value.isPlaying)
                CircleAvatar(
                  radius: 28,
                  backgroundColor: scheme.surface.withValues(alpha: 0.75),
                  child: Icon(Icons.play_arrow, size: 34, color: scheme.primary),
                ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: VideoProgressIndicator(c, allowScrubbing: true, padding: const EdgeInsets.all(6)),
              ),
              Positioned(
                top: 4,
                right: 4,
                child: IconButton(
                  tooltip: context.t('open_external'),
                  icon: Icon(Icons.open_in_new, color: scheme.surface),
                  onPressed: _external,
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
