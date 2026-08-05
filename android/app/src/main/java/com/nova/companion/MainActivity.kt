package com.nova.companion

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import java.util.Locale
import android.media.AudioManager
import android.media.ToneGenerator
import com.nova.companion.core.DiagnosticItem
import com.nova.companion.core.StartupValidator
import com.nova.companion.services.CompanionForegroundService

class MainActivity : ComponentActivity() {

    private lateinit var validator: StartupValidator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i("MainActivity", "Nova Assistant Launching (v3.0.0)")

        validator = StartupValidator(this)

        setContent {
            var validationReport by remember { mutableStateOf(validator.validateSystemReadiness()) }
            var isListening by remember { mutableStateOf(false) }
            var voiceStatusText by remember { mutableStateOf("Tap to Speak into Phone Mic") }

            val permissionLauncher = rememberLauncherForActivityResult(
                contract = ActivityResultContracts.RequestMultiplePermissions()
            ) { _ ->
                validationReport = validator.validateSystemReadiness()
            }

            val requiredPermissions = remember {
                val list = mutableListOf(
                    Manifest.permission.CAMERA,
                    Manifest.permission.RECORD_AUDIO,
                    Manifest.permission.READ_SMS,
                    Manifest.permission.SEND_SMS,
                    Manifest.permission.READ_CONTACTS,
                    Manifest.permission.CALL_PHONE,
                    Manifest.permission.ACCESS_FINE_LOCATION
                )
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    list.add(Manifest.permission.POST_NOTIFICATIONS)
                }
                list.toTypedArray()
            }

            LaunchedEffect(Unit) {
                permissionLauncher.launch(requiredPermissions)
                startCompanionService()
            }

            MaterialTheme(
                colorScheme = darkColorScheme(
                    primary = Color(0xFF6200EE),
                    secondary = Color(0xFF03DAC6),
                    background = Color(0xFF121212),
                    surface = Color(0xFF1E1E1E)
                )
            ) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    DeploymentDashboardScreen(
                        diagnostics = validationReport.diagnostics,
                        deviceModel = validationReport.deviceModel,
                        androidVersion = validationReport.androidVersion,
                        onRequestPermissions = {
                            permissionLauncher.launch(requiredPermissions)
                            requestBatteryOptimizationExemption()
                        },
                        onStartService = { startCompanionService() },
                        onStopService = { stopCompanionService() }
                    )
                }
            }
        }
    }

    private fun requestBatteryOptimizationExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            try {
                val pm = getSystemService(POWER_SERVICE) as? android.os.PowerManager
                if (pm?.isIgnoringBatteryOptimizations(packageName) == false) {
                    val intent = Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                        data = android.net.Uri.parse("package:$packageName")
                    }
                    startActivity(intent)
                }
            } catch (e: Exception) {
                Log.e("MainActivity", "Failed to open battery optimization settings: ${e.message}")
            }
        }
    }

    private fun startCompanionService() {
        try {
            Log.i("MainActivity", "Starting Companion Foreground Service")
            val intent = Intent(this, CompanionForegroundService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "Failed to start CompanionForegroundService: ${e.message}")
        }
    }

    private fun stopCompanionService() {
        Log.i("MainActivity", "Stopping Companion Foreground Service")
        val intent = Intent(this, CompanionForegroundService::class.java)
        stopService(intent)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DeploymentDashboardScreen(
    diagnostics: List<DiagnosticItem>,
    deviceModel: String,
    androidVersion: String,
    onRequestPermissions: () -> Unit,
    onStartService: () -> Unit,
    onStopService: () -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var isServiceRunning by remember { mutableStateOf(false) }
    var showPairingDialog by remember { mutableStateOf(false) }
    var isListening by remember { mutableStateOf(false) }
    var voiceStatusText by remember { mutableStateOf("Tap to Speak into Phone Mic") }

    if (showPairingDialog) {
        com.nova.companion.ui.PairingDialog(
            onPairingSuccess = { host ->
                showPairingDialog = false
                onStartService()
                isServiceRunning = true
            },
            onDismiss = { showPairingDialog = false }
        )
    }

    var isHeyNovaActive by remember { mutableStateOf(false) }

    LaunchedEffect(isHeyNovaActive) {
        if (isHeyNovaActive) {
            voiceStatusText = "⚡ 'Hey Nova' Active! Say 'Hey Nova' or speak your command..."
            while (isHeyNovaActive) {
                if (!SpeechRecognizer.isRecognitionAvailable(context)) break
                val recognizer = SpeechRecognizer.createSpeechRecognizer(context)
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                }

                val resultCompletable = kotlinx.coroutines.CompletableDeferred<Unit>()

                recognizer.setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {}
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(rmsdB: Float) {}
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() {}
                    override fun onError(error: Int) {
                        try { recognizer.destroy() } catch (e: Exception) {}
                        resultCompletable.complete(Unit)
                    }
                    override fun onResults(results: Bundle?) {
                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        val spokenText = matches?.firstOrNull() ?: ""
                        if (spokenText.isNotEmpty()) {
                            Log.i("MainActivity", "Hey Nova Listener Heard: '$spokenText'")
                            val lower = spokenText.lowercase().trim()
                            if (lower.contains("nova") || lower.contains("hey nova")) {
                                try {
                                    val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
                                    tone.startTone(ToneGenerator.TONE_PROP_BEEP, 150)
                                } catch (e: Exception) {}

                                val cleanCmd = lower
                                    .replace("hey nova", "")
                                    .replace("ok nova", "")
                                    .replace("hey assistant", "")
                                    .replace("nova", "")
                                    .trim()

                                if (cleanCmd.isEmpty()) {
                                    isListening = true
                                    voiceStatusText = "⚡ 'Hey Nova' Woke Up! Speak your command now..."
                                    startCommandMic(context) { cmdText ->
                                        isListening = false
                                        if (cmdText.isNotEmpty()) {
                                            voiceStatusText = executeVoiceAction(cmdText, context)
                                        }
                                    }
                                } else {
                                    voiceStatusText = executeVoiceAction(spokenText, context)
                                }
                            }
                        }
                        try { recognizer.destroy() } catch (e: Exception) {}
                        resultCompletable.complete(Unit)
                    }
                    override fun onPartialResults(partialResults: Bundle?) {}
                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })

                recognizer.startListening(intent)
                resultCompletable.await()
                kotlinx.coroutines.delay(400)
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Nova Assistant", fontWeight = FontWeight.Bold) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Header Card
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = "Nova Assistant",
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                        Text(
                            text = "Version 3.0.0 (AI Platform Active)",
                            fontSize = 16.sp,
                            color = MaterialTheme.colorScheme.secondary,
                            fontWeight = FontWeight.SemiBold
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "Status",
                            fontSize = 14.sp,
                            color = Color.Gray
                        )
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(12.dp)
                                    .background(if (isServiceRunning) Color(0xFF4CAF50) else Color.Gray, shape = CircleShape)
                            )
                            Text(
                                text = if (isServiceRunning) "Foreground Service Active 🟢" else "Not Connected",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (isServiceRunning) Color(0xFF4CAF50) else Color.LightGray
                            )
                        }
                    }
                }
            }

            // Always-On "Hey Nova" Hotword Activation Card
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = if (isHeyNovaActive) Color(0xFF1B5E20) else MaterialTheme.colorScheme.surface
                    )
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "⚡ 'HEY NOVA' VOICE WAKE WORD",
                                fontSize = 16.sp,
                                fontWeight = FontWeight.Bold,
                                color = Color.White
                            )
                            Text(
                                text = if (isHeyNovaActive) "Always Listening... Speak 'Hey Nova' anytime!" else "Hands-free voice activation like Google Assistant",
                                fontSize = 13.sp,
                                color = Color.LightGray
                            )
                        }
                        Switch(
                            checked = isHeyNovaActive,
                            onCheckedChange = { isHeyNovaActive = it },
                            colors = SwitchDefaults.colors(
                                checkedThumbColor = Color.White,
                                checkedTrackColor = Color(0xFF4CAF50)
                            )
                        )
                    }
                }
            }

            // Interactive Voice Assistant Mic Button
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = if (isListening) Color(0xFF311B92) else MaterialTheme.colorScheme.surface
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Button(
                            onClick = {
                                if (!SpeechRecognizer.isRecognitionAvailable(context)) {
                                    voiceStatusText = "⚠️ Speech recognizer unavailable"
                                    return@Button
                                }
                                isListening = true
                                voiceStatusText = "🎙️ Listening... Speak into your phone now!"

                                val recognizer = SpeechRecognizer.createSpeechRecognizer(context)
                                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
                                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                                }

                                recognizer.setRecognitionListener(object : RecognitionListener {
                                    override fun onReadyForSpeech(params: Bundle?) {}
                                    override fun onBeginningOfSpeech() {}
                                    override fun onRmsChanged(rmsdB: Float) {}
                                    override fun onBufferReceived(buffer: ByteArray?) {}
                                    override fun onEndOfSpeech() {
                                        isListening = false
                                    }
                                    override fun onError(error: Int) {
                                        isListening = false
                                        voiceStatusText = "⚠️ Listening error ($error). Try again!"
                                        try { recognizer.destroy() } catch (e: Exception) {}
                                    }
                                    override fun onResults(results: Bundle?) {
                                        isListening = false
                                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                                        val spokenText = matches?.firstOrNull() ?: ""
                                        Log.i("MainActivity", "Native Voice Heard: '$spokenText'")
                                        val resultMsg = executeVoiceAction(spokenText, context)
                                        voiceStatusText = resultMsg
                                        try { recognizer.destroy() } catch (e: Exception) {}
                                    }
                                    override fun onPartialResults(partialResults: Bundle?) {}
                                    override fun onEvent(eventType: Int, params: Bundle?) {}
                                })

                                recognizer.startListening(intent)
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(56.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isListening) Color(0xFFFF4081) else Color(0xFF6200EE),
                                contentColor = Color.White
                            ),
                            shape = RoundedCornerShape(28.dp)
                        ) {
                            Text(
                                text = if (isListening) "🎙️ LISTENING NOW (4s)..." else "🎙️ TAP TO SPEAK TO NOVA",
                                fontWeight = FontWeight.Bold,
                                fontSize = 16.sp
                            )
                        }
                        Text(
                            text = voiceStatusText,
                            fontSize = 13.sp,
                            color = Color(0xFF03DAC6),
                            fontWeight = FontWeight.Medium
                        )
                    }
                }
            }

            // Target Device Specs
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text("Target Device", fontSize = 14.sp, color = Color.Gray)
                            Text(deviceModel, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Android Version", fontSize = 14.sp, color = Color.Gray)
                            Text("Android $androidVersion", fontSize = 16.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }

            // System Readiness Diagnostics
            item {
                Text(
                    text = "System Readiness Diagnostics",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }

            items(diagnostics) { item ->
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(item.title, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                            Text(item.details, fontSize = 13.sp, color = Color.Gray)
                        }
                        Text(
                            text = if (item.isPassed) "✓ PASS" else "WARN",
                            fontWeight = FontWeight.Bold,
                            color = if (item.isPassed) Color(0xFF4CAF50) else Color(0xFFFF9800)
                        )
                    }
                }
            }

            // Service & Permission Controls
            item {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Button(
                        onClick = onRequestPermissions,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF03DAC6), contentColor = Color.Black)
                    ) {
                        Text("Grant Required Permissions", fontWeight = FontWeight.Bold)
                    }

                    Button(
                        onClick = { showPairingDialog = true },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6200EE), contentColor = Color.White)
                    ) {
                        Text("Pair with Nova Core", fontWeight = FontWeight.Bold)
                    }

                    Button(
                        onClick = {
                            onStartService()
                            isServiceRunning = true
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Start Foreground Service")
                    }

                    OutlinedButton(
                        onClick = {
                            onStopService()
                            isServiceRunning = false
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("Stop Companion Service")
                    }
                }
            }
        }
    }
}

fun executeVoiceAction(spokenText: String, context: android.content.Context): String {
    val lower = spokenText.lowercase()
        .replace("hey nova", "")
        .replace("ok nova", "")
        .replace("hey assistant", "")
        .replace("nova", "")
        .trim()

    val flashlightHandler = com.nova.companion.plugins.hardware.FlashlightHandler(context)
    val appControlHandler = com.nova.companion.plugins.app.AppControlHandler(context)

    return if (lower.contains("flashlight") && (lower.contains("on") || lower.contains("turn on"))) {
        flashlightHandler.execute("flashlight.on", org.json.JSONObject())
        "🔦 Flashlight Turned ON!"
    } else if (lower.contains("flashlight") && (lower.contains("off") || lower.contains("turn off"))) {
        flashlightHandler.execute("flashlight.off", org.json.JSONObject())
        "🔦 Flashlight Turned OFF!"
    } else if (lower.contains("youtube") || lower.contains("song") || (lower.contains("play") && !lower.contains("store"))) {
        val cleanQuery = lower
            .replace("play", "")
            .replace("on youtube", "")
            .replace("in youtube", "")
            .replace("youtube", "")
            .replace("search", "")
            .replace("find", "")
            .trim()
        val searchQuery = if (cleanQuery.isNotEmpty()) cleanQuery else "english song"
        appControlHandler.execute("youtube.play", org.json.JSONObject().put("query", searchQuery))
        "▶ Playing '$searchQuery' on YouTube!"
    } else if (lower.contains("open") || lower.contains("launch")) {
        val appName = lower.replace("open", "").replace("launch", "").trim()
        appControlHandler.execute("app.launch", org.json.JSONObject().put("app_name", appName))
        "📱 Opened $appName!"
    } else {
        "🗣️ Heard: \"$spokenText\""
    }
}

fun startCommandMic(context: android.content.Context, onCommandResult: (String) -> Unit) {
    if (!SpeechRecognizer.isRecognitionAvailable(context)) return
    val recognizer = SpeechRecognizer.createSpeechRecognizer(context)
    val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
        putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
    }
    recognizer.setRecognitionListener(object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onError(error: Int) {
            try { recognizer.destroy() } catch (e: Exception) {}
            onCommandResult("")
        }
        override fun onResults(results: Bundle?) {
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val spokenText = matches?.firstOrNull() ?: ""
            try { recognizer.destroy() } catch (e: Exception) {}
            onCommandResult(spokenText)
        }
        override fun onPartialResults(partialResults: Bundle?) {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
    })
    recognizer.startListening(intent)
}
