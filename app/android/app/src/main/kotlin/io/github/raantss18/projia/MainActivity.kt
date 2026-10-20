package io.github.raantss18.projia

import android.content.Intent
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import java.io.ByteArrayOutputStream
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var authChannel: MethodChannel? = null
    private var shortcutChannel: MethodChannel? = null
    private var askPending = false

    companion object {
        const val ACTION_ASK = "io.github.raantss18.projia.ASK"
    }

    private fun authLink(intent: Intent?): String? {
        val uri = intent?.data ?: return null
        if (intent.action != Intent.ACTION_VIEW || uri.scheme != "io.github.raantss18.projia" ||
            uri.host != "login-callback" || uri.path != "/") return null
        return uri.toString()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        authChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "projia/auth")
        // Raccourci et widget « Demander à Projia » : nouvelle discussion, clavier prêt.
        askPending = intent?.action == ACTION_ASK
        shortcutChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "projia/shortcut")
        shortcutChannel?.setMethodCallHandler { call, result ->
            if (call.method == "initialAsk") {
                result.success(askPending)
                askPending = false
            } else result.notImplemented()
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "projia/background")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "start" -> { TurnService.start(this); result.success(null) }
                        "stop" -> { TurnService.stop(this); result.success(null) }
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) { // démarrage refusé (application déjà en arrière-plan)
                    result.error("background", e.message, null)
                }
            }
        // Images clés d'une vidéo jointe (Android n'a pas ffmpeg) : décrites ensuite par un
        // modèle à vision, en plus de la transcription du son.
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "projia/video")
            .setMethodCallHandler { call, result ->
                if (call.method != "keyframes") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val path = call.argument<String>("path") ?: return@setMethodCallHandler result.success(emptyList<Any>())
                val count = (call.argument<Int>("count") ?: 4).coerceIn(1, 6)
                Thread {
                    val frames = keyframes(path, count)
                    runOnUiThread { result.success(frames) }
                }.start()
            }
        authChannel?.setMethodCallHandler { call, result ->
            if (call.method == "initialAuthLink") {
                result.success(authLink(intent))
                intent.data = null
            } else result.notImplemented()
        }
    }

    private fun keyframes(path: String, count: Int): List<Map<String, Any>> {
        val out = ArrayList<Map<String, Any>>()
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(path)
            val ms = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                ?.toLongOrNull() ?: 0L
            for (i in 0 until if (ms > 0) count else 0) {
                val at = ms * (2 * i + 1) / (2 * count)
                val frame = retriever.getFrameAtTime(at * 1000, MediaMetadataRetriever.OPTION_CLOSEST)
                    ?: continue
                val small = if (frame.width > 640)
                    Bitmap.createScaledBitmap(frame, 640, frame.height * 640 / frame.width, true)
                else frame
                val jpg = ByteArrayOutputStream()
                small.compress(Bitmap.CompressFormat.JPEG, 75, jpg)
                out.add(mapOf("t" to at / 1000.0, "jpg" to jpg.toByteArray()))
            }
        } catch (e: Exception) { // vidéo illisible : la transcription du son suffira
        } finally {
            try { retriever.release() } catch (e: Exception) {}
        }
        return out
    }

    override fun onDestroy() {
        TurnService.stop(this)
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.action == ACTION_ASK) shortcutChannel?.invokeMethod("ask", null)
        authLink(intent)?.let { authChannel?.invokeMethod("authLink", it) }
    }
}
