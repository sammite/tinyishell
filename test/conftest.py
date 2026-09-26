"""Pytest fixtures and configuration for Tiny SHell test battery."""

# pylint: disable=redefined-outer-name

import os
import subprocess
import time

import pytest


def pytest_addoption(parser):
    """Add options to choose target binary build type."""
    parser.addoption("--musl", action="store_true", help="run tests with musl static binaries")
    parser.addoption(
        "--asan",
        action="store_true",
        help="run tests with AddressSanitizer instrumented binaries",
    )
    parser.addoption(
        "--valgrind",
        action="store_true",
        help="run tests with Valgrind debug binaries",
    )


@pytest.fixture(scope="session")
def build_tsh(request):
    """Builds tsh and tshd binaries once per session."""
    secret = "testkey"
    port = 1234

    # Determine target
    if request.config.getoption("--musl"):
        target = "linux_musl"
    elif request.config.getoption("--asan"):
        target = "linux_asan"
    elif request.config.getoption("--valgrind"):
        target = "linux_valgrind"
    else:
        target = "linux"

    # Clean and build
    subprocess.run(["make", "clean"], capture_output=True, check=False)
    cmd = ["make", target, f"SECRET_KEY={secret}", f"SERVER_PORT={port}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if result.returncode != 0:
        pytest.fail(f"Build failed: {result.stderr}")

    return {
        "secret": secret,
        "port": port,
        "tsh_path": "./tsh",
        "tshd_path": "./tshd",
        "target": target,
    }


@pytest.fixture
def tshd_daemon(build_tsh):
    """Starts the tshd daemon and ensures it's killed after the test."""
    # Ensure no old daemon is running
    subprocess.run(["killall", "-9", "tshd"], capture_output=True, check=False)

    # Start the daemon (it forks into background)
    env = os.environ.copy()
    if build_tsh["target"] == "linux_asan":
        env["ASAN_OPTIONS"] = "detect_leaks=1:abort_on_error=1:halt_on_error=1"

    subprocess.run([build_tsh["tshd_path"]], env=env, check=False)
    time.sleep(0.5)  # Give it a moment to start

    yield build_tsh

    # Cleanup: Kill all tshd processes
    subprocess.run(["killall", "-9", "tshd"], capture_output=True, check=False)
