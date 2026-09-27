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
RISCV64_GCC="${RISCV64_GCC:-${TOOLCHAIN_DIR}/riscv64-linux-musl-cross/bin/riscv64-linux-musl-gcc}"
RISCV32_GCC="${RISCV32_GCC:-${TOOLCHAIN_DIR}/riscv32-linux-musl-cross/bin/riscv32-linux-musl-gcc}"
POWERPC_GCC="${POWERPC_GCC:-${TOOLCHAIN_DIR}/powerpc-linux-musl-cross/bin/powerpc-linux-musl-gcc}"
MIPS64_GCC="${MIPS64_GCC:-${TOOLCHAIN_DIR}/mips64-linux-musl-cross/bin/mips64-linux-musl-gcc}"
MIPS64EL_GCC="${MIPS64EL_GCC:-${TOOLCHAIN_DIR}/mips64el-linux-musl-cross/bin/mips64el-linux-musl-gcc}"

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

echo "[*] Building RISC-V 64..."
"$RISCV64_GCC" $CFLAGS $SRC -o test/test_pel_unit_riscv64

echo "[*] Building RISC-V 32..."
"$RISCV32_GCC" $CFLAGS $SRC -o test/test_pel_unit_riscv32

echo "[*] Building PowerPC (Big-Endian)..."
"$POWERPC_GCC" $CFLAGS $SRC -o test/test_pel_unit_powerpc

echo "[*] Building MIPS64 (Big-Endian)..."
"$MIPS64_GCC" $CFLAGS $SRC -o test/test_pel_unit_mips64

echo "[*] Building MIPS64EL (Little-Endian)..."
"$MIPS64EL_GCC" $CFLAGS $SRC -o test/test_pel_unit_mips64el

echo "=== 2. Running test_pel_unit across architectures via QEMU ==="

RUN_CMD='apk update -q && apk add -q \
    qemu-arm qemu-aarch64 qemu-mips qemu-mipsel \
    qemu-riscv64 qemu-riscv32 qemu-ppc qemu-mips64 qemu-mips64el && \
echo "--- Testing ARM32 (qemu-arm) ---" && \
qemu-arm ./test/test_pel_unit_arm && \
echo "--- Testing ARM64 (qemu-aarch64) ---" && \
qemu-aarch64 ./test/test_pel_unit_arm64 && \
echo "--- Testing MIPS Big-Endian (qemu-mips) ---" && \
qemu-mips ./test/test_pel_unit_mips && \
echo "--- Testing MIPSEL Little-Endian (qemu-mipsel) ---" && \
qemu-mipsel ./test/test_pel_unit_mipsel && \
echo "--- Testing RISC-V 64 (qemu-riscv64) ---" && \
qemu-riscv64 ./test/test_pel_unit_riscv64 && \
echo "--- Testing RISC-V 32 (qemu-riscv32) ---" && \
qemu-riscv32 ./test/test_pel_unit_riscv32 && \
echo "--- Testing PowerPC (qemu-ppc) ---" && \
qemu-ppc ./test/test_pel_unit_powerpc && \
echo "--- Testing MIPS64 Big-Endian (qemu-mips64) ---" && \
qemu-mips64 ./test/test_pel_unit_mips64 && \
echo "--- Testing MIPS64EL Little-Endian (qemu-mips64el) ---" && \
qemu-mips64el ./test/test_pel_unit_mips64el && \
echo "=== All 9 architecture unit tests passed under QEMU emulation ==="'

docker run --rm -v "$(pwd):/work" -w /work alpine sh -c "$RUN_CMD"

# Cleanup test binaries
rm -f test/test_pel_unit_arm test/test_pel_unit_arm64 test/test_pel_unit_mips test/test_pel_unit_mipsel \
      test/test_pel_unit_riscv64 test/test_pel_unit_riscv32 test/test_pel_unit_powerpc \
      test/test_pel_unit_mips64 test/test_pel_unit_mips64el
echo "[+] Cleanup complete."
