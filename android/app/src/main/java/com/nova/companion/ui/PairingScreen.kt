package com.nova.companion.ui

import android.content.Context
import android.util.Log
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nova.companion.security.SecurityManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

enum class PairingState {
    IDLE,
    CONNECTING,
    PAIRING_COMPLETE,
    FAILED
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PairingDialog(
    onPairingSuccess: (serverHost: String) -> Unit,
    onDismiss: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var serverHost by remember { mutableStateOf("100.91.159.98") }
    var pairingIdInput by remember { mutableStateOf("auto") }
    var pinInput by remember { mutableStateOf("123456") }
    var pairingState by remember { mutableStateOf(PairingState.IDLE) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {},
        dismissButton = {},
        title = {
            Text(
                text = "1-Tap Quick Pair",
                fontWeight = FontWeight.Bold,
                fontSize = 20.sp,
                color = Color.White
            )
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(
                    text = when (pairingState) {
                        PairingState.IDLE -> "Tap 'Connect' below to automatically pair with your laptop over Tailscale:"
                        PairingState.CONNECTING -> "Connecting & Authenticating with Nova Core..."
                        PairingState.PAIRING_COMPLETE -> "✓ Pairing Successful!"
                        PairingState.FAILED -> "Error: ${errorMessage ?: "Pairing Failed"}"
                    },
                    fontSize = 14.sp,
                    color = if (pairingState == PairingState.PAIRING_COMPLETE) Color(0xFF4CAF50) else if (pairingState == PairingState.FAILED) Color.Red else Color.LightGray
                )

                if (pairingState == PairingState.IDLE || pairingState == PairingState.FAILED) {
                    OutlinedTextField(
                        value = serverHost,
                        onValueChange = { serverHost = it },
                        label = { Text("Server Host IP") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    OutlinedTextField(
                        value = pinInput,
                        onValueChange = { if (it.length <= 6) pinInput = it },
                        label = { Text("Pairing PIN") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 8.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Button(
                            onClick = {
                                if (serverHost.isNotBlank()) {
                                    pairingState = PairingState.CONNECTING
                                    scope.launch {
                                        val pId = if (pairingIdInput.isBlank()) "auto" else pairingIdInput.trim()
                                        val pinVal = if (pinInput.isBlank()) "123456" else pinInput.trim()
                                        val success = executePairing(context, serverHost.trim(), pId, pinVal) { err ->
                                            errorMessage = err
                                        }
                                        if (success) {
                                            pairingState = PairingState.PAIRING_COMPLETE
                                            onPairingSuccess(serverHost.trim())
                                        } else {
                                            pairingState = PairingState.FAILED
                                        }
                                    }
                                } else {
                                    errorMessage = "Please enter Server Host IP"
                                    pairingState = PairingState.FAILED
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF6200EE), contentColor = Color.White)
                        ) {
                            Text("1-Tap Connect", fontWeight = FontWeight.Bold)
                        }

                        OutlinedButton(
                            onClick = onDismiss,
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("Cancel")
                        }
                    }
                } else if (pairingState == PairingState.CONNECTING) {
                    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator(modifier = Modifier.size(36.dp))
                    }
                }
            }
        }
    )
}

private suspend fun executePairing(
    context: Context,
    host: String,
    pairingId: String,
    pin: String,
    onError: (String) -> Unit
): Boolean = withContext(Dispatchers.IO) {
    try {
        val client = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .build()

        val secMgr = SecurityManager(context)
        val deviceId = secMgr.getDeviceId()

        val bodyJson = JSONObject().apply {
            put("pairing_id", pairingId)
            put("pin", pin)
            put("device_id", deviceId)
            put("device_name", "Samsung Galaxy A13")
            put("platform", "android")
        }

        val requestUrl = "http://$host:8000/api/v2/companion/pair/confirm"
        val requestBody = bodyJson.toString().toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url(requestUrl)
            .post(requestBody)
            .build()

        val response = client.newCall(request).execute()
        val respStr = response.body?.string() ?: ""

        if (response.isSuccessful) {
            val json = JSONObject(respStr)
            val accessToken = json.optString("access_token")
            val refreshToken = json.optString("refresh_token")
            val serverPubKey = json.optString("server_public_key")

            secMgr.saveTokens(accessToken, refreshToken)
            secMgr.saveServerPublicKey(serverPubKey)
            
            val wsUrl = "ws://$host:8000/api/v2/companion/ws"
            secMgr.saveServerUrl(wsUrl)

            Log.i("PairingScreen", "Pairing successful! Saved JWT tokens and WS URL: $wsUrl")
            true
        } else {
            val errDetail = try { JSONObject(respStr).optString("detail", "HTTP ${response.code}") } catch (e: Exception) { "HTTP ${response.code}" }
            withContext(Dispatchers.Main) { onError(errDetail) }
            false
        }
    } catch (e: Exception) {
        Log.e("PairingScreen", "Pairing HTTP error: ${e.message}")
        withContext(Dispatchers.Main) { onError(e.message ?: "Network error connecting to $host:8000") }
        false
    }
}
