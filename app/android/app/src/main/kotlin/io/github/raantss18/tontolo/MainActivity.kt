package io.github.raantss18.tontolo

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var authChannel: MethodChannel? = null

    private fun authLink(intent: Intent?): String? {
        val uri = intent?.data ?: return null
        if (intent.action != Intent.ACTION_VIEW || uri.scheme != "io.github.raantss18.tontolo" ||
            uri.host != "login-callback" || uri.path != "/") return null
        return uri.toString()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        authChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "tontolo/auth")
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "tontolo/background")
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
        authChannel?.setMethodCallHandler { call, result ->
            if (call.method == "initialAuthLink") {
                result.success(authLink(intent))
                intent.data = null
            } else result.notImplemented()
        }
    }

    override fun onDestroy() {
        TurnService.stop(this)
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        authLink(intent)?.let { authChannel?.invokeMethod("authLink", it) }
    }
}
