package com.asnidev.trailkeeper.record

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.asnidev.trailkeeper.MainActivity
import com.asnidev.trailkeeper.R
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

/**
 * Foreground service that keeps GPS running while a route is being recorded,
 * even with the app backgrounded. It owns the fused-location client and the
 * ongoing notification; all recording state lives in [TrackRecorder].
 */
class TrackRecordingService : Service() {
    private val fused by lazy { LocationServices.getFusedLocationProviderClient(this) }
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var notifJob: Job? = null

    private val callback =
        object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val loc = result.lastLocation ?: return
                TrackRecorder.onLocation(
                    loc.latitude,
                    loc.longitude,
                    if (loc.hasAltitude()) loc.altitude else null,
                    if (loc.hasAccuracy()) loc.accuracy else 999f,
                )
            }
        }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                val projectId = intent.getStringExtra(EXTRA_PROJECT_ID) ?: return START_NOT_STICKY
                if (!TrackRecorder.isActive) TrackRecorder.start(projectId)
                startForegroundWithNotification()
                requestUpdates()
                observeForNotificationUpdates()
            }
            ACTION_PAUSE -> {
                TrackRecorder.pause()
                updateNotification()
            }
            ACTION_RESUME -> {
                TrackRecorder.resume()
                updateNotification()
            }
            ACTION_STOP -> {
                TrackRecorder.stop()
                stopEverything()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopUpdates()
        notifJob?.cancel()
        scope.coroutineContext[Job]?.cancel()
        super.onDestroy()
    }

    // --- location --------------------------------------------------------

    @SuppressLint("MissingPermission")
    private fun requestUpdates() {
        val request =
            LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 3_000L)
                .setMinUpdateIntervalMillis(2_000L)
                .setMinUpdateDistanceMeters(2f)
                .build()
        fused.requestLocationUpdates(request, callback, Looper.getMainLooper())
    }

    private fun stopUpdates() {
        runCatching { fused.removeLocationUpdates(callback) }
    }

    private fun stopEverything() {
        stopUpdates()
        notifJob?.cancel()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    // --- notification ---------------------------------------------------

    private fun observeForNotificationUpdates() {
        notifJob?.cancel()
        notifJob =
            scope.launch {
                TrackRecorder.state.collectLatest { updateNotification() }
            }
    }

    private fun startForegroundWithNotification() {
        ensureChannel()
        val type =
            if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION else 0
        ServiceCompat.startForeground(this, NOTIF_ID, buildNotification(), type)
    }

    private fun updateNotification() {
        NotificationManagerCompat.from(this).notify(NOTIF_ID, buildNotification())
    }

    private fun ensureChannel() {
        val channel =
            NotificationChannelCompat.Builder(CHANNEL_ID, NotificationManager.IMPORTANCE_LOW)
                .setName("Route recording")
                .setDescription("Ongoing while a route is being recorded")
                .build()
        NotificationManagerCompat.from(this).createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        val s = TrackRecorder.state.value
        val paused = s.phase == RecPhase.PAUSED
        val km = s.distanceM / 1000.0
        val mins = s.movingMillis / 60_000
        val text =
            "%s · %.2f km · %d min · %d pts".format(
                if (paused) "Paused" else "Recording",
                km,
                mins,
                s.pointCount,
            )

        val open =
            PendingIntent.getActivity(
                this,
                0,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
        val builder =
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Trailkeeper — route")
                .setContentText(text)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(open)

        if (paused) {
            builder.addAction(0, "Resume", action(ACTION_RESUME))
        } else {
            builder.addAction(0, "Pause", action(ACTION_PAUSE))
        }
        builder.addAction(0, "Stop", action(ACTION_STOP))
        return builder.build()
    }

    private fun action(a: String): PendingIntent =
        PendingIntent.getService(
            this,
            a.hashCode(),
            Intent(this, TrackRecordingService::class.java).setAction(a),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

    companion object {
        private const val CHANNEL_ID = "track_recording"
        private const val NOTIF_ID = 4201
        const val ACTION_START = "com.asnidev.trailkeeper.record.START"
        const val ACTION_PAUSE = "com.asnidev.trailkeeper.record.PAUSE"
        const val ACTION_RESUME = "com.asnidev.trailkeeper.record.RESUME"
        const val ACTION_STOP = "com.asnidev.trailkeeper.record.STOP"
        const val EXTRA_PROJECT_ID = "project_id"

        private fun send(context: Context, action: String, projectId: String? = null) {
            val intent =
                Intent(context, TrackRecordingService::class.java).setAction(action).apply {
                    if (projectId != null) putExtra(EXTRA_PROJECT_ID, projectId)
                }
            if (action == ACTION_START) ContextCompat.startForegroundService(context, intent)
            else context.startService(intent)
        }

        fun start(context: Context, projectId: String) = send(context, ACTION_START, projectId)

        fun pause(context: Context) = send(context, ACTION_PAUSE)

        fun resume(context: Context) = send(context, ACTION_RESUME)

        fun stop(context: Context) = send(context, ACTION_STOP)
    }
}
