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
        versionCode = 14
        versionName = "10.2"
    }

    // توقيع نسخة المتجر (Google Play): تُقرأ من متغيرات البيئة/أسرار GitHub إن وُجدت
    signingConfigs {
        // مفتاح توقيع ثابت لملف APK الذي يُنزَّل من صفحة الإصدارات (من أسرار GitHub، لا يُحفظ في المستودع):
        // كل تحديث يُثبَّت فوق السابق مباشرة، ولا يستطيع غيرك نشر «تحديث» مزيّف باسم التطبيق.
        // بدون السر يُستخدم مفتاح التطوير العادي (للتجربة فقط).
        getByName("debug") {
            val ks = System.getenv("ANDROID_KEYSTORE_FILE")
            if (ks != null && file(ks).exists()) {
                storeFile = file(ks)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "shoppos"
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD") ?: System.getenv("ANDROID_KEYSTORE_PASSWORD")
            }
        }
        create("release") {
            val ks = System.getenv("ANDROID_KEYSTORE_FILE")
            if (ks != null && file(ks).exists()) {
                storeFile = file(ks)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "shoppos"
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD") ?: System.getenv("ANDROID_KEYSTORE_PASSWORD")
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
    // تنزيل وحدة الماسح مسبقاً عند أول تشغيل (فلا ينتظر المستخدم عند أول مسح)
    implementation("com.google.android.gms:play-services-base:18.5.0")
}
