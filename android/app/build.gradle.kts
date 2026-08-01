plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.deadrator.atmosconverter"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.deadrator.atmosconverter"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
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
    }
    packaging {
        jniLibs {
            // FFmpegKit's 16KB-page-aligned .so libraries must NOT be compressed
            // (Android 15/16 require uncompressed native libs for 16KB pages).
            useLegacyPackaging = false
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.kotlinx.coroutines.android)
    // Maintained FFmpeg fork (com.arthenica API drop-in), full variant includes
    // libmysofa (sofalizer), libswresample, all audio codecs.
    implementation(libs.ffmpeg.kit)
    // The fork's POM declares no transitive dependencies; FFmpegKitConfig needs
    // smart-exception-java at runtime (NoClassDefFoundError without it).
    implementation(libs.arthenica.smart.exception)

    debugImplementation(libs.androidx.ui.tooling)
}
