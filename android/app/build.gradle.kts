import org.gradle.api.tasks.Sync

plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "io.github.gr33nops.sonkip"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.gr33nops.sonkip"
        minSdk = 24
        targetSdk = 35
        versionCode = 2
        versionName = "1.1.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

val generatedPython = layout.buildDirectory.dir("generated/sonkipPython")
val syncSonkipPython by tasks.registering(Sync::class) {
    from("../../app") {
        into("app")
    }
    from("../../static") {
        into("app/static")
    }
    into(generatedPython)
}

chaquopy {
    defaultConfig {
        version = "3.10"
        pip {
            install("yt-dlp>=2025.11.12")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir(generatedPython)
        }
    }
}

tasks.named("preBuild").configure {
    dependsOn(syncSonkipPython)
}

tasks.matching {
    it.name.startsWith("merge") && it.name.endsWith("PythonSources")
}.configureEach {
    dependsOn(syncSonkipPython)
}
