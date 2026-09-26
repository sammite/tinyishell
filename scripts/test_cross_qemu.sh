#!/usr/bin/env bash
#
# scripts/test_cross_qemu.sh
# Cross-compile test_pel_unit for ARM, ARM64, MIPS, and MIPSEL,
# then execute under QEMU user-space emulation.
#
set -euo pipefail

TOOLCHAIN_DIR="${TOOLCHAIN_DIR:-.toolchains}"
ARM_GCC="${ARM_GCC:-${TOOLCHAIN_DIR}/arm-linux-musleabi-cross/bin/arm-linux-musleabi-gcc}"
ARM64_GCC="${ARM64_GCC:-${TOOLCHAIN_DIR}/aarch64-linux-musl-cross/bin/aarch64-linux-musl-gcc}"
MIPS_GCC="${MIPS_GCC:-${TOOLCHAIN_DIR}/mips-linux-musl-cross/bin/mips-linux-musl-gcc}"
MIPSEL_GCC="${MIPSEL_GCC:-${TOOLCHAIN_DIR}/mipsel-linux-musl-cross/bin/mipsel-linux-musl-gcc}"

CFLAGS="-O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer -static -I."
SRC="test/test_pel_unit.c pel.c monocypher.c monocypher-ed25519.c"

echo "=== 1. Cross-compiling test_pel_unit for all targets ==="
echo "[*] Building ARM (armv5te/v7)..."
"$ARM_GCC" $CFLAGS $SRC -o test/test_pel_unit_arm

echo "[*] Building ARM64 (aarch64)..."
"$ARM64_GCC" $CFLAGS $SRC -o test/test_pel_unit_arm64

echo "[*] Building MIPS (Big-Endian)..."
"$MIPS_GCC" $CFLAGS $SRC -o test/test_pel_unit_mips

echo "[*] Building MIPSEL (Little-Endian)..."
"$MIPSEL_GCC" $CFLAGS $SRC -o test/test_pel_unit_mipsel

echo "=== 2. Running test_pel_unit across architectures via QEMU ==="

RUN_CMD='apk update -q && apk add -q qemu-arm qemu-aarch64 qemu-mips qemu-mipsel && \
echo "--- Testing ARM32 (qemu-arm) ---" && \
qemu-arm ./test/test_pel_unit_arm && \
echo "--- Testing ARM64 (qemu-aarch64) ---" && \
qemu-aarch64 ./test/test_pel_unit_arm64 && \
echo "--- Testing MIPS Big-Endian (qemu-mips) ---" && \
qemu-mips ./test/test_pel_unit_mips && \
echo "--- Testing MIPSEL Little-Endian (qemu-mipsel) ---" && \
qemu-mipsel ./test/test_pel_unit_mipsel && \
echo "=== All architecture unit tests passed under QEMU emulation ==="'

docker run --rm -v "$(pwd):/work" -w /work alpine sh -c "$RUN_CMD"

# Cleanup test binaries
rm -f test/test_pel_unit_arm test/test_pel_unit_arm64 test/test_pel_unit_mips test/test_pel_unit_mipsel
echo "[+] Cleanup complete."
