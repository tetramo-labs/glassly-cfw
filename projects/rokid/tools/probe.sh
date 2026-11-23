#!/usr/bin/env bash
# Read-only snapshot of Rokid Glasses state for the Glassly launcher route.
# Usage: tools/probe.sh [adb serial]   Writes probes/<timestamp>/ next to this script.
set -uo pipefail

serial="${1:-}"
adb_cmd=(adb)
[[ -n "$serial" ]] && adb_cmd=(adb -s "$serial")
out="$(cd "$(dirname "$0")/.." && pwd)/probes/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"

run() {
  local name="$1"; shift
  { echo "\$ $*"; "${adb_cmd[@]}" shell "$@" 2>&1; echo "[exit $?]"; } > "$out/$name.txt"
}

adb devices -l > "$out/devices.txt" 2>&1
"${adb_cmd[@]}" get-state > /dev/null 2>&1 || { echo "No glasses reachable over adb; see $out/devices.txt"; exit 1; }

run props            getprop
run whoami           id
run packages-system  pm list packages -s -f
run packages-user    pm list packages -3 -f
run packages-disabled pm list packages -d
run home-role        cmd role get-role-holders android.app.role.HOME
run home-resolve     cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
run home-candidates  cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME
run activities       dumpsys activity activities
run services-running dumpsys activity services
run bluetooth        dumpsys bluetooth_manager
run input            dumpsys input
run display          dumpsys display
run wm               sh -c 'wm size; wm density'
run camera           dumpsys media.camera
run audio            dumpsys audio
run power            dumpsys power
run deviceidle       dumpsys deviceidle
run battery          dumpsys battery
run settings-global  settings list global
run settings-secure  settings list secure
run settings-system  settings list system
run accessibility    dumpsys accessibility
run getevent         getevent -lp

for pkg in $("${adb_cmd[@]}" shell pm list packages 2>/dev/null | tr -d '\r' | sed 's/^package://' | grep -iE 'rokid|sprite|yoda|launcher'); do
  run "pkg-$pkg" dumpsys package "$pkg"
done

echo "Wrote $out"
