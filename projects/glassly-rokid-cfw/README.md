# Glassly for Rokid

The glasses side of the Glassly launcher route for Rokid Glasses (RG, Android 12, 480×640 green
HUD). It is an ordinary Android app, `ai.glassly.rokid`, that is meant to become the glasses' home
screen and talks to the Glassly App over its own BLE service. Nothing on the glasses is reflashed.

The design and the link protocol live in the Glassly repo:
`notes/superpowers/specs/2026-11-15-rokid-glasses-glassly-launcher.md`.

This is phase 2: the link, text on the screen, and the touchpad. Scenes, mic, camera and the
flasher integration come later.

## Build

Needs the Android SDK (platform 36) and a JDK 17 or later; Android Studio's bundled one works.

```sh
echo "sdk.dir=$HOME/Library/Android/sdk" > local.properties
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew test assembleDebug
```

The debug APK is `app/build/outputs/apk/debug/app-debug.apk`.

## Install by hand

With USB debugging on for the glasses (Hi Rokid's developer settings) and the glasses visible to
`adb devices`:

```sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell pm grant ai.glassly.rokid android.permission.BLUETOOTH_ADVERTISE
adb shell pm grant ai.glassly.rokid android.permission.BLUETOOTH_CONNECT
adb shell pm grant ai.glassly.rokid android.permission.BLUETOOTH_SCAN
adb shell am start -n ai.glassly.rokid/.HomeActivity
```

The app then advertises its service and waits for the Glassly App. It keeps the Rokid launcher as
the home screen until phase 3. Making it the home app is
`adb shell cmd role add-role-holder android.app.role.HOME ai.glassly.rokid`, but do not run that on
the developer's glasses yet: the Rokid firmware reacts to a foreign home app by uninstalling its
assistant, and the assistant can lock adb when it comes back. Phase 3 works out what to disable
first, and how to undo it.

## Logs

Everything the app does is logged under one tag, including every key code the touchpad sends:

```sh
adb logcat -s GlasslyRokid
```

`tools/probe.sh` takes a read-only snapshot of the glasses' state (packages, home role, Bluetooth,
input devices, settings) into `probes/<timestamp>/`.

## Advertisement

The advertisement carries the service UUID. Android does not let an app set its own advertised
name, so the scan response carries the adapter's name (`Glasses_XXXX`, the stock one) and
manufacturer data under the test company ID `0xFFFF` holding `Glassly-XXXX`, where `XXXX` is the
same four characters. If the name does not fit, the app advertises without it and logs that.
