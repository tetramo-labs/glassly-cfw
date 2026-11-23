#!/bin/sh
# Arm a double-click test on the glasses: starts the test-only live link, which keeps
# the glasses awake until the last step runs or 15 idle minutes pass, then exits.
# Usage: arm-test.sh STEPS.json
set -eu
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
live=${LIVE_DIR:-/tmp/memomind-live}; mkdir -p "$live"
pkill -f "memomind-live$" 2>/dev/null || true
: > "$live/in"
nohup "$dir/memomind-live" >> "$live/stdout.log" 2>&1 &
sleep 1
printf 'steps %s\n' "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")" >> "$live/in"
echo "armed: $1 (log $live/out.jsonl)"
