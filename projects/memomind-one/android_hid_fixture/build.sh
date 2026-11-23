#!/bin/sh
set -eu
hid_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
hid_sdk=${ANDROID_SDK_ROOT:-/Users/fosse/Library/Android/sdk}
hid_jdk=${HID_JDK:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}
hid_tools="$hid_sdk/build-tools/36.0.0"
hid_android="$hid_sdk/platforms/android-36/android.jar"
hid_build="$hid_dir/build"
export JAVA_HOME="$hid_jdk"
export PATH="$hid_jdk/bin:$PATH"
rm -rf "$hid_build/classes" "$hid_build/dex"
mkdir -p "$hid_build/classes" "$hid_build/dex"
"$hid_jdk/bin/javac" -source 8 -target 8 -Xlint:-options -encoding UTF-8 \
    -classpath "$hid_android" -d "$hid_build/classes" \
    "$hid_dir/src/org/memomind/research/hid/"*.java
"$hid_jdk/bin/jar" cf "$hid_build/classes.jar" -C "$hid_build/classes" .
"$hid_tools/d8" --min-api 33 --lib "$hid_android" --output "$hid_build/dex" "$hid_build/classes.jar"
"$hid_tools/aapt2" link --manifest "$hid_dir/AndroidManifest.xml" \
    -I "$hid_android" -o "$hid_build/unsigned.apk"
(cd "$hid_build/dex" && zip -q -j "$hid_build/unsigned.apk" classes.dex)
"$hid_tools/zipalign" -f 4 "$hid_build/unsigned.apk" "$hid_build/aligned.apk"
if [ ! -f "$hid_dir/.debug.keystore" ]; then
    "$hid_jdk/bin/keytool" -genkeypair -keystore "$hid_dir/.debug.keystore" \
        -storepass android -keypass android -alias androiddebugkey -keyalg RSA -keysize 2048 \
        -validity 10000 -dname 'CN=MemoMind Local Research,O=Local Development,C=US'
fi
"$hid_tools/apksigner" sign --ks "$hid_dir/.debug.keystore" --ks-pass pass:android \
    --key-pass pass:android --out "$hid_build/memomind-hid-fixture.apk" "$hid_build/aligned.apk"
"$hid_tools/apksigner" verify --verbose "$hid_build/memomind-hid-fixture.apk"
shasum -a 256 "$hid_build/memomind-hid-fixture.apk"
