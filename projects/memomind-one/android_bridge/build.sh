#!/bin/sh
set -eu
bridge_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bridge_sdk=${ANDROID_SDK_ROOT:-/Users/fosse/Library/Android/sdk}
bridge_jdk=${BRIDGE_JDK:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}
bridge_tools="$bridge_sdk/build-tools/36.0.0"
bridge_android="$bridge_sdk/platforms/android-36/android.jar"
bridge_build="$bridge_dir/build"
export JAVA_HOME="$bridge_jdk"
export PATH="$bridge_jdk/bin:$PATH"
mkdir -p "$bridge_build/classes" "$bridge_build/dex"
"$bridge_jdk/bin/javac" -source 8 -target 8 -Xlint:-options -encoding UTF-8 \
    -classpath "$bridge_android" -d "$bridge_build/classes" \
    "$bridge_dir/src/org/memomind/research/bridge/BridgeActivity.java"
"$bridge_jdk/bin/jar" cf "$bridge_build/classes.jar" -C "$bridge_build/classes" .
"$bridge_tools/d8" --min-api 31 --lib "$bridge_android" --output "$bridge_build/dex" "$bridge_build/classes.jar"
"$bridge_tools/aapt2" link --manifest "$bridge_dir/AndroidManifest.xml" \
    -I "$bridge_android" -o "$bridge_build/unsigned.apk"
(cd "$bridge_build/dex" && zip -q -j "$bridge_build/unsigned.apk" classes.dex)
"$bridge_tools/zipalign" -f 4 "$bridge_build/unsigned.apk" "$bridge_build/aligned.apk"
if [ ! -f "$bridge_dir/.debug.keystore" ]; then
    "$bridge_jdk/bin/keytool" -genkeypair -keystore "$bridge_dir/.debug.keystore" \
        -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 \
        -validity 10000 -dname 'CN=MemoMind Local Research,O=Local Development,C=US'
fi
"$bridge_tools/apksigner" sign --ks "$bridge_dir/.debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$bridge_build/memomind-bridge.apk" "$bridge_build/aligned.apk"
"$bridge_tools/apksigner" verify --verbose "$bridge_build/memomind-bridge.apk"
shasum -a 256 "$bridge_build/memomind-bridge.apk"
