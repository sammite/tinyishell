# Robust Pytest Framework for Embedded Debug Shell (EDS)

This document outlines the granular testing strategy for `tsh` using the Python `pytest` framework.

## 1. Test Environment & Fixtures

- **`tshd_daemon` Fixture:**
    - Handles compilation of `tshd` with specific `SECRET_KEY` and `SERVER_PORT`.
    - Manages the lifecycle of the daemon process (start before test, kill/cleanup after).
- **Temporary Workspace:** Use pytest's `tmp_path` for creating local files for `put`/`get` tests.

## 2. Granular Test Cases

### Connectivity & Security
- `test_auth_success`: Connect with the correct `SECRET_KEY`.
- `test_auth_failure`: Attempt connection with an incorrect key; verify `tsh` reports failure.
- `test_custom_port`: Build and connect using a non-default `SERVER_PORT`.

### Directory Listing (`ls`)
- `test_ls_root`: Verify listing of `/`.
- `test_ls_home`: Verify listing of `/home` or current directory.
- `test_ls_format`: Use regex to validate that the output matches the expected format: `mode owner group size name`.
- `test_ls_invalid_dir`: Attempt to list a non-existent path; verify `tsh` return code.

### Binary Execution (`exec`)
- `test_exec_exit_zero`: Run `/bin/true`, verify exit code 0.
- `test_exec_exit_error`: Run `/bin/false`, verify exit code 1.
- `test_exec_with_args`: Run `/usr/bin/touch` with a path, verify exit code 0.
- `test_exec_not_found`: Attempt to execute a non-existent binary; verify return code (e.g., 255).

### File Transfer (`get` / `put`)
- `test_file_integrity_cycle`: 
    1. Generate a local file with random data and a known checksum.
    2. `put` the file to `/var/tmp`.
    3. `get` the file back to a new local path.
    4. Compare checksums to verify PEL integrity.
- `test_large_file_transfer`: Transfer a file larger than `BUFSIZE` (e.g., 1MB) to test PEL chunking.
- `test_transfer_permission_denied`: Attempt to `get` a root-only file or `put` to a read-only directory.

## 3. Automated Execution

Execute tests from the project root:
```bash
pytest -v
```
