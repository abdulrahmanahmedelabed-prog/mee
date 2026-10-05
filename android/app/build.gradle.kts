plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.shopaccounting.pos"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.shopaccounting.pos"
        minSdk = 26   // أندرويد 8 فأحدث
        targetSdk = 34
        versionCode = 13
        versionName = "10.1"
    }

    // توقيع نسخة المتجر (Google Play): تُقرأ من متغيرات البيئة/أسرار GitHub إن وُجدت
    signingConfigs {
        create("release") {
            val ks = System.getenv("ANDROID_KEYSTORE_FILE")
            if (ks != null && file(ks).exists()) {
                storeFile = file(ks)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            val ks = System.getenv("ANDROID_KEYSTORE_FILE")
            if (ks != null && file(ks).exists()) signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // ماسح الباركود من Google: لا يحتاج صلاحية الكاميرا، والواجهة جاهزة
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
}
