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
import com.nova.companion.core.DiagnosticItem
import com.nova.companion.core.StartupValidator
import com.nova.companion.services.CompanionForegroundService

class MainActivity : ComponentActivity() {

    private lateinit var validator: StartupValidator

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i("MainActivity", "Nova Companion Launching (v2.0.0)")

        validator = StartupValidator(this)

        setContent {
            var validationReport by remember { mutableStateOf(validator.validateSystemReadiness()) }

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
    var isServiceRunning by remember { mutableStateOf(false) }
    var showPairingDialog by remember { mutableStateOf(false) }

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

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Nova Companion", fontWeight = FontWeight.Bold) },
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
                            text = "Nova Companion",
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                        Text(
                            text = "Version 2.0",
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
                                text = if (isServiceRunning) "Foreground Service Active (Not Connected)" else "Not Connected",
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (isServiceRunning) Color(0xFF4CAF50) else Color.LightGray
                            )
                        }
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
