package com.nova.companion

import android.app.Application
import android.util.Log

class NovaCompanionApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        Log.i("NovaCompanion", "Nova Companion Android Application Initialized (v2.0.0)")
    }
}
