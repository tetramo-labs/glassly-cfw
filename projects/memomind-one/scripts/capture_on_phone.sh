#!/system/bin/sh
BASE=/data/local/tmp/memomind-20261030-2011
APP=/data/user/0/com.memomind.ai.aphrodite
mkdir -p "$BASE/app" "$BASE/external" "$BASE/hci" "$BASE/apk"
chmod 700 "$BASE"
date -u > "$BASE/started.txt"
pm path com.memomind.ai.aphrodite | while IFS= read -r p; do cp "${p#package:}" "$BASE/apk/"; done
logcat -v epoch --pid=10407 -f "$BASE/app-logcat.txt" &
LOGPID=$!
tcpdump -i any -s 0 -U -w "$BASE/network.pcap" 2>"$BASE/tcpdump.log" &
NETPID=$!
trap 'kill "$LOGPID" "$NETPID" 2>/dev/null; wait; date -u > "$BASE/stopped.txt"' EXIT
trap 'exit' INT TERM
n=0
while [ "$n" -lt 1800 ] && [ ! -e "$BASE/STOP" ]; do
  for folder in cache files app_flutter; do cp -a "$APP/$folder" "$BASE/app/" 2>>"$BASE/copy-errors.txt"; done
  cp -a /sdcard/Android/data/com.memomind.ai.aphrodite "$BASE/external/" 2>>"$BASE/copy-errors.txt"
  for f in /data/misc/bluetooth/logs/btsnoop*; do
    [ -f "$f" ] || continue
    cp "$f" "$BASE/hci/$n-${f##*/}"
  done
  n=$((n+1))
  sleep 1
done
