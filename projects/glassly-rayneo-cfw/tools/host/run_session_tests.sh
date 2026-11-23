#!/bin/bash
# Host check of the phone session: link loss, the wake takeover, PAGE_OPEN renewal and the uplink ring (page.c, link.c).
set -e
cd "$(dirname "$0")/../.."
OUT=${OUT:-/tmp/rayneo-session-tests}
mkdir -p "$OUT"
clang -std=c11 -O1 -g -fsanitize=address,undefined -Wall -Wextra -Wno-unused-function -Wno-unused-parameter \
  -Ipatches -Ipatches/generated -o "$OUT/session_test" tools/host/session_test.c
"$OUT/session_test"
