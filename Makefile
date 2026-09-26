CC		= gcc
RM		= rm -f
STRIP		= strip
CFLAGS		= -Os -Wall -Wextra -ffunction-sections -fdata-sections -fno-asynchronous-unwind-tables -fno-unwind-tables -flto
LDFLAGS		+= -Wl,--gc-sections -Wl,--build-id=none -flto

TOOLCHAIN	= /var/toolchain/sys30

COMM		= pel.o monocypher.o monocypher-ed25519.o
TSH		= tsh
TSHD		= tshd

ifdef SECRET_KEY
DEFS		+= -DSECRET_KEY="\"$(SECRET_KEY)\""
$(info [DEBUG] Building with SECRET_KEY: $(SECRET_KEY))
endif

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
CLIENT_OBJ=pel.c monocypher.c monocypher-ed25519.c  tsh.c
SERVER_OBJ=pel.c monocypher.c monocypher-ed25519.c tshd.c

DISTFILES= \
    monocypher.h \
    monocypher-ed25519.h \
    README \
    ChangeLog\
    pel.h \
    Makefile \
    tsh.h\
    $(CLIENT_OBJ) $(SERVER_OBJ)

VALGRIND_FLAGS	= --leak-check=full --show-leak-kinds=all --track-origins=yes --error-exitcode=1 --errors-for-leak-kinds=all --trace-children=yes

.PHONY: all clean dist osx darwin iphone linux linux_valgrind linux_asan linux_musl linux_x64 openbsd freebsd netbsd sunos cygwin irix hpux osf analyze valgrind asan ubsan

all:
	@echo
	@echo "Please specify one of these targets:"
	@echo
	@echo "	make linux"
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
		$(TSH) $(TSHD)

iphone:
	$(MAKE)								\
		CFLAGS="$(CFLAGS) -I$(TOOLCHAIN)/usr/include"		\
		LDFLAGS="$(LDFLAGS) -L$(TOOLCHAIN)/usr/lib -lutil"	\
		DEFS="$(DEFS) -DOPENBSD"				\
		$(TSH) $(TSHD)
	ldid -S $(TSH)
	ldid -S $(TSHD)

linux:
	$(CC) $(CFLAGS) $(DEFS) $(LDFLAGS) -o tsh  $(CLIENT_OBJ)
	$(CC) $(CFLAGS) $(DEFS) $(LDFLAGS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	$(STRIP) tsh tshd

linux_valgrind:
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -o tsh  $(CLIENT_OBJ)
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil

linux_asan:
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -o tsh  $(CLIENT_OBJ)
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil

analyze:
	@echo "--- Running GCC static analyzer (-fanalyzer) ---"
	$(CC) -I. -fanalyzer -Wall -Wextra -c pel.c tsh.c tshd.c
	@rm -f *.o
	@if [ -d "tshvenv" ]; then \
		echo "--- Running CodeChecker static analysis ---"; \
		bash -c "source tshvenv/bin/activate && \
			rm -rf codechecker_reports compile_commands.json && \
			CodeChecker log -b '$(MAKE) clean && $(MAKE) linux' -o compile_commands.json && \
			CodeChecker analyze compile_commands.json -i .codechecker_skip -o ./codechecker_reports && \
			CodeChecker parse ./codechecker_reports"; \
	fi

valgrind:
	@echo "--- Building dynamic glibc binaries with debug symbols ---"
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -o tsh $(CLIENT_OBJ)
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	$(CC) -O1 -g -fno-inline -Wall -Wextra -fno-omit-frame-pointer -I. test/test_pel_unit.c pel.c monocypher.c monocypher-ed25519.c -o test/test_pel_unit
	@echo "--- Running Valgrind on PEL cryptographic unit tests ---"
	valgrind $(VALGRIND_FLAGS) ./test/test_pel_unit
	@if [ -d "tshvenv" ]; then \
		echo "--- Running Valgrind pytest transaction tests ---"; \
		bash -c "source tshvenv/bin/activate && pytest -sv test/test_valgrind.py"; \
	fi

asan:
	@echo "--- Building AddressSanitizer binaries ---"
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -o tsh $(CLIENT_OBJ)
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer $(DEFS) -DLINUX -o tshd $(SERVER_OBJ) -lutil
	$(CC) -fsanitize=address -g -O1 -Wall -Wextra -fno-omit-frame-pointer -I. test/test_pel_unit.c pel.c monocypher.c monocypher-ed25519.c -o test/test_pel_unit_asan
	@echo "--- Running AddressSanitizer on PEL cryptographic unit tests ---"
	ASAN_OPTIONS="detect_leaks=1:abort_on_error=1:halt_on_error=1" ./test/test_pel_unit_asan
	@rm -f test/test_pel_unit_asan
	@if [ -d "tshvenv" ]; then \
		echo "--- Running AddressSanitizer pytest transaction tests ---"; \
		bash -c "source tshvenv/bin/activate && pytest -sv test/test_asan.py"; \
	fi

ubsan:
	@echo "--- Building UndefinedBehaviorSanitizer binaries ---"
	$(CC) -O2 -c monocypher.c monocypher-ed25519.c
	$(CC) -fsanitize=undefined -g -O1 -Wall -Wextra $(DEFS) -o tsh pel.c tsh.c monocypher.o monocypher-ed25519.o
	$(CC) -fsanitize=undefined -g -O1 -Wall -Wextra $(DEFS) -DLINUX -o tshd pel.c tshd.c monocypher.o monocypher-ed25519.o -lutil
	$(CC) -fsanitize=undefined -g -O1 -Wall -Wextra -I. test/test_pel_unit.c pel.c monocypher.o monocypher-ed25519.o -o test/test_pel_unit_ubsan
	@echo "--- Running UndefinedBehaviorSanitizer on PEL cryptographic unit tests ---"
	UBSAN_OPTIONS="halt_on_error=1:abort_on_error=1:print_stacktrace=1" ./test/test_pel_unit_ubsan
	@rm -f test/test_pel_unit_ubsan monocypher.o monocypher-ed25519.o
	@if [ -d "tshvenv" ]; then \
		echo "--- Running UndefinedBehaviorSanitizer pytest transaction tests ---"; \
		bash -c "source tshvenv/bin/activate && pytest -sv test/test_ubsan.py"; \
	fi

linux_musl:
	musl-gcc $(CFLAGS) -static $(DEFS) $(LDFLAGS) -static -o tsh  $(CLIENT_OBJ)
	musl-gcc $(CFLAGS) -static $(DEFS) $(LDFLAGS) -static -DLINUX -o tshd $(SERVER_OBJ)
	$(STRIP) tsh tshd

linux_x64:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -Xlinker --no-as-needed -lutil"	\
		DEFS="$(DEFS) -DLINUX"					\
		$(TSH) $(TSHD)

openbsd:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -lutil"				\
		DEFS="$(DEFS) -DOPENBSD"				\
		$(TSH) $(TSHD)

freebsd:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -lutil"				\
		DEFS="$(DEFS) -DFREEBSD"				\
		$(TSH) $(TSHD)

netbsd: openbsd

sunos:
	$(MAKE)								\
		LDFLAGS="$(LDFLAGS) -lsocket -lnsl"			\
		DEFS="$(DEFS) -DSUNOS"					\
		$(TSH) $(TSHD)

cygwin:
	$(MAKE)								\
		DEFS="$(DEFS) -DCYGWIN"					\
		$(TSH) $(TSHD)

irix:
	$(MAKE)								\
		CC="cc"							\
		CFLAGS="-O"						\
		DEFS="$(DEFS) -DIRIX"					\
		$(TSH) $(TSHD)

hpux:
	$(MAKE)								\
		CC="cc"							\
		CFLAGS="-O"						\
		DEFS="$(DEFS) -DHPUX"					\
		$(TSH) $(TSHD)

osf:
	$(MAKE)								\
		CC="cc"							\
		CFLAGS="-O"						\
		DEFS="$(DEFS) -DOSF"					\
		$(TSH) $(TSHD)

$(TSH): $(COMM) tsh.o
	$(CC) ${LDFLAGS} -o $(TSH) $(COMM) tsh.o
	$(STRIP) $(TSH)

$(TSHD): $(COMM) tshd.o
	$(CC) ${LDFLAGS} -o $(TSHD) $(COMM) tshd.o
	$(STRIP) $(TSHD)

monocypher.o: monocypher.h
monocypher-ed25519.o: monocypher-ed25519.h monocypher.h
pel.o: monocypher.h monocypher-ed25519.h pel.h
tsh.o: pel.h tsh.h
tshd.o: pel.h tsh.h

.c.o:
	$(CC) ${CFLAGS} ${DEFS} -c $*.c

clean:
	$(RM) $(TSH) $(TSHD) test/test_pel_unit *.o test/*.o core compile_commands.json
	rm -rf codechecker_reports


dist:
	mkdir $(VERSION)
	cp $(DISTFILES) $(VERSION)
	tar -czf $(VERSION).tar.gz $(VERSION)
	rm -r $(VERSION)
