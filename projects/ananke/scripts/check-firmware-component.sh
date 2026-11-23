#!/bin/sh
# Offline component checks only. This does not link a device image or open USB.
set -eu
cd "$(dirname "$0")/.."
mkdir -p research/pi32v2-analysis
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  research/test_button_stream.c firmware/button_stream.c \
  -o research/pi32v2-analysis/test_button_stream
research/pi32v2-analysis/test_button_stream
sh scripts/pi32v2-tool.sh clang -target pi32v2 -mcpu=r3 -integrated-as -Os \
  -ffreestanding -fno-builtin -Wall -Wextra -Werror \
  -c firmware/button_stream.c -o research/pi32v2-analysis/button_stream.o
sh scripts/pi32v2-tool.sh objdump -section-headers -r research/pi32v2-analysis/button_stream.o
