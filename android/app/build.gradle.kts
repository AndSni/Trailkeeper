import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

val keystoreProperties = Properties().apply {
    val file = rootProject.file("keystore.properties")
    if (file.exists()) {
        file.inputStream().use { load(it) }
    }
}

android {
    namespace = "com.asnidev.trailkeeper"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.asnidev.trailkeeper"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        // The backend is reached three ways, tried in this order by
        // network/ApiClient.kt's reachability probe (same pattern as
        // SharpRight):
        //  - EXTERNAL_API_BASE_URL: the always-on server via its Cloudflare
        //    Tunnel, reachable from anywhere. (Subdomain still TBD - see
        //    docs/BLUEPRINT.md sec 14.)
        //  - LAN_API_BASE_URL: the server's wifi-LAN address, device on the
        //    same network.
        //  - API_BASE_URL: local dev loop, `adb reverse tcp:9110 tcp:9110`
        //    against a backend run on this machine.
        // Port 9110 must match deploy/trailkeeper-api.service and the
        // cloudflared ingress - see deploy/README.md.
        buildConfigField("String", "EXTERNAL_API_BASE_URL", "\"https://trailkeeper.asnidev.com/\"")
        buildConfigField("String", "LAN_API_BASE_URL", "\"http://192.168.50.27:9110/\"")
        buildConfigField("String", "API_BASE_URL", "\"http://127.0.0.1:9110/\"")
    }

    signingConfigs {
        create("release") {
            if (keystoreProperties.isNotEmpty()) {
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.fragment:fragment-ktx:1.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // Room - the local sync cache (server is the source of truth; the DB is
    // rebuildable, so destructive migration is fine, see TrailkeeperDb).
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    ksp("androidx.room:room-compiler:2.6.1")

    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // MapLibre Native - vector map, trail/task overlays, the GPS puck.
    // Base style is OpenFreeMap's free hosted "liberty" for now; a
    // self-hosted .pmtiles for offline use is a later slice (BLUEPRINT sec 9).
    implementation("org.maplibre.gl:android-sdk:11.5.2")
    implementation("com.google.android.gms:play-services-location:21.3.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
