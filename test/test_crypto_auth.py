"""Cryptographic and authentication error checking tests for tsh and tshd."""

import os
import subprocess
import time


def test_pel_c_unit_suite():
    """Compiles and executes the C cryptographic unit test suite.

    Validates:
    - Handshake key exchange and Ed25519 authentication
    - Rejection of mismatched secrets with PEL_WRONG_CHALLENGE
    - Poly1305 MAC tag and ciphertext bit-flip tamper rejection with PEL_CORRUPTED_DATA
    - Oversized packet length rejection with PEL_BAD_MSG_LENGTH
    """
    c_test_bin = "./test_pel_unit_bin"
    build_cmd = [
        "gcc",
        "-I.",
        "-Wall",
        "-Wextra",
        "-fno-asynchronous-unwind-tables",
        "-fno-unwind-tables",
        "test/test_pel_unit.c",
        "pel.c",
        "monocypher.c",
        "monocypher-ed25519.c",
        "-o",
        c_test_bin,
    ]
    try:
        build_res = subprocess.run(build_cmd, capture_output=True, text=True, check=False)
        assert build_res.returncode == 0, f"Compilation failed: {build_res.stderr}"

        run_res = subprocess.run([c_test_bin], capture_output=True, text=True, check=False)
        assert (
            run_res.returncode == 0
        ), f"PEL unit tests failed:\n{run_res.stdout}\n{run_res.stderr}"
        assert "All PEL C cryptographic unit tests passed successfully!" in run_res.stdout
    finally:
        if os.path.exists(c_test_bin):
            os.remove(c_test_bin)


def test_auth_failure_wrong_secret(tshd_daemon):
    """Verifies that attempting connection with an incorrect key fails cleanly."""
    config = tshd_daemon
    cmd = [
        config["tsh_path"],
        "-s",
        "definitely_wrong_secret",
        "localhost",
        "ls",
        "/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 10
    assert "Authentication failed." in res.stderr
    assert res.stdout == ""


def test_auth_failure_empty_secret(tshd_daemon):
    """Verifies that attempting connection with an empty secret fails cleanly."""
    config = tshd_daemon
    cmd = [
        config["tsh_path"],
        "-s",
        "",
        "localhost",
        "ls",
        "/",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 10
    assert "Authentication failed." in res.stderr
    assert res.stdout == ""


def test_auth_recovery_after_failed_attempts(tshd_daemon):
    """Verifies daemon remains responsive and stable after multiple failed authentications."""
    config = tshd_daemon

    # Send 5 invalid attempts in rapid succession
    for i in range(5):
        bad_cmd = [
            config["tsh_path"],
            "-s",
            f"attacker_attempt_{i}",
            "localhost",
            "ls",
            "/",
        ]
        res = subprocess.run(bad_cmd, capture_output=True, text=True, check=False)
        assert res.returncode == 10
        assert "Authentication failed." in res.stderr

    time.sleep(0.2)

    # Legitimate connection must succeed immediately
    good_cmd = [
        config["tsh_path"],
        "-s",
        config["secret"],
        "localhost",
        "ls",
        "/",
    ]
    good_res = subprocess.run(good_cmd, capture_output=True, text=True, check=False)
    assert good_res.returncode == 0
    assert "etc" in good_res.stdout or "bin" in good_res.stdout
