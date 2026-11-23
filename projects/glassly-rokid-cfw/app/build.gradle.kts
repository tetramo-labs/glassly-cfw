plugins {
    id("com.android.application")
}

android {
    namespace = "ai.glassly.rokid"
    compileSdk = 36

    defaultConfig {
        applicationId = "ai.glassly.rokid"
        minSdk = 31
        // The Rokid firmware is tuned for apps at 34.
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0-dev"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    // android.jar's org.json is a stub on the JVM; the protocol tests need the real one.
    testImplementation("org.json:json:20260814")
}
