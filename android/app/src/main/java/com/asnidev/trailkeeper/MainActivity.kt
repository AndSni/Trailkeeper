package com.asnidev.trailkeeper

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.asnidev.trailkeeper.data.Session
import com.asnidev.trailkeeper.data.TokenStore
import com.asnidev.trailkeeper.ui.theme.TrailkeeperTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        TokenStore.init(applicationContext)
        Session.start()

        setContent {
            TrailkeeperTheme {
                TrailkeeperApp()
            }
        }
    }
}
