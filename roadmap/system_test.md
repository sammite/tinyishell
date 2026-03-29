# Roadmap: Complex System Test (Nested Daemon Deployment)

The objective of this test is to verify the full operational lifecycle of `tsh` by using an active connection to deploy and control a second, "nested" daemon configured in a different mode.

## 1. Objective
Validate that `tsh` can:
1. Build a functional daemon for a specific target configuration.
2. Transfer that binary to a remote system.
3. Prepare and execute the binary remotely.
4. Establish a secure communication channel with the new nested instance.

## 2. Test Scenario
- **Primary Daemon:** Standard bind mode on Port 1234.
- **Nested Daemon:** Connect-back mode targeting Port 5555 on localhost.
- **Workflow:**
    1. Build the Primary `tshd` binary (Bind mode) and rename it to `tshd_primary` to preserve its configuration.
    2. Build the Nested `tshd` binary (Connect-Back mode) and rename it to `tshd_nested`.
    3. Start `tshd_primary`.
    4. Use the `tsh` client to `put` the `tshd_nested` binary to `/var/tmp/tshd_nested` via the Primary Daemon.
    5. Use `tsh exec` to `chmod +x` and then start the remote `tshd_nested`.
    6. Start a `tsh` client in listener mode (`tsh cb`) on Port 5555.
    7. Connectivity is verified once the nested daemon connects back.

## 3. Implementation Challenges
- **Binary Management:** `tshd` binaries must be renamed immediately after building because their configuration (Port, CB_MODE, CB_HOST) is baked in at compile-time. Reusing the generic `tshd` name leads to deployment of incorrectly configured binaries.
- **Connect-Back Delay:** `tshd` has a hardcoded `CONNECT_BACK_DELAY` (default 5s). The test must account for this with retries and sufficient timeouts.
- **Cross-Device Links:** Moving binaries between `/tmp` (used by pytest `tmp_path`) and `/var/tmp` can trigger `EXDEV` errors. Use `shutil.move` or direct `put` from the original location.
- **Clean Environment:** Ensure no conflicting `tshd` processes exist before the test starts.
- **Makefile Recursion:** Ensure that recursive `make` calls correctly pass `DEFS` and macros (like `CB_MODE`) without quote stripping.

## 4. Success Criteria
- The `tsh cb` command successfully receives a connection.
- An `ls /` command executed through the nested connection returns a valid directory listing.
- Both daemons are successfully terminated and cleaned up after the test.
