#!/bin/sh
# Task-local Ghidra installation and settings; no global Java or Ghidra setup.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export JAVA_HOME=/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
export XDG_CONFIG_HOME="$project_dir/.tools/ghidra/settings"
export XDG_CACHE_HOME="$project_dir/.tools/ghidra/cache"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
exec "$project_dir/.tools/ghidra/ghidra_12.2_PUBLIC/support/analyzeHeadless" "$@"
