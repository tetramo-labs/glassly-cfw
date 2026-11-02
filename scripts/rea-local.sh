#!/bin/sh
# Use the verified task-local runtime and JADX provider, without global setup.
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
node_bin="$project_dir/.tools/rea-runtime/node-v24.22.1-darwin-arm64/bin"
rea_dir="${REA_CHECKOUT:-/Users/fosse/dev/rea}"
export PATH="$node_bin:$PATH"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}"
export REA_JADX_MCP_JAR="${REA_JADX_MCP_JAR:-$project_dir/.tools/rea-jadx/jadx-headless-mcp-0.7.1-all.jar}"
exec "$node_bin/node" "$rea_dir/scripts/rea.mjs" "$@"
