// NOT BUILT OR TESTED here. Receives the Assistant's text, calls ContextIQ's read-only voice endpoint, speaks the reply.
package com.contextiq.app

import android.app.Activity
import android.os.Bundle
import android.speech.tts.TextToSpeech
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class AskActivity : Activity() {
    private lateinit var tts: TextToSpeech
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val question = intent.getStringExtra("question") ?: intent.data?.getQueryParameter("question") ?: return finish()
        tts = TextToSpeech(this) { thread { speak(ask(question)) } }
    }
    private fun ask(q: String): String = try {
        val c = URL(BuildConfig.CONTEXTIQ_URL + "/api/voice").openConnection() as HttpURLConnection
        c.requestMethod = "POST"; c.doOutput = true
        c.setRequestProperty("Content-Type", "application/json")
        c.setRequestProperty("X-Voice-Token", BuildConfig.VOICE_TOKEN)
        c.outputStream.use { it.write(JSONObject(mapOf("text" to q)).toString().toByteArray()) }
        JSONObject(c.inputStream.bufferedReader().readText()).getString("speech")
    } catch (e: Exception) { "Sorry, I couldn't reach ContextIQ." }
    private fun speak(s: String) = runOnUiThread { tts.speak(s, TextToSpeech.QUEUE_FLUSH, null, "ciq") }
}
