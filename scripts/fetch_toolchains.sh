#!/usr/bin/env bash
#
# scripts/fetch_toolchains.sh
# Download and unpack standalone musl-cross toolchains from musl.cc
#
set -euo pipefail

TOOLCHAIN_DIR="${TOOLCHAIN_DIR:-.toolchains}"
BASE_URL="https://musl.cc"

declare -A TOOLCHAINS=(
    ["arm"]="arm-linux-musleabi-cross"
    ["arm64"]="aarch64-linux-musl-cross"
    ["aarch64"]="aarch64-linux-musl-cross"
    ["mips"]="mips-linux-musl-cross"
    ["mipsel"]="mipsel-linux-musl-cross"
    ["riscv64"]="riscv64-linux-musl-cross"
    ["riscv32"]="riscv32-linux-musl-cross"
    ["powerpc"]="powerpc-linux-musl-cross"
    ["ppc"]="powerpc-linux-musl-cross"
    ["mips64"]="mips64-linux-musl-cross"
    ["mips64el"]="mips64el-linux-musl-cross"
)

usage() {
    echo "Usage: $0 [arm|arm64|mips|mipsel|riscv64|riscv32|powerpc|mips64|mips64el|all]"
    exit 1
}

fetch_target() {
    local target="$1"
    local archive_name="${TOOLCHAINS[$target]}"
    local dest_dir="${TOOLCHAIN_DIR}/${archive_name}"

    if [ -d "${dest_dir}/bin" ]; then
        echo "[+] Toolchain '${archive_name}' already exists in ${dest_dir}"
        return 0
    fi

    echo "[*] Downloading ${archive_name}.tgz from ${BASE_URL}..."
    mkdir -p "${TOOLCHAIN_DIR}"
    curl -fSL "${BASE_URL}/${archive_name}.tgz" | tar -xz -C "${TOOLCHAIN_DIR}"
    echo "[+] Unpacked ${archive_name} into ${TOOLCHAIN_DIR}/"
}

if [ $# -eq 0 ]; then
    usage
fi

TARGET="$1"

if [ "$TARGET" = "all" ]; then
    for t in arm arm64 mips mipsel riscv64 riscv32 powerpc mips64 mips64el; do
        fetch_target "$t"
    done
else
    if [ -z "${TOOLCHAINS[$TARGET]+x}" ]; then
        echo "Error: Unknown target '$TARGET'"
        usage
    fi
    fetch_target "$TARGET"
fi

echo "[+] Done. Toolchains available in: ${TOOLCHAIN_DIR}"
