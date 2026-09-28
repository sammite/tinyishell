CROSS_COMPILE	?=
CC		= $(CROSS_COMPILE)gcc
RM		= rm -f
STRIP		= $(CROSS_COMPILE)strip
CFLAGS		= -Os -Wall -Wextra -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -fno-unwind-tables -fstack-usage -flto
LDFLAGS		+= -Wl,--gc-sections -Wl,--build-id=none -flto

TOOLCHAIN_DIR	?= .toolchains
ARM_CROSS	?= $(TOOLCHAIN_DIR)/arm-linux-musleabi-cross/bin/arm-linux-musleabi-
ARM64_CROSS	?= $(TOOLCHAIN_DIR)/aarch64-linux-musl-cross/bin/aarch64-linux-musl-
MIPS_CROSS	?= $(TOOLCHAIN_DIR)/mips-linux-musl-cross/bin/mips-linux-musl-
MIPSEL_CROSS	?= $(TOOLCHAIN_DIR)/mipsel-linux-musl-cross/bin/mipsel-linux-musl-
RISCV64_CROSS	?= $(TOOLCHAIN_DIR)/riscv64-linux-musl-cross/bin/riscv64-linux-musl-
RISCV32_CROSS	?= $(TOOLCHAIN_DIR)/riscv32-linux-musl-cross/bin/riscv32-linux-musl-
POWERPC_CROSS	?= $(TOOLCHAIN_DIR)/powerpc-linux-musl-cross/bin/powerpc-linux-musl-
MIPS64_CROSS	?= $(TOOLCHAIN_DIR)/mips64-linux-musl-cross/bin/mips64-linux-musl-
MIPS64EL_CROSS	?= $(TOOLCHAIN_DIR)/mips64el-linux-musl-cross/bin/mips64el-linux-musl-
DIST_DIR	?= dist

COMM		= pel.o monocypher.o monocypher-ed25519.o
TSH		= tsh
TSHD		= tshd

PYTHON		?= python3
KEY_DIR		?= .
KEY_FILE	?= $(KEY_DIR)/tsh_key
PUBKEY_HEADER	?= tsh_pubkey.h

ifdef CB_HOST
DEFS		+= -DCB_HOST="\"$(CB_HOST)\""
$(info [DEBUG] Building with CB_HOST: $(CB_HOST))
endif

ifdef SERVER_PORT
DEFS		+= -DSERVER_PORT=$(SERVER_PORT)
$(info [DEBUG] Building with SERVER_PORT: $(SERVER_PORT))
endif

ifdef CB_MODE
DEFS		+= -DCB_MODE
$(info [DEBUG] Building with CB_MODE enabled)
endif

ifdef DEBUG
DEFS		+= -DDEBUG
$(info [DEBUG] Building with DEBUG enabled)
endif

VERSION=tsh-0.7
SERVER_OBJ=pel.c monocypher.c monocypher-ed25519.c tshd.c

DISTFILES= \
    monocypher.h \
    monocypher-ed25519.h \
    README \
    ChangeLog\
    pel.h \
    Makefile \
    tsh.h\
    tsh_client.py\
    tsh_pel.py\
    $(SERVER_OBJ)

VALGRIND_FLAGS	= --leak-check=full --show-leak-kinds=all --track-origins=yes --error-exitcode=1 --errors-for-leak-kinds=all --trace-children=yes

.PHONY: all clean dist osx darwin iphone linux linux_valgrind linux_asan linux_musl linux_musl_generic linux_arm_musl linux_arm64_musl linux_mips_musl linux_mipsel_musl linux_riscv64_musl linux_riscv32_musl linux_powerpc_musl linux_mips64_musl linux_mips64el_musl cross_all test_cross_qemu linux_x64 openbsd freebsd netbsd sunos cygwin irix hpux osf analyze valgrind asan ubsan rekey

all:
	@echo
	@echo "Please specify one of these targets:"
	@echo
	@echo "	make linux"
	@echo "	make linux_musl"
	@echo "	make linux_arm_musl"
	@echo "	make linux_arm64_musl"
	@echo "	make linux_mips_musl"
	@echo "	make linux_mipsel_musl"
	@echo "	make linux_riscv64_musl"
	@echo "	make linux_riscv32_musl"
	@echo "	make linux_powerpc_musl"
	@echo "	make linux_mips64_musl"
	@echo "	make linux_mips64el_musl"
	@echo "	make cross_all"
	@echo "	make test_cross_qemu"
	@echo "	make linux_x64"
	@echo "	make freebsd"
	@echo "	make openbsd"
	@echo "	make netbsd"
	@echo "	make cygwin"
	@echo "	make sunos"
	@echo "	make irix"
	@echo "	make hpux"
	@echo "	make osf"
	@echo "	make iphone"
	@echo "	make darwin"
	@echo "	make analyze"
	@echo "	make valgrind"
	@echo "	make asan"
	@echo "	make ubsan"
	@echo
	make `uname | tr A-Z a-z`

osx: darwin

darwin:
	$(MAKE)								\
		CC="clang"						\
		LDFLAGS="$(LDFLAGS) -lutil"				\
		DEFS="$(DEFS) -DOPENBSD"				\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

iphone:
	$(MAKE)								\
		CFLAGS="$(CFLAGS) -I$(TOOLCHAIN)/usr/include"		\
		LDFLAGS="$(LDFLAGS) -L$(TOOLCHAIN)/usr/lib -lutil"	\
		DEFS="$(DEFS) -DOPENBSD"				\
		$(TSHD)
	ldid -S $(TSHD)
	ln -sf tsh_client.py $(TSH)

linux: $(PUBKEY_HEADER)
	$(CC) $(CFLAGS) $(DEFS) $(LDFLAGS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	$(STRIP) tshd
	ln -sf tsh_client.py $(TSH)

linux_valgrind: $(PUBKEY_HEADER)
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	ln -sf tsh_client.py $(TSH)

linux_asan: $(PUBKEY_HEADER)
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	ln -sf tsh_client.py $(TSH)

analyze:
	@echo "--- Running GCC static analyzer (-fanalyzer) ---"
	$(CC) -I. -fanalyzer -Wall -Wextra -c pel.c tshd.c
	@rm -f *.o
	@if [ -d "tshvenv" ]; then \
		echo "--- Running CodeChecker static analysis ---"; \
		bash -c "source tshvenv/bin/activate && \
			rm -rf codechecker_reports compile_commands.json && \
			CodeChecker log -b '$(MAKE) clean && $(MAKE) linux' -o compile_commands.json && \
			CodeChecker analyze compile_commands.json -i .codechecker_skip -o ./codechecker_reports && \
			CodeChecker parse ./codechecker_reports"; \
	fi

valgrind: $(PUBKEY_HEADER)
	@echo "--- Building dynamic glibc binaries with debug symbols ---"
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	ln -sf tsh_client.py $(TSH)
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer -I. test/test_pel_unit.c pel.c monocypher.c monocypher-ed25519.c -o test/test_pel_unit
	@echo "--- Running Valgrind on PEL cryptographic unit tests ---"
	valgrind $(VALGRIND_FLAGS) ./test/test_pel_unit
	@if [ -d "tshvenv" ]; then \
		echo "--- Running Valgrind pytest transaction tests ---"; \
		bash -c "source tshvenv/bin/activate && pytest -sv test/test_valgrind.py"; \
	fi

asan: $(PUBKEY_HEADER)
	@echo "--- Building AddressSanitizer binaries ---"
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	ln -sf tsh_client.py $(TSH)
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer -I. test/test_pel_unit.c pel.c monocypher.c monocypher-ed25519.c -o test/test_pel_unit_asan
	@echo "--- Running AddressSanitizer on PEL cryptographic unit tests ---"
	ASAN_OPTIONS="detect_leaks=1:abort_on_error=1:halt_on_error=1" ./test/test_pel_unit_asan
	@rm -f test/test_pel_unit_asan
	@if [ -d "tshvenv" ]; then \
		echo "--- Running AddressSanitizer pytest transaction tests ---"; \
		bash -c "source tshvenv/bin/activate && pytest -sv test/test_asan.py"; \
	fi

ubsan: $(PUBKEY_HEADER)
	@echo "--- Building UndefinedBehaviorSanitizer binaries ---"
	$(CC) -O2 -c monocypher.c monocypher-ed25519.c
	$(CC) -fsanitize=undefined -g -O1 -Wall -Wextra $(DEFS) -DLINUX -o tshd pel.c tshd.c monocypher.o monocypher-ed25519.o -lutil
	ln -sf tsh_client.py $(TSH)
	$(CC) -fsanitize=undefined -g -O1 -Wall -Wextra -I. test/test_pel_unit.c pel.c monocypher.o monocypher-ed25519.o -o test/test_pel_unit_ubsan
	@echo "--- Running UndefinedBehaviorSanitizer on PEL cryptographic unit tests ---"
	UBSAN_OPTIONS="halt_on_error=1:abort_on_error=1:print_stacktrace=1" ./test/test_pel_unit_ubsan
	@rm -f test/test_pel_unit_ubsan monocypher.o monocypher-ed25519.o
	@if [ -d "tshvenv" ]; then \
		echo "--- Running UndefinedBehaviorSanitizer pytest transaction tests ---"; \
		bash -c "source tshvenv/bin/activate && pytest -sv test/test_ubsan.py"; \
	fi

linux_musl:
	$(MAKE) CC="musl-gcc" STRIP="$(STRIP)" linux_musl_generic

linux_musl_generic: $(PUBKEY_HEADER)
	$(RM) $(TSHD)
	$(CC) $(CFLAGS) -static $(DEFS) $(LDFLAGS) -static -DLINUX -o $(TSHD) $(SERVER_OBJ)
	$(STRIP) $(TSHD)
	ln -sf tsh_client.py $(TSH)

linux_arm_musl:
	@if [ -x "$(ARM_CROSS)gcc" ]; then \
		$(MAKE) CC="$(ARM_CROSS)gcc" STRIP="$(ARM_CROSS)strip" linux_musl_generic; \
	elif command -v arm-linux-musleabi-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="arm-linux-musleabi-gcc" STRIP="arm-linux-musleabi-strip" linux_musl_generic; \
	else \
		echo "[-] ARM cross toolchain not found in $(ARM_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh arm to download."; \
		exit 1; \
	fi

linux_arm64_musl:
	@if [ -x "$(ARM64_CROSS)gcc" ]; then \
		$(MAKE) CC="$(ARM64_CROSS)gcc" STRIP="$(ARM64_CROSS)strip" linux_musl_generic; \
	elif command -v aarch64-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="aarch64-linux-musl-gcc" STRIP="aarch64-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] AArch64 cross toolchain not found in $(ARM64_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh arm64 to download."; \
		exit 1; \
	fi

linux_mips_musl:
	@if [ -x "$(MIPS_CROSS)gcc" ]; then \
		$(MAKE) CC="$(MIPS_CROSS)gcc" STRIP="$(MIPS_CROSS)strip" linux_musl_generic; \
	elif command -v mips-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="mips-linux-musl-gcc" STRIP="mips-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] MIPS cross toolchain not found in $(MIPS_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh mips to download."; \
		exit 1; \
	fi

linux_mipsel_musl:
	@if [ -x "$(MIPSEL_CROSS)gcc" ]; then \
		$(MAKE) CC="$(MIPSEL_CROSS)gcc" STRIP="$(MIPSEL_CROSS)strip" linux_musl_generic; \
	elif command -v mipsel-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="mipsel-linux-musl-gcc" STRIP="mipsel-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] MIPSEL cross toolchain not found in $(MIPSEL_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh mipsel to download."; \
		exit 1; \
	fi

linux_riscv64_musl:
	@if [ -x "$(RISCV64_CROSS)gcc" ]; then \
		$(MAKE) CC="$(RISCV64_CROSS)gcc" STRIP="$(RISCV64_CROSS)strip" linux_musl_generic; \
	elif command -v riscv64-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="riscv64-linux-musl-gcc" STRIP="riscv64-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] RISC-V 64 cross toolchain not found in $(RISCV64_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh riscv64 to download."; \
		exit 1; \
	fi

linux_riscv32_musl:
	@if [ -x "$(RISCV32_CROSS)gcc" ]; then \
		$(MAKE) CC="$(RISCV32_CROSS)gcc" STRIP="$(RISCV32_CROSS)strip" linux_musl_generic; \
	elif command -v riscv32-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="riscv32-linux-musl-gcc" STRIP="riscv32-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] RISC-V 32 cross toolchain not found in $(RISCV32_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh riscv32 to download."; \
		exit 1; \
	fi

linux_powerpc_musl:
	@if [ -x "$(POWERPC_CROSS)gcc" ]; then \
		$(MAKE) CC="$(POWERPC_CROSS)gcc" STRIP="$(POWERPC_CROSS)strip" linux_musl_generic; \
	elif command -v powerpc-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="powerpc-linux-musl-gcc" STRIP="powerpc-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] PowerPC cross toolchain not found in $(POWERPC_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh powerpc to download."; \
		exit 1; \
	fi

linux_mips64_musl:
	@if [ -x "$(MIPS64_CROSS)gcc" ]; then \
		$(MAKE) CC="$(MIPS64_CROSS)gcc" STRIP="$(MIPS64_CROSS)strip" linux_musl_generic; \
	elif command -v mips64-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="mips64-linux-musl-gcc" STRIP="mips64-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] MIPS64 cross toolchain not found in $(MIPS64_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh mips64 to download."; \
		exit 1; \
	fi

linux_mips64el_musl:
	@if [ -x "$(MIPS64EL_CROSS)gcc" ]; then \
		$(MAKE) CC="$(MIPS64EL_CROSS)gcc" STRIP="$(MIPS64EL_CROSS)strip" linux_musl_generic; \
	elif command -v mips64el-linux-musl-gcc >/dev/null 2>&1; then \
		$(MAKE) CC="mips64el-linux-musl-gcc" STRIP="mips64el-linux-musl-strip" linux_musl_generic; \
	else \
		echo "[-] MIPS64EL cross toolchain not found in $(MIPS64EL_CROSS) or PATH."; \
		echo "    Run ./scripts/fetch_toolchains.sh mips64el to download."; \
		exit 1; \
	fi

cross_all:
	@mkdir -p $(DIST_DIR)/arm $(DIST_DIR)/arm64 $(DIST_DIR)/mips $(DIST_DIR)/mipsel \
		  $(DIST_DIR)/riscv64 $(DIST_DIR)/riscv32 $(DIST_DIR)/powerpc \
		  $(DIST_DIR)/mips64 $(DIST_DIR)/mips64el
	@echo "--- Building static musl ARM (arm-linux-musleabi) ---"
	$(MAKE) linux_arm_musl
	@cp $(TSHD) $(DIST_DIR)/arm/
	@echo "--- Building static musl AArch64 (aarch64-linux-musl) ---"
	$(MAKE) linux_arm64_musl
	@cp $(TSHD) $(DIST_DIR)/arm64/
	@echo "--- Building static musl MIPS (mips-linux-musl) ---"
	$(MAKE) linux_mips_musl
	@cp $(TSHD) $(DIST_DIR)/mips/
	@echo "--- Building static musl MIPSEL (mipsel-linux-musl) ---"
	$(MAKE) linux_mipsel_musl
	@cp $(TSHD) $(DIST_DIR)/mipsel/
	@echo "--- Building static musl RISC-V 64 (riscv64-linux-musl) ---"
	$(MAKE) linux_riscv64_musl
	@cp $(TSHD) $(DIST_DIR)/riscv64/
	@echo "--- Building static musl RISC-V 32 (riscv32-linux-musl) ---"
	$(MAKE) linux_riscv32_musl
	@cp $(TSHD) $(DIST_DIR)/riscv32/
	@echo "--- Building static musl PowerPC (powerpc-linux-musl) ---"
	$(MAKE) linux_powerpc_musl
	@cp $(TSHD) $(DIST_DIR)/powerpc/
	@echo "--- Building static musl MIPS64 (mips64-linux-musl) ---"
	$(MAKE) linux_mips64_musl
	@cp $(TSHD) $(DIST_DIR)/mips64/
	@echo "--- Building static musl MIPS64EL (mips64el-linux-musl) ---"
	$(MAKE) linux_mips64el_musl
	@cp $(TSHD) $(DIST_DIR)/mips64el/
	@echo "--- Cross-compilation complete! Binaries in $(DIST_DIR)/ ---"
	@ls -lh $(DIST_DIR)/*/*

test_cross_qemu:
	@./scripts/test_cross_qemu.sh

linux_x64:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -Xlinker --no-as-needed -lutil"	\
		DEFS="$(DEFS) -DLINUX"					\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

openbsd:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -lutil"				\
		DEFS="$(DEFS) -DOPENBSD"				\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

freebsd:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -lutil"				\
		DEFS="$(DEFS) -DFREEBSD"				\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

netbsd: openbsd

sunos:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -lsocket -lnsl"			\
		DEFS="$(DEFS) -DSUNOS"					\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

cygwin:
	$(MAKE)								\
		DEFS="$(DEFS) -DCYGWIN"					\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

irix:
	$(MAKE)								\
		CC="cc"							\
		CFLAGS="-O"						\
		DEFS="$(DEFS) -DIRIX"					\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

hpux:
	$(MAKE)								\
		CC="cc"							\
		CFLAGS="-O"						\
		DEFS="$(DEFS) -DHPUX"					\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

osf:
	$(MAKE)								\
		CC="cc"							\
		CFLAGS="-O"						\
		DEFS="$(DEFS) -DOSF"					\
		$(TSHD)
	ln -sf tsh_client.py $(TSH)

$(TSH):
	ln -sf tsh_client.py $(TSH)

$(TSHD): $(PUBKEY_HEADER) $(COMM) tshd.o
	$(CC) ${LDFLAGS} -o $(TSHD) $(COMM) tshd.o
	$(STRIP) $(TSHD)

monocypher.o: monocypher.h
monocypher-ed25519.o: monocypher-ed25519.h monocypher.h
pel.o: monocypher.h monocypher-ed25519.h pel.h
tshd.o: pel.h tsh.h $(PUBKEY_HEADER)

$(PUBKEY_HEADER):
	@if [ ! -f $(PUBKEY_HEADER) ] || [ ! -f $(KEY_FILE) ]; then \
		echo "--- Generating Ed25519 keypair ($(KEY_FILE), $(PUBKEY_HEADER)) ---"; \
		$(PYTHON) scripts/keygen.py -o $(KEY_FILE) --header $(PUBKEY_HEADER); \
	fi

rekey:
	@echo "--- Regenerating Ed25519 keypair ($(KEY_FILE), $(PUBKEY_HEADER)) ---"
	$(PYTHON) scripts/keygen.py -o $(KEY_FILE) --header $(PUBKEY_HEADER)

.c.o:
	$(CC) ${CFLAGS} ${DEFS} -c $*.c

clean:
	$(RM) $(TSH) $(TSHD) test/test_pel_unit test/test_pel_unit_* *.o test/*.o *.su test/*.su core compile_commands.json
	rm -rf codechecker_reports $(DIST_DIR) build


dist:
	mkdir $(VERSION)
	cp $(DISTFILES) $(VERSION)
	tar -czf $(VERSION).tar.gz $(VERSION)
	rm -r $(VERSION)
