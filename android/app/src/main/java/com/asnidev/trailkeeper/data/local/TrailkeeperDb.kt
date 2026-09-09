package com.asnidev.trailkeeper.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(
    entities = [
        ProjectEntity::class,
        TrailEntity::class,
        TaskEntity::class,
        WorkLogEntity::class,
        ProjectMemberEntity::class,
        SyncStateEntity::class,
        ProjectSyncEntity::class,
        OutboxEntity::class,
        MessageEntity::class,
        NotificationEntity::class,
        JobTypeEntity::class,
        SegmentWorkEntity::class,
        StructureEntity::class,
        InspectionFormEntity::class,
        InspectionEntity::class,
        TrackEntity::class,
    ],
    version = 7,
    exportSchema = false,
)
abstract class TrailkeeperDb : RoomDatabase() {
    abstract fun projectDao(): ProjectDao
    abstract fun trailDao(): TrailDao
    abstract fun taskDao(): TaskDao
    abstract fun workLogDao(): WorkLogDao
    abstract fun projectMemberDao(): ProjectMemberDao
    abstract fun syncStateDao(): SyncStateDao
    abstract fun outboxDao(): OutboxDao
    abstract fun messageDao(): MessageDao
    abstract fun notificationDao(): NotificationDao
    abstract fun jobTypeDao(): JobTypeDao
    abstract fun segmentWorkDao(): SegmentWorkDao
    abstract fun structureDao(): StructureDao
    abstract fun inspectionFormDao(): InspectionFormDao
    abstract fun inspectionDao(): InspectionDao
    abstract fun trackDao(): TrackDao

    companion object {
        @Volatile private var built: TrailkeeperDb? = null

        /** Call once from MainActivity with the application context. */
        fun init(context: Context) {
            get(context)
        }

        /** The singleton, after [init]. */
        val db: TrailkeeperDb
            get() = built ?: error("TrailkeeperDb.init() was not called")

        fun get(context: Context): TrailkeeperDb =
            built
                ?: synchronized(this) {
                    built
                        ?: Room.databaseBuilder(
                                context.applicationContext,
                                TrailkeeperDb::class.java,
                                "trailkeeper.db",
                            )
                            // The DB is a sync cache - anything lost is
                            // re-fetched from the server on next open.
                            .fallbackToDestructiveMigration()
                            .build()
                            .also { built = it }
                }
    }
}
