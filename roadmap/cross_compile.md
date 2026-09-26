# Roadmap: Cross-Compilation for Embedded ARM & MIPS Targets

This roadmap documents the cross-compilation pipeline for building static, minimal-dependency `tsh` and `tshd` binaries targeting resource-constrained embedded devices.

## 1. Supported Architectures

| Architecture | Target Triple | Endianness | ABI / Profile | Common Real-World Targets |
| :--- | :--- | :--- | :--- | :--- |
| **ARM32** | `arm-linux-musleabi` | Little-Endian | 32-bit EABI (ARMv5te / ARMv7-A) | Embedded IoT, IP cameras, Raspberry Pi (32-bit) |
| **ARM64** | `aarch64-linux-musl` | Little-Endian | 64-bit LP64 (ARMv8-A) | SBCs, modern ARM gateways, OpenWrt 64-bit |
| **MIPS32 (BE)** | `mips-linux-musl` | **Big-Endian** | 32-bit o32 (MIPS-I / MIPS32r2) | Atheros/Qualcomm Wi-Fi routers (TP-Link, OpenWrt) |
| **MIPS32 (LE)** | `mipsel-linux-musl` | **Little-Endian** | 32-bit o32 (MIPS-I / MIPS32r2) | MediaTek MT7620/MT7628/MT7688, RT5350 routers |

All binaries are statically linked against `musl libc` (`-static`) with garbage collection of unused sections (`-ffunction-sections -fdata-sections -Wl,--gc-sections -flto`), eliminating external shared library dependencies on target filesystems.

---

## 2. Binary Footprint Benchmarks

Static musl build size comparison across architectures:

| Target | `tsh` (Client) | `tshd` (Daemon) | Target Footprint |
| :--- | :--- | :--- | :--- |
| **x86_64** (Host) | 91.8 KB | 50.3 KB | Standard x86_64 Linux |
| **ARM64** (`aarch64-linux-musl`) | 90.1 KB (92,264 B) | **45.6 KB (46,720 B)** | 64-bit embedded Linux |
| **ARM32** (`arm-linux-musleabi`) | 105.5 KB (108,120 B) | **65.2 KB (66,808 B)** | Universal 32-bit ARM Linux |
| **MIPS32 BE** (`mips-linux-musl`) | 142.5 KB (145,964 B) | **91.3 KB (93,568 B)** | Big-Endian OpenWrt routers |
| **MIPS32 LE** (`mipsel-linux-musl`) | 142.5 KB (145,964 B) | **91.3 KB (93,520 B)** | Little-Endian MediaTek routers |

---

## 3. Architecture-Specific Implementation Details

### 3.1 Strict Memory Alignment (`tshd.c`)
On architectures with strict alignment requirements (such as MIPS and older ARM cores), unaligned 64-bit loads trigger a `SIGBUS` hardware trap.
In `tshd_ls_dir()`, the raw `SYS_getdents64` buffer is declared with explicit 8-byte alignment:
```c
char getdents_buf[1024] __attribute__( ( aligned( 8 ) ) );
```
This guarantees that casting offsets into `struct linux_dirent64 *` does not cause alignment violations on 32-bit architectures.

### 3.2 Endian-Neutral Wire Protocol (`pel.c`)
The PEL transport protocol handles framing length prefixes and 64-bit replay protection sequence numbers using explicit bit shifts (big-endian wire format). Monocypher operates endian-independently. Big-Endian MIPS (`mips-linux-musl`) and Little-Endian (`arm`, `mipsel`, `x86_64`) communicate seamlessly across network boundaries without translation layers.

### 3.3 Foreign ELF Stripping
Host `strip` cannot parse foreign ELF targets. The build system invokes `$(STRIP)` derived from the target cross-prefix (`$(CROSS_COMPILE)strip`).

---

## 4. Usage Guide

### 4.1 Toolchain Acquisition
To download standalone musl cross toolchains into `.toolchains/` without requiring root permissions:
```bash
# Fetch all target toolchains (ARM, ARM64, MIPS, MIPSEL)
./scripts/fetch_toolchains.sh all

# Or fetch an individual target:
./scripts/fetch_toolchains.sh arm
./scripts/fetch_toolchains.sh mips
```

### 4.2 Building Binaries

Build specific architecture targets directly:
```bash
make linux_arm_musl     # Builds ARM32 binaries (tsh, tshd)
make linux_arm64_musl   # Builds ARM64 binaries (tsh, tshd)
make linux_mips_musl    # Builds MIPS Big-Endian binaries (tsh, tshd)
make linux_mipsel_musl  # Builds MIPS Little-Endian binaries (tsh, tshd)
```

Build and organize all architectures into `dist/<arch>/`:
```bash
make cross_all
```

Custom toolchain paths can be passed using standard environment overrides:
```bash
make ARM_CROSS=/custom/toolchain/bin/arm-linux-musleabi- linux_arm_musl
```

### 4.3 Automated Cross-Architecture Testing (QEMU User Emulation)
Run the PEL cryptographic unit test suite across all 4 target architectures under QEMU user space emulation:
```bash
make test_cross_qemu
```

---

## 5. Verification Checklist

- [x] Alignment-safe directory reading on MIPS/ARM (`__attribute__((aligned(8)))`).
- [x] Endianness compatibility verified on Big-Endian MIPS under `qemu-mips`.
- [x] Pure static linking against `musl libc` verified with `file` and `ldd`.
- [x] Automated QEMU user space unit tests passing for `arm`, `aarch64`, `mips`, `mipsel`.
- [x] All 41 integration tests passing cleanly without regressions.
