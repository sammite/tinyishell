# Roadmap: Static Linking with musl libc

The goal of this task is to enable static linking against `musl libc` to produce truly portable, minimal-footprint binaries suitable for embedded systems without any shared library dependencies.

## 1. Why musl libc?

- **Size:** `musl` is significantly smaller than `glibc`.
- **Portability:** Static binaries don't depend on the target's libc version.
- **Security:** Reduces the attack surface by eliminating dynamic linking vulnerabilities.

## 2. Setting up the Environment

To use `musl`, we need the `musl-gcc` wrapper and the `musl` development headers.

### Installation on Debian/Ubuntu:
```bash
sudo apt-get update
sudo apt-get install musl-tools
```

### Installation on Fedora/RHEL:
```bash
sudo dnf install musl-libc-static musl-gcc
```

### Installation on Arch Linux:
```bash
sudo pacman -S musl
```

### Verification:
Ensure `musl-gcc` is in your PATH:
```bash
musl-gcc --version
```

## 3. Implementation Plan

### Step 1: Update Makefile
Add a new target `linux_musl` that uses `musl-gcc` and the `-static` flag.

```makefile
linux_musl:
	$(MAKE) \
		CC="musl-gcc" \
		CFLAGS="$(CFLAGS) -static" \
		LDFLAGS="$(LDFLAGS) -static" \
		DEFS="$(DEFS) -DLINUX" \
		$(TSH) $(TSHD)
```

*Note: We might need to handle the `-lutil` dependency. `musl` provides most standard functions, but some PTY-related functions usually in `libutil` on glibc systems might be different or unnecessary now that we've removed PTY support.*

### Step 2: Handle Dependencies
Verify if `musl` supports all the syscalls and headers we are using. Since we've removed PTY support and are using standard POSIX for `ls` and `execv`, it should be highly compatible.

### Step 3: Verification
1. Build with `make linux_musl`.
2. Check if the binary is truly static:
   ```bash
   file tsh
   ldd tsh  # Should report "not a dynamic executable"
   ```
3. Run the integration tests using the static binaries to ensure functional parity.

## 4. Expected Outcomes
- Binary size significantly reduced (target < 100KB for a fully static build).
- Zero external library dependencies.
- Improved reliability on minimal Linux distributions (like Alpine or custom BusyBox builds).
