package com.asnidev.trailkeeper.data

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.FileOutputStream

/**
 * Downscales a picked image to fit within 1500x2000 (portrait) / 2000x1500
 * (landscape), applies its EXIF rotation, and re-encodes as JPEG q78 to a
 * cache file for upload. Keeps task photos small on disk and over the wire.
 */
object ImageCompress {
    private const val LONG_EDGE = 2000
    private const val SHORT_EDGE = 1500
    private const val QUALITY = 78

    fun compressForUpload(context: Context, uri: Uri): File {
        val cr = context.contentResolver

        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        cr.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, bounds) }
        val srcW = bounds.outWidth.coerceAtLeast(1)
        val srcH = bounds.outHeight.coerceAtLeast(1)

        val maxLong = LONG_EDGE
        val maxShort = SHORT_EDGE
        // Decode at ~2x the needed size, then exact-scale below.
        var sample = 1
        while (
            srcW / (sample * 2) >= maxLong * 2 || srcH / (sample * 2) >= maxLong * 2
        ) sample *= 2

        val decoded =
            cr.openInputStream(uri)?.use {
                BitmapFactory.decodeStream(
                    it,
                    null,
                    BitmapFactory.Options().apply { inSampleSize = sample },
                )
            } ?: error("Could not read the image")

        val rotated = applyExifRotation(context, uri, decoded)

        val w = rotated.width
        val h = rotated.height
        val portrait = h >= w
        val boxW = if (portrait) maxShort else maxLong
        val boxH = if (portrait) maxLong else maxShort
        val scale = minOf(boxW.toFloat() / w, boxH.toFloat() / h, 1f)
        val finalBmp =
            if (scale < 1f) {
                Bitmap.createScaledBitmap(
                    rotated,
                    (w * scale).toInt().coerceAtLeast(1),
                    (h * scale).toInt().coerceAtLeast(1),
                    true,
                )
            } else {
                rotated
            }

        val out = File(context.cacheDir, "tk_upload_${System.currentTimeMillis()}.jpg")
        FileOutputStream(out).use { finalBmp.compress(Bitmap.CompressFormat.JPEG, QUALITY, it) }
        if (finalBmp !== rotated) finalBmp.recycle()
        if (rotated !== decoded) rotated.recycle()
        decoded.recycle()
        return out
    }

    private fun applyExifRotation(context: Context, uri: Uri, bmp: Bitmap): Bitmap {
        val orientation =
            runCatching {
                context.contentResolver.openInputStream(uri)?.use { ExifInterface(it) }
            }.getOrNull()?.getAttributeInt(
                ExifInterface.TAG_ORIENTATION,
                ExifInterface.ORIENTATION_NORMAL,
            ) ?: ExifInterface.ORIENTATION_NORMAL

        val m = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> m.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> m.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> m.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> m.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> m.postScale(1f, -1f)
            else -> return bmp
        }
        return Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
    }
}
