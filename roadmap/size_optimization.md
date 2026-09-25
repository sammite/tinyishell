# Embedded Size Reduction for Static musl tshd

## Results Summary

| Milestone / Optimization | Static musl `tshd` | Static musl `tshd` (CB_MODE) | Cumulative Reduction |
| :--- | :--- | :--- | :--- |
| **Legacy Baseline (AES + SHA1)** | 87,520 bytes (~85.5 KB) | 108,000 bytes (~105.5 KB) | Baseline |
| **Monocypher Migration** | 75,472 bytes (~74.0 KB) | 79,296 bytes (~77.5 KB) | -12.0 KB (-14%) / -28.7 KB (-27%) |
| **Phase 1: Compiler & Linker Flags** | 71,104 bytes (~69.5 KB) | 71,104 bytes (~69.5 KB) | -16.4 KB (-19%) / -36.9 KB (-34%) |
| **Phase 2 & 3: Stdio & Malloc Dropped** | **50,360 bytes (~49.2 KB)** | **50,360 bytes (~49.2 KB)** | **-37.2 KB (-42.5%) / -57.6 KB (-53.4%)** |

All **36 tests in the test suite** pass cleanly (`./begin_tests.sh`).

---

## Implemented Optimizations

### 1. Cryptographic Migration (Monocypher)
* Replaced legacy AES-CBC-128 (16.5 KB S-box tables) and HMAC-SHA1 (8 KB unrolled transform).
* Implemented X25519 (ECDH) + Ed25519 (Client Auth) + ChaCha20-Poly1305 (AEAD) + BLAKE2b (KDF).
* Zero private keys or credentials stored on target devices.
* Adheres to Barr-C:2018.

### 2. Toolchain & Linker Flags (Phase 1)
* Added `-fno-asynchronous-unwind-tables -fno-unwind-tables` to `CFLAGS`.
* Added `-Wl,--build-id=none` to `LDFLAGS`.
* Stripped unnecessary `.eh_frame` DWARF unwinding tables and 4 KB page alignment overhead.

### 3. Formatted I/O (`stdio`) Elimination (Phase 2)
* Removed all calls to `perror()`.
* Replaced `snprintf()` with direct pointer-based integer and octal formatters (`append_octal6`, `append_uint`, `append_str`).
* Removed `<stdio.h>` dependency from `tshd`.
* Eliminates musl's `printf_core`, `fmt_fp` (4.7 KB float formatter), and `errmsgstr` error-table.

### 4. Memory Allocator & Syscall Optimization (Phase 3)
* Replaced POSIX `opendir()` / `readdir()` / `closedir()` with raw Linux `SYS_getdents64` and `fstatat()`.
* Replaced `strdup()` in `tshd_execv()` with direct in-place parsing on the message buffer.
* Eliminates `malloc()`, `free()`, and musl's entire slab allocator (`alloc_slot`, `__malloc_alloc_meta`, `__malloc_context`).
