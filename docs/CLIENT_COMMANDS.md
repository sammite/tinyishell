# Tiny SHell (`tsh`) Client Reference & Command Guide

This guide documents all command-line arguments, operational modes, single-shot actions, and interactive REPL commands supported by the Tiny SHell client (`tsh_client.py` and the `./tsh` executable).

---

## 1. Overview & Architecture

The `tinyishell` client is implemented natively in Python ([`tsh_client.py`](file:///home/sam/Projects/tinyishell/tsh_client.py) and [`tsh_pel.py`](file:///home/sam/Projects/tinyishell/tsh_pel.py)) using `PyNaCl`. A convenience executable symlink (`./tsh -> tsh_client.py`) is provided in the repository root.

- **Authentication:** All client connections authenticate with an Ed25519 private key seed (by default `./tsh_key`).
- **Transport Security:** Once authenticated via the Monocypher PEL protocol, all subsequent traffic is encrypted using XChaCha20-Poly1305 AEAD with BLAKE2b key derivation and 64-bit sequence counters.
- **Persistent Session Architecture:** Connections maintain an active command dispatch loop over a single TCP stream. Operations (`ls`, `get`, `put`) use in-band 0-byte completion frames rather than socket closure, and `TCP_NODELAY` enables sub-millisecond sequential command execution without reconnection or repeated forking.

---

## 2. Command-Line Syntax & Options

### 2.1 Invocation Syntax
```bash
./tsh [OPTIONS] <HOSTNAME | cb> [ACTION] [ACTION_ARGS...]
```
*(Alternatively, invoke directly via `python3 tsh_client.py ...`)*

### 2.2 Global Flags

| Option | Flag Alias | Default | Description |
| :--- | :--- | :--- | :--- |
| `-k KEY`, `--key KEY` | `-s SECRET` | `./tsh_key` (or `$TSH_KEY`) | Path to the 32-byte Ed25519 private key seed file. |
| `-p PORT`, `--port PORT` | | `1234` | Target TCP port on the server (or local port to bind in connect-back mode). |
| `-d DIR`, `--dir DIR` | | `/` | Initial remote working directory for interactive REPL sessions. |
| `-c CMD`, `--command CMD` | | *None* | Non-interactively executes a single REPL command string and exits. |
| `-v`, `--version` | | | Displays client version and cryptographic engine information. |
| `-h`, `--help` | | | Displays usage summary and argument options. |

---

## 3. Single-Shot Mode (CLI Commands)

When an action verb (`ls`, `exec`, `get`, `put`, `ps`) is passed on the command line, the client executes the request, prints the result, and terminates immediately.

### 3.1 Directory Listing (`ls`)
Queries and displays remote file attributes directly via the daemon's internal `SYS_getdents64` library call.

- **Syntax:**
  ```bash
  ./tsh [OPTIONS] <hostname|cb> ls <remote-directory>
  ```
- **Output Format:**
  ```
  <octal_mode> <uid> <gid> <file_size_bytes> <file_or_dir_name>
  ```
- **Examples:**
  ```bash
  # List remote root directory
  ./tsh 192.168.1.100 ls /

  # List /var/tmp using a custom port and key
  ./tsh -p 8888 -k /keys/prod_key 192.168.1.100 ls /var/tmp
  ```

---

### 3.2 Remote Command Execution (`exec`)
Forks and executes a command string on the remote target using `/bin/sh -c "<command>"`. The client displays the remote command output and prints the remote exit code.

- **Syntax:**
  ```bash
  ./tsh [OPTIONS] <hostname|cb> exec "<command_string>"
  ```
- **Exit Code Behavior:**
  - Standard exit code output: `Exit code: <N>`
  - The client's process exit code matches the remote exit code.
- **Examples:**
  ```bash
  # Check kernel version on remote target
  ./tsh 192.168.1.100 exec "uname -a"

  # Check network interfaces and memory usage
  ./tsh 192.168.1.100 exec "ip addr && free -m"

  # Restart a background service
  ./tsh 192.168.1.100 exec "/etc/init.d/dropbear restart"
  ```

---

### 3.3 File Upload (`put`)
Uploads a local file to a remote path or directory over encrypted PEL packets (streamed in 4096-byte chunks).

- **Syntax:**
  ```bash
  ./tsh [OPTIONS] <hostname|cb> put <local-source-file> <remote-destination-dir-or-file>
  ```
- **Output:** Live byte transfer counter followed by `<total_bytes> done.`.
- **Examples:**
  ```bash
  # Upload a binary to /var/tmp
  ./tsh 192.168.1.100 put busybox_mips /var/tmp

  # Upload firmware image to root
  ./tsh -k ./tsh_key 192.168.1.100 put firmware.bin /tmp/firmware.bin
  ```

---

### 3.4 File Download (`get`)
Downloads a remote file from the target device to a local directory or file path.

- **Syntax:**
  ```bash
  ./tsh [OPTIONS] <hostname|cb> get <remote-source-file> [local-destination-path]
  ```
- **Output:** Live byte transfer counter followed by `<total_bytes> done.`.
- **Examples:**
  ```bash
  # Download remote /etc/passwd to current local directory
  ./tsh 192.168.1.100 get /etc/passwd .

  # Download remote diagnostic log to /tmp/target_dmesg.log
  ./tsh 192.168.1.100 get /var/log/dmesg /tmp/target_dmesg.log
  ```

---

### 3.5 Process Listing (`ps`)
Queries running processes directly by traversing `/proc` on the remote target without requiring an external `ps` binary or any modifications to `tshd`. The client discovers PIDs via remote directory listing and fetches process metadata (`/proc/<pid>/stat`, `/proc/<pid>/cmdline`) concurrently.

- **Syntax:**
  ```bash
  ./tsh [OPTIONS] <hostname|cb> ps
  ```
- **Output Format:**
  ```
     PID   PPID USER     STAT      RSS COMMAND
       1      0 root     S        4.2M /sbin/init
    1240      1 root     S        1.8M /usr/sbin/dropbear -F
    1520      1 1000     S        128K ./tshd
  ```
- **Examples:**
  ```bash
  # List running processes on remote target
  ./tsh 192.168.1.100 ps

  # List processes on default localhost target
  ./tsh ps
  ```

---

### 3.6 Connect-Back Mode (`cb`)
Used when the embedded target is behind a NAT or firewall and `tshd` was built with `CB_MODE` enabled. Instead of connecting outbound to the target, the client binds a local listening socket and waits for the target to connect back.

- **Syntax:**
  ```bash
  ./tsh [OPTIONS] cb <action> [action_args...]
  ```
- **Example Workflow:**
  ```bash
  # 1. Start client waiting for target connection on port 5555
  ./tsh -p 5555 cb ls /
  ```

  # 2. Output on client terminal:
  # Waiting for the server to connect...connected.
  # <directory listing output...>
  ```

---

## 4. Interactive REPL Mode

When executed without a single-shot action verb, the client launches an interactive command-line shell tracking remote working directory context across queries.

### 4.1 Launching the REPL
```bash
./tsh [OPTIONS] <hostname|cb>
```
Example:
```bash
$ ./tsh 192.168.1.100
Connected to Tiny SHell. Type 'help' or '?' to list commands.

tsh [192.168.1.100:/]$ 
```

### 4.2 Built-In REPL Commands

| Command | Syntax | Description |
| :--- | :--- | :--- |
| `cd` | `cd <remote-dir>` | Changes the remote working directory. Validates directory existence remotely, normalizes relative paths (`..`, `.`), and updates prompt. |
| `pwd` | `pwd` | Displays the current remote working directory path. |
| `ls` | `ls [remote-dir]` | Lists remote files in current remote working directory (or optional target path). |
| `exec` | `exec <command>` | Executes command on remote target (automatically prepends `cd <cwd> &&` to maintain directory context). |
| `put` | `put <local-file> [remote-dst]` | Uploads local file into the currently tracked remote directory (or optional remote destination path). |
| `get` | `get <remote-file> [local-dst]` | Downloads file relative to current remote directory into local directory. |
| `ps` | `ps` | Lists running processes on the remote target parsed from `/proc`. |
| `lcd` | `lcd <local-dir>` | Changes local workstation working directory. |
| `lpwd` | `lpwd` | Displays current local workstation working directory. |
| `help`, `?` | `help [command]` | Lists all available REPL commands and displays syntax documentation. |
| `exit`, `quit` | `exit` | Terminates the REPL session (`Ctrl-D` and `Ctrl-C` also exit). |

### 4.3 Interactive REPL Session Example
```text
$ ./tsh 192.168.1.50
Connected to Tiny SHell. Type 'help' or '?' to list commands.

tsh [192.168.1.50:/]$ cd /var/tmp
tsh [192.168.1.50:/var/tmp]$ ls
040777 0 0 4096 .
040755 0 0 4096 ..
100644 0 0 1024 system.log

tsh [192.168.1.50:/var/tmp]$ put local_script.sh
350 done.

tsh [192.168.1.50:/var/tmp]$ exec chmod +x local_script.sh && ./local_script.sh
Script output: Sensor health OK
Exit code: 0

tsh [192.168.1.50:/var/tmp]$ get system.log ./diagnostics/
1024 done.

tsh [192.168.1.50:/var/tmp]$ exit
```

---

## 5. Non-Interactive Scripting & Pipelines

### 5.1 Single Command String (`-c`)
You can pass single-command scripts directly through the REPL engine without opening an interactive terminal:
```bash
./tsh 192.168.1.100 -c "pwd"
./tsh 192.168.1.100 -d /var/tmp -c "ls"
```

### 5.2 Piped Stdin Execution
Multi-line commands can be streamed via standard input pipelines for automated orchestration:
```bash
cat << 'EOF' | ./tsh 192.168.1.100
cd /var/tmp
pwd
ls
exit
EOF
```

---

## 6. Exit Codes

The client standardizes exit codes across all single-shot and programmatic invocations:

| Return Code | Meaning | Cause / Notes |
| :---: | :--- | :--- |
| `0` | **Success** | Command, listing, or transfer completed successfully. |
| `1` | **Client Error** | Invalid command-line arguments, syntax error, or missing local key file. |
| `4` | **Connection Error** | Network socket error, connection refused, or broken pipe. |
| `10` | **Auth Failed** | Server rejected Ed25519 signature / challenge verification. |
| `11` | **Protocol Error** | Packet Encryption Layer error (corrupted payload or bad length). |
| `14` | **Local Creat Error** | `get` failed to create local target file (permission denied or disk full). |
| `19` | **Local Open Error** | `put` failed to open local source file (file not found). |
| `39` | **Bad Server Response** | Unexpected response length from server during `exec`. |
| `N` | **Remote Exit Code** | In `exec` mode, returns the process exit code returned by `/bin/sh` (e.g. `1` for `/bin/false`, `127` for command not found). |
