import org.gradle.api.tasks.Sync

plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "io.github.gr33nops.sonkip"
    compileSdk = 35

    packaging {
        jniLibs.useLegacyPackaging = true
        jniLibs.keepDebugSymbols += "**/libqjs.so"
    }
    sourceSets.getByName("main") {
        jniLibs.srcDir(layout.buildDirectory.dir("generated/runtime"))
        assets.srcDir(layout.buildDirectory.dir("generated/runtimeLicenses"))
    }

    defaultConfig {
        applicationId = "io.github.gr33nops.sonkip"
        minSdk = 24
        targetSdk = 35
        versionCode = 12
        versionName = "2.2.0"

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
    testOptions {
        unitTests.isIncludeAndroidResources = true
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.17")
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
        System.getenv("SONKIP_BUILD_PYTHON")?.let { buildPython(it) }
        pip {
            install("yt-dlp==2026.8.19")
            install("yt-dlp-ejs==0.8.0")
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
    doFirst {
        for (abi in listOf("arm64-v8a", "armeabi-v7a")) {
            check(layout.buildDirectory.file("generated/runtime/$abi/libqjs.so").get().asFile.isFile) {
                "Missing QuickJS runtime. Run python android/build_runtime.py from the repository root first."
            }
        }
    }
}

tasks.matching {
    it.name.startsWith("merge") && it.name.endsWith("PythonSources")
}.configureEach {
    dependsOn(syncSonkipPython)
}
