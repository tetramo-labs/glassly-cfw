#!/bin/sh
# Offline only: no USB access, writer, or install command.
set -eu
cd "$(dirname "$0")/.."
sh scripts/check-firmware-component.sh
clang -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
  research/test_ananke_binding.c firmware/button_stream.c \
  -o research/pi32v2-analysis/test_ananke_binding
research/pi32v2-analysis/test_ananke_binding
sh scripts/pi32v2-tool.sh clang -target pi32v2 -mcpu=r3 -integrated-as -Os \
  -ffreestanding -fno-builtin -fno-common -Wall -Wextra -Werror \
  -c firmware/ananke_v0900.c -o research/pi32v2-analysis/ananke_v0900.o
sh scripts/pi32v2-tool.sh /opt/jieli/pi32v2/bin/ld \
  -T firmware/ananke_v0900.ld \
  research/pi32v2-analysis/ananke_v0900.o research/pi32v2-analysis/button_stream.o \
  -o research/pi32v2-analysis/ananke-cfw.elf
sh scripts/pi32v2-tool.sh objdump -disassemble -minstrev3 -address-mask=0x1ffffff \
  research/pi32v2-analysis/ananke-cfw.elf > research/pi32v2-analysis/ananke-cfw.asm
../gamebrick-mini/.venv/bin/python3 research/build_candidate.py
../gamebrick-mini/.venv/bin/python3 -m unittest discover -s research -p test_candidate.py
