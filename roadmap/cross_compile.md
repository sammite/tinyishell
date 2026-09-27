# Roadmap: Cross-Compilation for Embedded Architectures

This roadmap documents the cross-compilation pipeline for building static, minimal-dependency `tsh` and `tshd` binaries targeting resource-constrained embedded systems and networking equipment.

## 1. Supported Architectures (9 Targets)

| Architecture | Target Triple | Endianness | ABI / Profile | Common Real-World Targets |
| :--- | :--- | :--- | :--- | :--- |
| **ARM64** | `aarch64-linux-musl` | Little-Endian | 64-bit LP64 (ARMv8-A) | Modern SBCs, 64-bit ARM gateways, OpenWrt |
| **ARM32** | `arm-linux-musleabi` | Little-Endian | 32-bit EABI (ARMv5te / ARMv7-A) | Embedded IoT, IP cameras, Raspberry Pi (32-bit) |
| **RISC-V 64** | `riscv64-linux-musl` | Little-Endian | 64-bit LP64D (RVC) | Milk-V Duo, StarFive VisionFive 2, Allwinner D1 |
| **RISC-V 32** | `riscv32-linux-musl` | Little-Endian | 32-bit ILP32D (RVC) | Kendryte, low-cost micro-Linux SBCs |
| **PowerPC 32** | `powerpc-linux-musl` | **Big-Endian** | 32-bit PPC (e500/e300) | Industrial PLCs, SCADA, NXP/Freescale PowerQUICC |
| **MIPS32 (BE)** | `mips-linux-musl` | **Big-Endian** | 32-bit o32 (MIPS-I / MIPS32r2) | Atheros/Qualcomm Wi-Fi routers (TP-Link, OpenWrt) |
| **MIPS32 (LE)** | `mipsel-linux-musl` | **Little-Endian** | 32-bit o32 (MIPS-I / MIPS32r2) | MediaTek MT7620/MT7628/MT7688, RT5350 routers |
| **MIPS64 (BE)** | `mips64-linux-musl` | **Big-Endian** | 64-bit N64 (MIPS-III) | Cavium Octeon routers, Ubiquiti EdgeRouter PRO |
| **MIPS64 (LE)** | `mips64el-linux-musl` | **Little-Endian** | 64-bit N64 (MIPS-III) | Loongson, Cavium Octeon (LE mode) appliances |

All binaries are statically linked against `musl libc` (`-static`) with dead-code and unused section stripping (`-ffunction-sections -fdata-sections -Wl,--gc-sections -flto`), eliminating external shared library dependencies on target filesystems.

---

## 2. Binary Footprint Benchmarks

Static musl build size comparison across all 9 target architectures:

| Target Architecture | `tsh` (Client) | `tshd` (Daemon) | Relative Footprint |
| :--- | :--- | :--- | :--- |
| **ARM64** (`aarch64-linux-musl`) | 91 KB | **46 KB** | Minimal 64-bit profile |
| **RISC-V 64** (`riscv64-linux-musl`) | 79 KB | **42 KB** | Smallest 64-bit footprint |
| **RISC-V 32** (`riscv32-linux-musl`) | 106 KB | **58 KB** | Compact 32-bit profile |
| **ARM32** (`arm-linux-musleabi`) | 106 KB | **66 KB** | Universal 32-bit ARM Linux |
| **PowerPC 32** (`powerpc-linux-musl`) | 130 KB | **75 KB** | Big-Endian industrial profile |
| **MIPS64 BE** (`mips64-linux-musl`) | 130 KB | **68 KB** | High-throughput enterprise profile |
| **MIPS64 LE** (`mips64el-linux-musl`) | 130 KB | **68 KB** | High-throughput enterprise profile |
| **MIPS32 BE** (`mips-linux-musl`) | 143 KB | **92 KB** | Standard OpenWrt router profile |
| **MIPS32 LE** (`mipsel-linux-musl`) | 143 KB | **92 KB** | Standard MediaTek router profile |
| **x86_64** (Host) | 92 KB | **50 KB** | Standard x86_64 Linux |

---

## 3. Architecture-Specific Implementation Details

### 3.1 Strict Memory Alignment (`tshd.c`)
On architectures with strict alignment requirements (such as MIPS, PowerPC, and older ARM cores), unaligned 64-bit loads trigger hardware `SIGBUS` faults.
In `tshd_ls_dir()`, the raw `SYS_getdents64` buffer is declared with explicit 8-byte alignment:
```c
char getdents_buf[1024] __attribute__( ( aligned( 8 ) ) );
```
This guarantees that casting offsets into `struct linux_dirent64 *` does not cause alignment violations on 32-bit or 64-bit architectures.

### 3.2 Endian-Neutral Wire Protocol (`pel.c`)
The PEL transport protocol handles framing length prefixes and 64-bit replay protection sequence numbers using explicit bit shifts (big-endian wire format). Monocypher operates endian-independently. Big-Endian targets (`mips`, `powerpc`, `mips64`) and Little-Endian targets (`arm`, `arm64`, `riscv64`, `riscv32`, `mipsel`, `mips64el`, `x86_64`) communicate seamlessly across network boundaries without translation layers.

### 3.3 Foreign ELF Stripping
Host `strip` cannot parse foreign ELF targets. The build system invokes `$(STRIP)` derived from the target cross-prefix (`$(CROSS_COMPILE)strip`).

---

## 4. Usage Guide

### 4.1 Toolchain Acquisition
To download standalone musl cross toolchains into `.toolchains/` without requiring root permissions:
```bash
# Fetch all target toolchains (ARM, ARM64, MIPS, MIPSEL, RISCV64, RISCV32, PowerPC, MIPS64, MIPS64EL)
./scripts/fetch_toolchains.sh all

# Or fetch an individual target:
./scripts/fetch_toolchains.sh riscv64
./scripts/fetch_toolchains.sh powerpc
```

### 4.2 Building Binaries

Build specific architecture targets directly:
```bash
make linux_arm_musl      # ARM32
make linux_arm64_musl    # ARM64
make linux_riscv64_musl  # RISC-V 64
make linux_riscv32_musl  # RISC-V 32
make linux_powerpc_musl  # PowerPC 32
make linux_mips_musl     # MIPS32 Big-Endian
make linux_mipsel_musl   # MIPS32 Little-Endian
make linux_mips64_musl   # MIPS64 Big-Endian
make linux_mips64el_musl # MIPS64 Little-Endian
```

Build and stage all architectures into `dist/<arch>/`:
```bash
make cross_all
```

Custom toolchain paths can be passed using standard environment overrides:
```bash
make RISCV64_CROSS=/custom/toolchain/bin/riscv64-linux-musl- linux_riscv64_musl
```

### 4.3 Automated Cross-Architecture Testing (QEMU User Emulation)
Run the PEL cryptographic unit test suite across all 9 target architectures under QEMU user space emulation:
```bash
make test_cross_qemu
```

---

## 5. Verification Checklist

- [x] Alignment-safe directory reading on MIPS/ARM/PPC (`__attribute__((aligned(8)))`).
- [x] Endianness compatibility verified on Big-Endian architectures (MIPS, PowerPC, MIPS64) under QEMU.
- [x] Pure static linking against `musl libc` verified with `file` and `ldd`.
- [x] Automated QEMU user space unit tests passing for all 9 architectures.
- [x] All 41 integration tests passing cleanly without regressions.
